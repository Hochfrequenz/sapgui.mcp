"""
SPRO (Customizing IMG) search tool.

This module provides a tool to search the SAP Implementation Guide (IMG)
for customizing activities by keyword. Returns structured results with
activity names, parent nodes, and area context.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.spro_parser import parse_spro_search_results
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import (
    SPRO_IMG_HEADING_DE,
    SPRO_IMG_HEADING_EN,
    SPRO_INITIAL_SCREEN_DE,
    SPRO_INITIAL_SCREEN_EN,
    SPRO_RESULTS_DIALOG_DE,
    SPRO_RESULTS_DIALOG_EN,
    SPRO_SEARCH_BUTTON_DE,
    SPRO_SEARCH_BUTTON_EN,
)
from sapguimcp.models.spro_models import SPROActivity, SPROFileSummary, SPROSearchResult

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_spro_tools"]

# Maximum time to wait for search results (ms)
_SEARCH_TIMEOUT_MS = 60_000
_SEARCH_POLL_INTERVAL_MS = 2_000

# F5 IMG tree loading can be slow — poll for heading
_F5_POLL_INTERVAL_S = 1.0
_F5_MAX_POLLS = 10  # 10 * 1s = 10 seconds max wait

# SPRO IMG tree control element ID (stable across languages)
_SPRO_TREE_ID = "wnd[0]/usr/cntlTREE_CONTROL_CONTAINER/shellcont/shell"


# =============================================================================
# SPRO Navigation Helpers
# =============================================================================


async def _click_sap_ref_img(backend: "WebGuiBackend | DesktopBackend") -> str | None:
    """Click 'SAP Referenz-IMG' / 'SAP Reference IMG' button via F5.

    On the SPRO initial screen, F5 triggers the SAP Reference IMG view.
    The IMG tree can take several seconds to render, so we poll for the
    heading instead of checking only once.

    Returns error string or None on success.
    """
    # Verify we're on the SPRO initial screen before pressing F5
    snapshot = await backend.get_snapshot()
    snapshot_str = str(snapshot)
    if SPRO_INITIAL_SCREEN_DE not in snapshot_str and SPRO_INITIAL_SCREEN_EN not in snapshot_str:
        return "Not on SPRO initial screen " f"(expected '{SPRO_INITIAL_SCREEN_DE}' or '{SPRO_INITIAL_SCREEN_EN}')"

    await backend.press_key("F5")
    await backend.wait_for_ready()

    # Poll for the IMG heading — the tree can take a few seconds to render.
    for poll in range(_F5_MAX_POLLS):
        snapshot = await backend.get_snapshot()
        snapshot_str = str(snapshot)
        if SPRO_IMG_HEADING_DE in snapshot_str or SPRO_IMG_HEADING_EN in snapshot_str:
            return None
        logger.debug("IMG heading not found yet, poll %d/%d", poll + 1, _F5_MAX_POLLS)
        await asyncio.sleep(_F5_POLL_INTERVAL_S)

    return "Failed to enter IMG tree (heading not found after F5)"


async def _open_search_dialog(backend: "WebGuiBackend | DesktopBackend") -> str | None:
    """Open the SPRO search dialog by clicking the search button.

    Ctrl+F is intercepted by the browser, so we click the button directly
    using the backend's click_button method.

    Returns error string or None on success.
    """
    for label in [SPRO_SEARCH_BUTTON_DE, SPRO_SEARCH_BUTTON_EN]:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            return None
        except ValueError:
            continue

    return "Could not find search button in IMG toolbar"


async def _fill_search_and_execute(backend: "WebGuiBackend", query: str) -> str | None:
    """Fill the search term in the dialog and press Enter.

    The search dialog textbox is a ct='CBS' field that requires real
    keyboard input (Playwright fill/JS value assignment don't trigger
    SAP's server-side state). We click the textbox to focus, then type
    via keyboard and press Enter.

    Returns error string or None on success.
    """
    # HACK: Raw JS querySelector + click() instead of Playwright's locator.click().
    # We need this because the protocol has no CSS-selector-based click method,
    # and the dialog textbox has no ARIA label usable with fill_field().
    # Unlike Playwright's locator, JS click() skips actionability checks
    # (visibility, stability), so this is less robust. The Tab fallback mitigates.
    try:
        focused = await backend.evaluate_javascript(
            "(() => {"
            "  const input = document.querySelector(\"[role='dialog'] input[role='textbox']\");"
            "  if (input) { input.focus(); input.click(); return true; }"
            "  return false;"
            "})()"
        )
        if not focused:
            logger.warning("Could not find search input, attempting Tab focus")
            await backend.press_key("Tab")
    except Exception:  # pylint: disable=broad-exception-caught
        logger.warning("Could not click search input, attempting Tab focus")
        await backend.press_key("Tab")

    # Clear any existing text and type the query
    await backend.press_key("Control+a")
    await backend.press_key("Delete")
    await backend.type_text(query)

    # Press Enter to execute search
    await backend.press_key("Enter")

    return None


async def _wait_for_results(backend: "WebGuiBackend | DesktopBackend") -> str:
    """Wait for SPRO search results dialog to appear.

    Polls for the results dialog title which appears when search completes.
    SPRO search can be slow (10-60+ seconds), especially on first run when
    the text index needs to be built.

    Returns the ARIA snapshot when results are ready, or the last snapshot on timeout.
    """
    elapsed_ms = 0

    while elapsed_ms < _SEARCH_TIMEOUT_MS:
        await asyncio.sleep(_SEARCH_POLL_INTERVAL_MS / 1000)
        elapsed_ms += _SEARCH_POLL_INTERVAL_MS

        snapshot = await backend.get_snapshot()
        snapshot_str = str(snapshot)

        # Check for results dialog
        if SPRO_RESULTS_DIALOG_DE in snapshot_str or SPRO_RESULTS_DIALOG_EN in snapshot_str:
            logger.info(
                "SPRO search results found after %d ms",
                elapsed_ms,
            )
            return snapshot

        # Check if we returned to the IMG tree (search dialog gone, no results)
        if SPRO_IMG_HEADING_DE in snapshot_str or SPRO_IMG_HEADING_EN in snapshot_str:
            if "dialog" not in snapshot_str.lower():
                logger.info(
                    "SPRO search completed with no results after %d ms",
                    elapsed_ms,
                )
                return snapshot

    # Timeout — return whatever we have
    logger.warning("SPRO search timed out after %d ms", _SEARCH_TIMEOUT_MS)
    return await backend.get_snapshot()


async def _search_img_desktop(  # pylint: disable=too-many-locals
    backend: "WebGuiBackend | DesktopBackend", query: str
) -> SPROSearchResult:
    """Desktop-specific SPRO IMG search using tree control node reading.

    The desktop SAP GUI doesn't expose the SPRO search dialog available in WebGUI.
    Instead, we expand the IMG tree nodes (2 levels deep) and filter by query text.
    """
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    now = datetime.now(UTC)

    # Navigate to SPRO and open IMG tree
    tx = await backend.enter_transaction("SPRO")
    if not tx.success:
        return SPROSearchResult.failure(
            error=f"Failed to navigate to SPRO: {tx.error}",
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )
    await backend.wait_for_ready()

    # Press F5 for SAP Reference IMG
    await backend.press_key("F5")
    await backend.wait(3000)

    if not isinstance(backend, DesktopBackend):
        return SPROSearchResult.failure(
            error="SPRO desktop search requires DesktopBackend",
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    session = backend.require_session()
    com = backend.com

    def _read_and_search() -> list[dict[str, str]]:
        """Expand top-level nodes, read children, filter by query."""
        tree = session.find_by_id(_SPRO_TREE_ID)
        raw: Any = getattr(tree, "com", getattr(tree, "_com", tree))

        keys = raw.GetAllNodeKeys()
        query_lower = query.lower()
        matches: list[dict[str, str]] = []

        # Expand all level-02 nodes to reveal level-03 children (activities)
        # Key format: 'LL  P      N' where LL is a 2-digit zero-padded level
        level2_keys: list[str] = []
        for i in range(keys.Count):
            k: str = keys(i)
            if k[:2] == "02":
                level2_keys.append(k)

        for k in level2_keys:
            try:
                raw.ExpandNode(k)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Re-read all nodes after expansion
        keys = raw.GetAllNodeKeys()
        # Build parent context map
        current_l2 = ""
        for i in range(keys.Count):
            k = keys(i)
            text: str = raw.GetItemText(k, "TEXT")
            level = k[:2]

            if level == "02":
                current_l2 = text
            if query_lower in text.lower() and level in ("02", "03"):
                matches.append(
                    {
                        "activity_name": text,
                        "parent_node": current_l2 if level == "03" else "SAP Customizing",
                        "area": current_l2,
                    }
                )

        return matches

    raw_matches = await com.run(_read_and_search)

    # Navigate back: F3 exits IMG tree, F3 exits SPRO
    await backend.press_key("F3")
    await backend.press_key("F3")

    activities = [SPROActivity(**m) for m in raw_matches]
    return SPROSearchResult(
        query=query,
        activities=activities,
        activity_count=len(activities),
        retrieved_at=now,
    )


async def _search_img(backend: "WebGuiBackend", query: str) -> SPROSearchResult:
    """Execute a full SPRO IMG search."""
    now = datetime.now(UTC)

    # Navigate to SPRO
    tx_result = await backend.enter_transaction("SPRO")
    if not tx_result.success:
        return SPROSearchResult.failure(
            error=f"Failed to navigate to SPRO: {tx_result.error}",
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    await backend.wait_for_ready()

    # Enter IMG tree (F5)
    img_error = await _click_sap_ref_img(backend)
    if img_error:
        return SPROSearchResult.failure(
            error=img_error,
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Open search dialog
    dialog_error = await _open_search_dialog(backend)
    if dialog_error:
        return SPROSearchResult.failure(
            error=dialog_error,
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Fill search term and execute
    search_error = await _fill_search_and_execute(backend, query)
    if search_error:
        return SPROSearchResult.failure(
            error=search_error,
            query=query,
            activities=[],
            activity_count=0,
            retrieved_at=now,
        )

    # Wait for results
    snapshot = AriaSnapshot(await _wait_for_results(backend))
    logger.debug("SPRO search snapshot length=%d", len(str(snapshot)))

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

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_spro_search")
        except ValueError as e:
            return SPROSearchResult.failure(
                error=f"Session error: {e}",
                query=query,
                activities=[],
                activity_count=0,
                retrieved_at=now,
            )

        # Desktop backend: use tree control reading instead of ARIA parsing
        if backend.backend_type == "desktop":
            try:
                result = await _search_img_desktop(backend, query)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("SPRO desktop search query=%r", query)
                result = SPROSearchResult.failure(
                    error=f"Error searching IMG for '{query}': {e}",
                    query=query,
                    activities=[],
                    activity_count=0,
                    retrieved_at=now,
                )
        else:
            try:
                result = await _search_img(cast("WebGuiBackend", backend), query)
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
                retrieved_at=result.retrieved_at,
            )

        return result
