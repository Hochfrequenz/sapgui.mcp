"""
SE24 (Class Builder) lookup tool.

This module provides a tool to look up class/interface metadata from SE24,
returning strongly-typed Pydantic models with method and attribute details.
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
    SE24Entry,
    SE24Error,
    SE24FileSummary,
    SE24Result,
    get_browser_manager,
)
from sapwebguimcp.parsers.se24_parser import SE24TabSnapshots, parse_se24_snapshot
from sapwebguimcp.tools.sap_tool_impl import sap_transaction_impl

logger = logging.getLogger(__name__)

__all__ = ["register_se24_tools"]

# Threshold for writing to file instead of returning inline
MAX_INLINE_OBJECTS = 5


# =============================================================================
# SE24 Navigation Helpers
# =============================================================================


async def _fill_class_field(page: Any, class_name: str) -> SE24Error | None:
    """Fill the class/interface name field in SE24. Returns error or None."""
    now = datetime.now(UTC)

    # Try German label first, then English
    # German: "Objekttyp" or "Klasse/Interface"
    class_field = page.get_by_role("textbox", name="Objekttyp")
    if await class_field.count() == 0:
        class_field = page.get_by_role("textbox", name="Object type")
    if await class_field.count() == 0:
        class_field = page.get_by_role("textbox", name="Object Type")
    if await class_field.count() == 0:
        class_field = page.get_by_role("textbox", name="Klasse/Interface")
    if await class_field.count() == 0:
        class_field = page.get_by_role("textbox", name="Class/Interface")

    if await class_field.count() == 0:
        return SE24Error(
            class_name=class_name,
            error="Could not find class/interface field in SE24",
            retrieved_at=now,
        )

    await class_field.click(click_count=3)
    await page.wait_for_timeout(50)
    await page.keyboard.type(class_name.upper())
    return None


async def _click_display_button(page: Any) -> None:
    """Click the Display button (F7)."""
    await page.wait_for_timeout(300)
    await page.keyboard.press("F7")
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")


async def _check_class_not_found(page: Any, class_name: str) -> SE24Error | None:
    """Check if status bar shows class not found. Returns error or None."""
    now = datetime.now(UTC)
    status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
    status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""

    not_found_msgs = {
        "existiert nicht",
        "does not exist",
        "nicht gefunden",
        "not found",
        "nicht vorhanden",
    }
    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        await page.keyboard.press("F3")
        await page.wait_for_load_state("networkidle")
        return SE24Error(
            class_name=class_name,
            error=f"Class/interface '{class_name}' not found",
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
        "methods": ["Methoden", "Methods"],
        "attributes": ["Attribute", "Attributes"],
        "interfaces": ["Interfaces", "Schnittstellen"],
    }

    names_to_try = tab_names.get(tab_name, [tab_name])
    for name in names_to_try:
        if await _click_tab(page, name):
            await page.wait_for_timeout(200)
            snapshot: str = await page.locator("body").aria_snapshot()
            return snapshot

    return None


async def _lookup_single_class(page: Any, class_name: str) -> SE24Entry | SE24Error:
    """Look up a single class/interface in SE24."""
    now = datetime.now(UTC)

    # Navigate to SE24
    await page.wait_for_timeout(300)
    tx_result = await sap_transaction_impl("SE24")
    if not tx_result.success:
        return SE24Error(
            class_name=class_name,
            error=f"Failed to navigate to SE24: {tx_result.error}",
            retrieved_at=now,
        )

    # Wait for SE24 screen
    try:
        class_field = page.get_by_role("textbox", name="Objekttyp")
        if await class_field.count() == 0:
            class_field = page.get_by_role("textbox", name="Object type")
        await class_field.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeout:
        page_title = await page.title()
        return SE24Error(
            class_name=class_name,
            error=f"SE24 screen did not load (page title: '{page_title}')",
            retrieved_at=now,
        )

    # Fill class name
    error = await _fill_class_field(page, class_name)
    if error:
        return error

    # Click display
    await _click_display_button(page)

    # Check for not found error
    error = await _check_class_not_found(page, class_name)
    if error:
        return error

    # Get main snapshot first
    main_snapshot: str = await page.locator("body").aria_snapshot()
    logger.debug("SE24: Got main snapshot for %s, length: %d chars", class_name, len(main_snapshot))

    # Capture each tab
    tab_snapshots = SE24TabSnapshots(
        methods_tab=await _capture_tab_snapshot(page, "methods"),
        attributes_tab=await _capture_tab_snapshot(page, "attributes"),
        interfaces_tab=await _capture_tab_snapshot(page, "interfaces"),
    )

    # Parse all snapshots
    return parse_se24_snapshot(
        snapshot=main_snapshot,
        class_name=class_name,
        tab_snapshots=tab_snapshots,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se24_tools(mcp: FastMCP) -> None:
    """Register SE24 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up class/interface metadata from SE24 (Class Builder). "
            "Returns class structure including methods with parameters, "
            "attributes, and implemented interfaces. Supports single class or list of classes. "
            "Each method includes: name, visibility, parameters, exceptions, and description."
        ),
    )
    async def sap_se24_lookup(
        classes: str | list[str],
        output_file: str | None = None,
    ) -> SE24Result | SE24FileSummary:
        """
        Look up class/interface metadata from SE24.

        Args:
            classes: Single class/interface name or list of names
                (e.g., 'CL_SALV_TABLE' or ['CL_SALV_TABLE', 'CL_ABAP_CHAR_UTILITIES'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >5 classes to avoid context overflow.

        Returns:
            SE24Result with entries and errors (inline), or
            SE24FileSummary with file path and statistics (when output_file provided)
        """
        class_list = [classes] if isinstance(classes, str) else list(classes)

        if not class_list:
            return SE24Result.failure("No classes provided")

        browser_manager = await get_browser_manager()
        page = await browser_manager.get_current_page()

        entries: list[SE24Entry] = []
        errors: list[SE24Error] = []

        for class_name in class_list:
            try:
                result = await _lookup_single_class(page, class_name)
                if isinstance(result, SE24Entry):
                    entries.append(result)
                else:
                    errors.append(result)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error looking up %s in SE24", class_name)
                errors.append(
                    SE24Error(
                        class_name=class_name,
                        error=f"Error looking up '{class_name}': {e}",
                        retrieved_at=datetime.now(UTC),
                    )
                )

        # Build final result
        if entries:
            final_result = SE24Result(entries=entries, errors=errors)
        else:
            final_result = SE24Result.failure(
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

            return SE24FileSummary(
                success=final_result.success,
                error=final_result.error,
                output_file=str(output_path.absolute()),
                total_requested=len(class_list),
                successful=len(entries),
                failed=len(errors),
                sample_entries=[e.class_name for e in entries[:5]],
                sample_errors=[e.class_name for e in errors[:5]],
            )

        if len(class_list) > MAX_INLINE_OBJECTS:
            logger.warning(
                "Returning %d classes inline - consider using output_file parameter",
                len(class_list),
            )

        return final_result
