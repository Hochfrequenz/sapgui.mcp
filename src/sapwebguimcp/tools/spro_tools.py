"""
SPRO (Customizing IMG) search tool.

This module provides a tool to search the SAP Implementation Guide (IMG)
for customizing activities by keyword. Returns structured results with
activity names, parent nodes, and area context.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import Page

from sapwebguimcp.lang import (
    SPRO_RESULTS_DIALOG_DE,
    SPRO_RESULTS_DIALOG_EN,
    SPRO_SEARCH_BUTTON_DE,
    SPRO_SEARCH_BUTTON_EN,
    bilingual_pattern,
)
from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.spro_models import SPROFileSummary, SPROSearchResult
from sapwebguimcp.parsers.spro_parser import parse_spro_search_results
from sapwebguimcp.tools.sap_page_helpers import navigate_transaction

logger = logging.getLogger(__name__)

__all__ = ["register_spro_tools"]

# Maximum time to wait for search results (ms)
_SEARCH_TIMEOUT_MS = 60_000
_SEARCH_POLL_INTERVAL_MS = 2_000


# =============================================================================
# SPRO Navigation Helpers
# =============================================================================


async def _click_sap_ref_img(page: Page) -> str | None:
    """Click 'SAP Referenz-IMG' / 'SAP Reference IMG' button via F5.

    On the SPRO initial screen, F5 triggers the SAP Reference IMG view.
    Returns error string or None on success.
    """
    await page.keyboard.press("F5")
    await page.wait_for_timeout(3000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(500)

    # Verify we're in the IMG tree by checking for the search button
    snapshot = await page.locator("body").aria_snapshot()
    if SPRO_SEARCH_BUTTON_DE not in snapshot and SPRO_SEARCH_BUTTON_EN not in snapshot:
        return "Failed to enter IMG tree (search button not found after F5)"

    return None


async def _open_search_dialog(page: Page) -> str | None:
    """Open the SPRO search dialog by clicking the search button.

    The search button is a DIV with role=button and title containing
    'Suchen (Strg+F)' (DE) or 'Find (Ctrl+F)' (EN). Ctrl+F is intercepted
    by the browser, so we must click the button directly via its title attribute.

    Returns error string or None on success.
    """
    # Click search button via title attribute (SAP WebGUI uses DIV buttons)
    search_pattern = bilingual_pattern(SPRO_SEARCH_BUTTON_DE, SPRO_SEARCH_BUTTON_EN)
    clicked = await page.evaluate(
        """(pattern) => {
            const regex = new RegExp(pattern);
            const btn = document.querySelector('[title*="Such"][title*="Strg"]') ||
                        document.querySelector('[title*="Find"][title*="Ctrl"]');
            if (btn) { btn.click(); return true; }
            return false;
        }""",
        search_pattern,
    )

    if not clicked:
        return "Could not find search button in IMG toolbar"

    await page.wait_for_timeout(1500)
    return None


async def _fill_search_and_execute(page: Page, query: str) -> str | None:
    """Fill the search term in the dialog and press Enter.

    The search dialog textbox is a ct='CBS' field that requires real
    keyboard input (Playwright fill/JS value assignment don't trigger
    SAP's server-side state). We click the input, type via keyboard,
    and press Enter.

    Returns error string or None on success.
    """
    # Click the search input in the dialog to focus it
    search_input = page.locator("[role='dialog'] input[role='textbox']")
    if await search_input.count() == 0:
        return "Search dialog not found or has no input field"

    await search_input.click()
    await page.wait_for_timeout(300)

    # Clear any existing text
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(100)

    # Type search term character by character (SAP CBS field requirement)
    await page.keyboard.type(query)
    await page.wait_for_timeout(300)

    # Press Enter to execute search
    await page.keyboard.press("Enter")

    return None


async def _wait_for_results(page: Page) -> str:
    """Wait for SPRO search results dialog to appear.

    Polls for the results dialog title which appears when search completes.
    SPRO search can be slow (10-60+ seconds), especially on first run when
    the text index needs to be built.

    Returns the ARIA snapshot when results are ready, or an error snapshot.
    """
    elapsed_ms = 0

    while elapsed_ms < _SEARCH_TIMEOUT_MS:
        await page.wait_for_timeout(_SEARCH_POLL_INTERVAL_MS)
        elapsed_ms += _SEARCH_POLL_INTERVAL_MS

        snapshot = await page.locator("body").aria_snapshot()

        # Check for results dialog
        if SPRO_RESULTS_DIALOG_DE in snapshot or SPRO_RESULTS_DIALOG_EN in snapshot:
            logger.info(
                "SPRO search results found after %d ms",
                elapsed_ms,
            )
            return snapshot

        # Check if loading indicator is gone and no results dialog
        if "Loading" not in snapshot and "dialog" not in snapshot:
            # Search completed with no results (dialog closed)
            logger.info(
                "SPRO search completed with no results after %d ms",
                elapsed_ms,
            )
            return snapshot

    # Timeout — return whatever we have
    logger.warning("SPRO search timed out after %d ms", _SEARCH_TIMEOUT_MS)
    return await page.locator("body").aria_snapshot()


async def _search_img(page: Page, query: str) -> SPROSearchResult:
    """Execute a full SPRO IMG search."""
    now = datetime.now(UTC)

    # Navigate to SPRO
    tx_error = await navigate_transaction(page, "SPRO")
    if tx_error:
        return SPROSearchResult.failure(
            error=f"Failed to navigate to SPRO: {tx_error}",
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Enter IMG tree (F5)
    img_error = await _click_sap_ref_img(page)
    if img_error:
        return SPROSearchResult.failure(
            error=img_error,
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Open search dialog
    dialog_error = await _open_search_dialog(page)
    if dialog_error:
        return SPROSearchResult.failure(
            error=dialog_error,
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Fill search term and execute
    search_error = await _fill_search_and_execute(page, query)
    if search_error:
        return SPROSearchResult.failure(
            error=search_error,
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Wait for results
    snapshot = await _wait_for_results(page)
    logger.debug("SPRO search snapshot length=%d", len(snapshot))

    return parse_spro_search_results(snapshot, query)


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_spro_tools(mcp: FastMCP) -> None:
    """Register SPRO tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Search the SAP Implementation Guide (IMG) for customizing activities by keyword. "
            "USE THIS to find where specific SAP configuration is maintained (e.g., 'country', "
            "'pricing', 'tax'). Returns matching IMG activities with their parent node and area. "
            "The search covers all IMG text content. Results can then be used to navigate to "
            "specific configuration via SM30 or other transactions.\n\n"
            "Note: First search in a language may be slow (30-60s) while the text index is built. "
            "Subsequent searches are faster."
        ),
    )
    async def sap_spro_search(
        query: str,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SPROSearchResult | SPROFileSummary:
        """
        Search the SAP Implementation Guide (IMG) for customizing activities.

        Args:
            query: Search keyword (e.g., 'country', 'pricing', 'tax')
            output_file: If provided, write full results to this JSON file and return summary.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SPROSearchResult with matching activities (inline), or
            SPROFileSummary with file path and preview (when output_file provided)
        """
        now = datetime.now(UTC)
        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_spro_search")
        except ValueError as e:
            return SPROSearchResult.failure(
                error=f"Session error: {e}",
                query=query,
                activities=[],
                activity_count=0,
                retrieved_at=now,
            )

        try:
            result = await _search_img(page, query)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("SPRO search query=%r", query)
            result = SPROSearchResult.failure(
                error=f"Error searching IMG for '{query}': {e}",
                query=query,
                activities=[],
                activity_count=0,
                retrieved_at=now,
            )

        # Write to file if requested
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SPROFileSummary(
                success=True,
                output_file=str(output_path.absolute()),
                query=result.query,
                activity_count=result.activity_count,
                sample_activities=result.activities[:5],
            )

        return result
