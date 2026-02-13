"""
SE24 (Class Builder) lookup tool.

This module provides a tool to look up class/interface metadata from SE24,
returning strongly-typed Pydantic models with method and attribute details.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

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


async def _find_class_field(page: Any) -> Any:
    """Find the class/interface input field in SE24 using multiple strategies."""
    # Build list of locator strategies to try in order
    strategies = [
        # Strategy 1: Try by role with exact name matches
        *[
            page.get_by_role("textbox", name=name)
            for name in ["Objekttyp", "Object type", "Object Type", "Klasse/Interface", "Class/Interface"]
        ],
        # Strategy 2: Try regex pattern for object type field
        page.get_by_role("textbox", name=re.compile(r"Objekt|Object|Klasse|Class", re.I)),
        # Strategy 3: Try by input title attribute (common in SAP Web GUI)
        page.locator("input[title*='Objekttyp'], input[title*='Object type']").first,
        # Strategy 4: Try by placeholder or aria-label
        page.locator("[aria-label*='Objekt'], [aria-label*='Object'], [aria-label*='Klasse']").first,
        # Strategy 5: Look for input field near the "Objekttyp" label
        page.locator("text=Objekttyp >> xpath=../following-sibling::*//input").first,
        # Strategy 6: First visible input field on the page (last resort)
        page.locator("input:visible").first,
    ]

    for field in strategies:
        if await field.count() > 0:
            return field

    return None


async def _fill_class_field(page: Any, class_name: str) -> SE24Error | None:
    """Fill the class/interface name field in SE24. Returns error or None."""
    now = datetime.now(UTC)

    class_field = await _find_class_field(page)

    if class_field is None or await class_field.count() == 0:
        return SE24Error(
            class_name=class_name,
            error="Could not find class/interface field in SE24",
            retrieved_at=now,
        )

    # Clear the field first by selecting all and deleting
    await class_field.click(click_count=3)
    await page.wait_for_timeout(100)
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(50)

    # Type the class name
    await page.keyboard.type(class_name.upper())
    await page.wait_for_timeout(100)
    return None


async def _click_display_button(page: Any) -> None:
    """Click the Display button (F7)."""
    await page.wait_for_timeout(300)
    await page.keyboard.press("F7")
    await page.wait_for_timeout(1000)  # Wait longer for SAP to process
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(500)  # Additional wait for page state to settle


async def _check_class_not_found(page: Any, class_name: str) -> SE24Error | None:
    """Check if class was not found by verifying page state. Returns error or None."""
    now = datetime.now(UTC)

    # Primary check: Are we still on the initial screen?
    # If we successfully displayed a class, the page title changes from "Einstieg"/"Initial"
    page_title = await page.title()
    is_initial_screen = "Einstieg" in page_title or "Initial" in page_title

    if not is_initial_screen:
        # We're on a display screen, so the class was found
        return None

    # We're still on initial screen - this means the class was not found
    # Check status bar for specific error message (but don't rely solely on it)
    status_bar = page.locator("#sapStatusBarAll, [id*='STATUSBAR']").first
    status_text = await status_bar.text_content() if await status_bar.count() > 0 else ""

    not_found_msgs = {
        "existiert nicht",
        "does not exist",
        "nicht gefunden",
        "not found",
        "nicht vorhanden",
    }

    # If status bar confirms not found, or we're still on initial screen after F7
    if status_text and any(msg in status_text.lower() for msg in not_found_msgs):
        error_msg = f"Class/interface '{class_name}' not found"
    else:
        # Still on initial screen but no clear error - might be a display issue
        error_msg = f"Class/interface '{class_name}' not found (still on initial screen)"

    # Don't press F3 here - the next /nSE24 will handle navigation
    # Pressing F3 can leave us in unexpected states
    return SE24Error(
        class_name=class_name,
        error=error_msg,
        retrieved_at=now,
    )


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
        logger.debug("Failed to click tab", extra={"tab": tab_name})
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

    # Wait for SE24 screen to be ready
    await page.wait_for_timeout(500)
    await page.wait_for_load_state("networkidle")

    # Try to find the class field with multiple strategies
    class_field = await _find_class_field(page)
    if class_field is None or await class_field.count() == 0:
        page_title = await page.title()
        return SE24Error(
            class_name=class_name,
            error=f"SE24 screen did not load or field not found (page title: '{page_title}')",
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
    logger.debug("Got main snapshot", extra={"object": class_name, "length": len(main_snapshot)})

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
            "USE THIS instead of sap_transaction('SE24') - faster and returns structured data. "
            "Returns class structure including methods with parameters, "
            "attributes, and implemented interfaces. Supports single class or list of classes. "
            "Each method includes: name, visibility, parameters, exceptions, and description."
        ),
    )
    async def sap_se24_lookup(
        classes: str | list[str],
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE24Result | SE24FileSummary:
        """
        Look up class/interface metadata from SE24.

        Args:
            classes: Single class/interface name or list of names
                (e.g., 'CL_SALV_TABLE' or ['CL_SALV_TABLE', 'CL_ABAP_CHAR_UTILITIES'])
            output_file: If provided, write full results to this JSON file and return summary.
                        Recommended for >5 classes to avoid context overflow.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE24Result with entries and errors (inline), or
            SE24FileSummary with file path and statistics (when output_file provided)
        """
        class_list = [classes] if isinstance(classes, str) else list(classes)

        if not class_list:
            return SE24Result.failure("No classes provided")

        browser_manager = await get_browser_manager()

        try:
            page = browser_manager.get_session_page_checked(session, agent_id, "sap_se24_lookup")
        except ValueError as e:
            return SE24Result.failure(f"Session error: {e}")

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
                logger.exception("Looking up in SE24", extra={"object": class_name})
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
                "Returning classes inline - consider using output_file parameter",
                extra={"count": len(class_list)},
            )

        return final_result
