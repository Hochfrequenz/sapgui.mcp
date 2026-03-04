"""
SM30 (Table Maintenance View) read-only lookup tool.

This module provides a tool to display SM30 table maintenance views,
returning structured data with dynamically-parsed columns and rows.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import Locator, Page

from sapwebguimcp.backend.types import AriaSnapshot
from sapwebguimcp.lang import (
    SM30_DISPLAY_BUTTON_DE,
    SM30_DISPLAY_BUTTON_EN,
    SM30_TABLE_VIEW_DE,
    SM30_TABLE_VIEW_EN,
    bilingual_pattern,
)
from sapwebguimcp.models import get_browser_manager
from sapwebguimcp.models.sm30_models import SM30FileSummary, SM30ViewResult
from sapwebguimcp.parsers.sm30_parser import parse_sm30_snapshot
from sapwebguimcp.tools.sap_page_helpers import navigate_transaction

logger = logging.getLogger(__name__)

__all__ = ["register_sm30_tools"]


# =============================================================================
# SM30 Navigation Helpers
# =============================================================================


async def _find_view_field(page: Page) -> Locator | None:
    """Find the Table/View input field in SM30 using multiple strategies."""
    strategies = [
        page.get_by_role("textbox", name=SM30_TABLE_VIEW_DE),
        page.get_by_role("textbox", name=SM30_TABLE_VIEW_EN),
        page.get_by_role(
            "textbox",
            name=re.compile(
                bilingual_pattern(SM30_TABLE_VIEW_DE, SM30_TABLE_VIEW_EN),
                re.I,
            ),
        ),
    ]

    for field in strategies:
        if await field.count() > 0:
            return field

    return None


async def _fill_view_field(page: Page, view_name: str) -> str | None:
    """Fill the view name field in SM30. Returns error string or None."""
    view_field = await _find_view_field(page)

    if view_field is None or await view_field.count() == 0:
        return "Could not find Table/View field in SM30"

    # Clear the field
    await view_field.click(click_count=3)
    await page.wait_for_timeout(100)
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(50)

    # Type the view name
    await page.keyboard.type(view_name.upper())
    await page.wait_for_timeout(100)
    return None


async def _click_display_button(page: Page) -> str | None:
    """
    Click the Anzeigen/Display button in SM30.

    SM30 does not use standard F5/F7 keys for Display. We use Playwright's
    native button click which properly triggers SAP WebGUI's event handlers.

    Returns error string or None on success.
    """
    for label in [SM30_DISPLAY_BUTTON_DE, SM30_DISPLAY_BUTTON_EN]:
        btn = page.get_by_role("button", name=label, exact=True)
        if await btn.count() > 0:
            try:
                await btn.click()
                await page.wait_for_timeout(2000)
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(500)
                return None
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Click %r button failed: %r", label, e)
                continue

    return "Could not find Anzeigen/Display button in SM30"


async def _lookup_view(page: Page, view_name: str) -> SM30ViewResult:
    """Look up a single SM30 view."""
    now = datetime.now(UTC)

    # Navigate to SM30
    tx_error = await navigate_transaction(page, "SM30")
    if tx_error:
        return SM30ViewResult.failure(
            error=f"Failed to navigate to SM30: {tx_error}",
            view_name=view_name,
            description="",
            view_type="unsupported",
            columns=[],
            rows=[],
            row_count=0,
            retrieved_at=now,
        )

    # Wait for SM30 screen to be ready
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Fill view name
    fill_error = await _fill_view_field(page, view_name)
    if fill_error:
        return SM30ViewResult.failure(
            error=fill_error,
            view_name=view_name,
            description="",
            view_type="unsupported",
            columns=[],
            rows=[],
            row_count=0,
            retrieved_at=now,
        )

    # Click Display button
    click_error = await _click_display_button(page)
    if click_error:
        return SM30ViewResult.failure(
            error=click_error,
            view_name=view_name,
            description="",
            view_type="unsupported",
            columns=[],
            rows=[],
            row_count=0,
            retrieved_at=now,
        )

    # Get snapshot and parse
    snapshot = await page.locator("body").aria_snapshot()
    logger.debug(
        "Got SM30 snapshot view=%r length=%d",
        view_name,
        len(snapshot),
    )

    return parse_sm30_snapshot(AriaSnapshot(snapshot), view_name)


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_sm30_tools(mcp: FastMCP) -> None:
    """Register SM30 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up SAP table maintenance view entries from SM30 (read-only display mode). "
            "USE THIS instead of sap_transaction('SM30') - faster and returns structured data. "
            "Returns entries from the maintenance view with dynamically-parsed columns. "
            "Supports any flat table view (e.g., V_T005 for countries, custom Z* views). "
            "Non-flat views (SM34/cluster/hierarchical) are detected and reported as unsupported. "
            "Note: only the first page of rows is returned (typically ~12 rows); "
            "views with more entries will report the total row_count from the view header."
        ),
    )
    async def sap_sm30_lookup(
        view_name: str,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SM30ViewResult | SM30FileSummary:
        """
        Look up table maintenance view entries from SM30.

        Args:
            view_name: The maintenance view or table name (e.g., 'V_T005', 'V_T002')
            output_file: If provided, write full results to this JSON file and return summary.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SM30ViewResult with view data (inline), or
            SM30FileSummary with file path and preview (when output_file provided)
        """
        now = datetime.now(UTC)
        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_sm30_lookup")
        except ValueError as e:
            return SM30ViewResult.failure(
                error=f"Session error: {e}",
                view_name=view_name,
                description="",
                view_type="unsupported",
                columns=[],
                rows=[],
                row_count=0,
                retrieved_at=now,
            )

        try:
            result = await _lookup_view(page, view_name)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Looking up SM30 view=%r", view_name)
            result = SM30ViewResult.failure(
                error=f"Error looking up view '{view_name}': {e}",
                view_name=view_name,
                description="",
                view_type="unsupported",
                columns=[],
                rows=[],
                row_count=0,
                retrieved_at=now,
            )

        # Write to file if requested
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SM30FileSummary(
                success=True,
                output_file=str(output_path.absolute()),
                view_name=result.view_name,
                description=result.description,
                view_type=result.view_type,
                columns=result.columns,
                row_count=result.row_count,
                sample_rows=result.rows[:5],
            )

        return result
