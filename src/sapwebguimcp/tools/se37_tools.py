"""
SE37 (Function Builder) lookup tool.

This module provides a tool to look up function module metadata from SE37,
returning strongly-typed Pydantic models with parameter and exception details.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from playwright.async_api import TimeoutError as PlaywrightTimeout

from sapwebguimcp.models import (
    SE37Entry,
    SE37Error,
    SE37FileSummary,
    SE37Result,
    get_browser_manager,
)
from sapwebguimcp.parsers.se37_parser import SE37TabSnapshots, parse_se37_snapshot
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_se37_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE37 Navigation Helpers
# =============================================================================


async def _fill_fm_field(page: Any, fm_name: str) -> SE37Error | None:
    """Fill the function module name field in SE37. Returns error or None."""
    now = datetime.now(UTC)

    # Try German label first, then English
    fm_field = page.get_by_role("textbox", name="Funktionsbaustein")
    if await fm_field.count() == 0:
        fm_field = page.get_by_role("textbox", name="Function module")
    if await fm_field.count() == 0:
        fm_field = page.get_by_role("textbox", name="Function Module")

    if await fm_field.count() == 0:
        return SE37Error(
            function_module=fm_name,
            error="Could not find function module field in SE37",
            retrieved_at=now,
        )

    await fm_field.click(click_count=3)
    await page.wait_for_timeout(50)
    await page.keyboard.type(fm_name.upper())
    return None


async def _click_display_button(page: Any) -> None:
    """Click the Display button (F7)."""
    await page.wait_for_timeout(300)
    await page.keyboard.press("F7")
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")


async def _check_fm_not_found(page: Any, fm_name: str) -> SE37Error | None:
    """Check if status bar shows function module not found. Returns error or None."""
    now = datetime.now(UTC)
    status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
    status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""

    not_found_msgs = {
        "ist noch nicht vorhanden",
        "does not exist",
        "nicht gefunden",
        "not found",
        "nicht vorhanden",
    }
    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        await page.keyboard.press("F3")
        await page.wait_for_load_state("networkidle")
        return SE37Error(
            function_module=fm_name,
            error=f"Function module '{fm_name}' not found",
            retrieved_at=now,
        )

    return None


async def _click_tab(page: Any, tab_name: str) -> bool:
    """Click a tab by name. Returns True if successful."""
    try:
        tab = page.locator(f"[role='tab']:has-text('{tab_name}')")
        if await tab.count() > 0:
            await tab.click()
            await page.wait_for_timeout(300)
            await page.wait_for_load_state("networkidle")
            return True
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("Failed to click tab: %s", tab_name)
    return False


async def _capture_tab_snapshot(page: Any, tab_name: str) -> str | None:
    """Click a tab and capture its snapshot. Returns snapshot or None."""
    # Try German and English tab names
    tab_names = {
        "import": ["Import"],
        "export": ["Export"],
        "changing": ["Changing"],
        "tables": ["Tabellen", "Tables"],
        "exceptions": ["Ausnahmen", "Exceptions"],
    }

    names_to_try = tab_names.get(tab_name, [tab_name])
    for name in names_to_try:
        if await _click_tab(page, name):
            await page.wait_for_timeout(200)
            snapshot: str = await page.locator("body").aria_snapshot()
            return snapshot

    return None


async def _lookup_single_fm(page: Any, fm_name: str) -> SE37Entry | SE37Error:
    """Look up a single function module in SE37."""
    now = datetime.now(UTC)

    # Navigate to SE37
    await page.wait_for_timeout(300)
    tx_result = await sap_transaction_impl("SE37")
    if not tx_result.success:
        return SE37Error(
            function_module=fm_name,
            error=f"Failed to navigate to SE37: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for SE37 screen
    try:
        fm_field = page.get_by_role("textbox", name="Funktionsbaustein")
        if await fm_field.count() == 0:
            fm_field = page.get_by_role("textbox", name="Function module")
        await fm_field.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        page_title = await page.title()
        return SE37Error(
            function_module=fm_name,
            error=f"SE37 screen did not load (page title: '{page_title}')",
            retrieved_at=now,
        )

    # Fill function module name
    error = await _fill_fm_field(page, fm_name)
    if error:
        return error

    # Click display
    await _click_display_button(page)

    # Check for not found error
    error = await _check_fm_not_found(page, fm_name)
    if error:
        return error

    # Get main snapshot first
    main_snapshot = await page.locator("body").aria_snapshot()
    logger.debug("SE37: Got main snapshot for %s, length: %d chars", fm_name, len(main_snapshot))

    # Capture each tab
    tab_snapshots = SE37TabSnapshots(
        import_tab=await _capture_tab_snapshot(page, "import"),
        export_tab=await _capture_tab_snapshot(page, "export"),
        changing_tab=await _capture_tab_snapshot(page, "changing"),
        tables_tab=await _capture_tab_snapshot(page, "tables"),
        exceptions_tab=await _capture_tab_snapshot(page, "exceptions"),
    )

    # Parse all snapshots
    return parse_se37_snapshot(
        snapshot=main_snapshot,
        fm_name=fm_name,
        tab_snapshots=tab_snapshots,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se37_tools(mcp: FastMCP) -> None:
    """Register SE37 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up function module metadata from SE37 (Function Builder). "
            "Returns function module signature including import/export/changing/tables parameters "
            "and exceptions. Supports single FM or list of FMs. "
            "Each parameter includes: name, typing (LIKE/TYPE), reference type, "
            "default value, optional flag, and description."
        ),
    )
    async def sap_se37_lookup(
        function_modules: str | list[str],
        output_file: str | None = None,
    ) -> SE37Result | SE37FileSummary:
        """
        Look up function module metadata from SE37.

        Args:
            function_modules: Single FM name or list of names
                (e.g., 'RFC_READ_TABLE' or ['RFC_READ_TABLE', 'BAPI_USER_GET_DETAIL'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >5 function modules to avoid context overflow.

        Returns:
            SE37Result with entries and errors (inline), or
            SE37FileSummary with file path and statistics (when output_file provided)
        """
        fm_list = [function_modules] if isinstance(function_modules, str) else list(function_modules)

        if not fm_list:
            return SE37Result.failure("No function modules provided")

        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        entries: list[SE37Entry] = []
        errors: list[SE37Error] = []

        for fm_name in fm_list:
            try:
                result = await _lookup_single_fm(page, fm_name)
                if isinstance(result, SE37Entry):
                    entries.append(result)
                else:
                    errors.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error looking up %s in SE37", fm_name)
                errors.append(
                    SE37Error(
                        function_module=fm_name,
                        error=f"Error looking up '{fm_name}': {e}",
                        retrieved_at=datetime.now(UTC),
                    )
                )

        # Build final result
        if entries:
            final_result = SE37Result(entries=entries, errors=errors)
        else:
            final_result = SE37Result.failure(
                error=f"All {len(errors)} lookups failed",
                entries=[],
                errors=errors,
            )

        # Write to file if requested
        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(final_result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE37FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(fm_list),
                successful=len(entries),
                failed=len(errors),
                sample_entries=[e.function_module for e in entries[:5]],
                sample_errors=[e.function_module for e in errors[:5]],
            )

        if len(fm_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning %d function modules inline - consider using output_file parameter",
                len(fm_list),
            )

        return final_result
