"""
ST22 (Short Dump Analysis) lookup tool.

This module provides a tool to list and inspect ABAP runtime errors (short dumps)
from ST22, returning strongly-typed Pydantic models with dump details.

ST22 flow:
1. Navigate to ST22 (selection screen with date/user/program filters)
2. Click "Heute"/"Today" or "Gestern"/"Yesterday" buttons for quick access,
   or fill date fields and press F8 for custom date ranges
3. Parse the dump list from the ALV grid
4. Optionally double-click a dump row to get detail text
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.st22_parser import (
    is_no_dumps_message,
    parse_st22_dump_detail,
    parse_st22_dump_list,
    parse_st22_initial_screen,
)
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.models import TableData
from sapguimcp.models.config import get_sap_config
from sapguimcp.models.st22_models import (
    ST22Dump,
    ST22DumpDetail,
    ST22DumpDetailResult,
    ST22DumpListResult,
)
from sapguimcp.utils import SapLanguage, format_sap_date

if TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_st22_tools"]


# =============================================================================
# ST22 Navigation Helpers
# =============================================================================


async def _navigate_to_st22(backend: "WebGuiBackend | DesktopBackend") -> str | None:
    """Navigate to ST22. Returns error message or None on success."""
    tx_result = await backend.enter_transaction("ST22")
    if not tx_result.success:
        return f"Failed to navigate to ST22: {tx_result.error}"

    await backend.wait_for_ready()
    return None


async def _clear_user_field(backend: "WebGuiBackend | DesktopBackend") -> None:
    """Clear the Benutzer/User field to search for all users.

    ST22 pre-fills the user field with the current user.
    We need to clear it using the backend's fill_field.
    """
    for label in ["Benutzer", "User"]:
        try:
            await backend.fill_field(label, "")
            return
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Could not clear user field with label=%r", label)
    # Fallback: try SAP technical field name (desktop backend)
    try:
        if await backend.focus_and_type("S_UNAME-LOW", ""):
            return
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    logger.debug("User field not found for clearing")


async def _fill_date_field(
    backend: "WebGuiBackend | DesktopBackend", target_date: str, language: SapLanguage
) -> str | None:
    """Fill the date field with a formatted date. Returns error or None."""
    try:
        formatted = format_sap_date(target_date, language)
    except ValueError:
        return f"Invalid date format: {target_date} (expected YYYY-MM-DD)"

    # Find and fill the Datum/Date field
    for label in ["Datum", "Date"]:
        try:
            await backend.fill_field(label, formatted)
            return None
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Could not fill date field with label=%r", label)

    # Fallback: try SAP technical field name (desktop backend)
    try:
        if await backend.focus_and_type("S_DATUM-LOW", formatted):
            return None
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    return "Could not find date field"


async def _try_quick_button(backend: "WebGuiBackend | DesktopBackend", target_date: str | None) -> bool:
    """Try to use Heute/Today or Gestern/Yesterday quick buttons.

    These buttons navigate directly to the dump list for all users,
    bypassing the selection screen filters.

    Returns True if a button was clicked, False otherwise.
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    if target_date is None or target_date == today.isoformat():
        labels = ["Heute", "Today"]
    elif target_date == yesterday.isoformat():
        labels = ["Gestern", "Yesterday"]
    else:
        return False

    for label in labels:
        try:
            await backend.click_button(label)
            await backend.wait_for_ready()
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Quick button click failed for label=%r", label)

    return False


async def _execute_search(backend: "WebGuiBackend | DesktopBackend", target_date: str | None) -> str | None:
    """Execute the ST22 search. Returns error or None.

    Strategy:
    1. Try Heute/Gestern quick buttons (preferred - works for all users)
    2. Fall back to clearing user field + filling date + F8
    """
    sap_cfg = get_sap_config()
    language: SapLanguage = sap_cfg.get_default().language

    # Strategy 1: Quick buttons for today/yesterday
    if await _try_quick_button(backend, target_date):
        return None

    # Strategy 2: Manual search with date field + F8
    # Clear user field to search for all users
    await _clear_user_field(backend)

    # Fill date if specified
    if target_date:
        error = await _fill_date_field(backend, target_date, language)
        if error:
            return error

    # Press F8 to execute
    await backend.press_key("F8")
    await backend.wait_for_ready()

    return None


async def _select_dump_by_index(
    backend: "WebGuiBackend | DesktopBackend", dump_index: int, dump_count: int
) -> str | None:
    """Select a dump from the list by double-clicking the row via click_table_cell.

    Returns error message or None on success.
    """
    if dump_index < 0 or dump_index >= dump_count:
        return f"dump_index {dump_index} out of range (0..{dump_count - 1})"

    try:
        # Use click_table_cell with dblclick action, row is 1-based in the backend
        result = await backend.click_table_cell(row=dump_index + 1, column=0, action="dblclick")
        if not result.success:
            return f"Could not select dump at index {dump_index}: {result.error}"
        await backend.wait_for_ready()
        return None
    except Exception as e:  # pylint: disable=broad-exception-caught
        return f"Could not find row at index {dump_index}: {e}"


async def _capture_full_detail(backend: "WebGuiBackend | DesktopBackend") -> str:
    """Capture the full dump detail by scrolling and collecting snapshots.

    ST22 detail is a long scrollable text. Scroll down and concatenate
    snapshots to get as much content as possible.
    """
    snapshots: list[str] = []

    # Capture initial view
    snapshot = await backend.get_snapshot()
    snapshots.append(str(snapshot))

    # Scroll down to capture more content (up to 10 pages)
    for _ in range(10):
        await backend.press_key("PageDown")
        new_snapshot = await backend.get_snapshot()
        new_snapshot_str = str(new_snapshot)

        # Stop if we get the same content (reached bottom)
        if new_snapshot_str == snapshots[-1]:
            break
        snapshots.append(new_snapshot_str)

    return "\n".join(snapshots)


async def _capture_desktop_detail(backend: "WebGuiBackend | DesktopBackend") -> str:
    """Capture full ST22 dump detail text by scrolling through the detail screen.

    The detail screen is a long scrollable text. Read screen text, scroll down,
    and concatenate until no new content appears.
    """
    pages: list[str] = []

    screen_text = await backend.get_screen_text()
    text = screen_text.full_text if hasattr(screen_text, "full_text") else str(screen_text)
    pages.append(text)

    for _ in range(20):  # max 20 pages
        await backend.press_key("PageDown")
        await backend.wait(500)
        screen_text = await backend.get_screen_text()
        new_text = screen_text.full_text if hasattr(screen_text, "full_text") else str(screen_text)
        if new_text == pages[-1]:
            break  # reached bottom
        pages.append(new_text)

    return "\n".join(pages)


def _parse_desktop_detail_text(full_text: str, source_dump: "ST22Dump") -> "ST22DumpDetail":
    """Parse raw dump detail text into an ST22DumpDetail model.

    Extracts structured fields from the free-text dump detail.
    Falls back to metadata from the list entry if parsing fails.
    """
    what_happened = ""
    how_to_correct = ""
    call_stack: list[str] = []
    program = source_dump.program
    error_type = source_dump.error_type
    line: int | None = None

    # Extract "What happened" section
    wh_match = re.search(r"(?:Was ist geschehen|What happened)\??\s*\n(.*?)(?:\n\s*\n|\Z)", full_text, re.DOTALL)
    if wh_match:
        what_happened = wh_match.group(1).strip()

    # Extract "How to correct" section
    hc_match = re.search(
        r"(?:Was können Sie tun|How to correct|Fehlerbehandlung)\??\s*\n(.*?)(?:\n\s*\n|\Z)", full_text, re.DOTALL
    )
    if hc_match:
        how_to_correct = hc_match.group(1).strip()

    # Extract source line
    line_match = re.search(r"(?:Zeile|Line|Quelltext)[:\s]+(\d+)", full_text)
    if line_match:
        line = int(line_match.group(1))

    # Extract call stack lines (lines starting with typical call stack patterns)
    for stack_line in re.findall(r"^\s*\d+\s+\S+.*$", full_text, re.MULTILINE):
        stripped = stack_line.strip()
        if stripped and len(stripped) > 10:
            call_stack.append(stripped)

    # Truncate raw text to ~10KB
    raw_text = full_text[:10240]

    return ST22DumpDetail(
        error_type=error_type,
        short_text=source_dump.short_text,
        what_happened=what_happened,
        how_to_correct=how_to_correct,
        program=program,
        include=source_dump.include,
        line=line,
        call_stack=call_stack[:20],  # limit to 20 entries
        raw_text=raw_text,
    )


# =============================================================================
# Main Lookup Logic
# =============================================================================


async def _st22_lookup_desktop(  # pylint: disable=too-many-locals,too-many-branches,too-many-return-statements
    backend: "WebGuiBackend | DesktopBackend",
    target_date: str | None,
    dump_index: int | None,
) -> ST22DumpListResult | ST22DumpDetailResult:
    """Desktop-specific ST22 lookup using read_table instead of ARIA parsing."""
    now = datetime.now(UTC)
    date_str = target_date or date.today().isoformat()
    logger.info("ST22 desktop backend path", extra={"date": date_str})

    # Navigate to ST22
    error = await _navigate_to_st22(backend)
    if error:
        return ST22DumpListResult.failure(
            error=error,
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Execute search
    error = await _execute_search(backend, target_date)
    if error:
        return ST22DumpListResult.failure(
            error=error,
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Check status bar for "no dumps"
    sbar = await backend.get_status_bar()
    if sbar.message and any(
        msg in sbar.message.lower() for msg in ["keine dumps", "no dumps", "keine kurzabzüge", "no short dumps"]
    ):
        if dump_index is not None:
            return ST22DumpDetailResult.failure(
                error=f"No dumps found for {date_str} -- cannot select dump_index {dump_index}",
                detail=None,
                retrieved_at=now,
            )
        return ST22DumpListResult(
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Read table data
    table_data: TableData = await backend.read_table(start_row=1, max_rows=200)

    if not table_data.headers:
        return ST22DumpListResult(
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Convert to ST22Dump models
    dumps: list[ST22Dump] = []
    for idx, tr in enumerate(table_data.rows):
        d = tr.data
        dumps.append(
            ST22Dump(
                index=idx,
                time=d.get("Uhrzeit", d.get("Time", "")),
                program=d.get("Programm", d.get("Program", "")),
                include=d.get("Include", None),
                error_type=d.get("Laufzeitfehler", d.get("Runtime Error", d.get("Runtime Errors", ""))),
                short_text=d.get("Kurztext", d.get("Short Text", d.get("Short text", ""))),
                user=d.get("Benutzer", d.get("User", "")),
            )
        )

    # Sort by time descending, keeping a mapping from sorted index to original
    # table row position (needed for double-clicking the correct row).
    indexed_dumps = [(d.index, d) for d in dumps]  # (original_table_row, dump)
    indexed_dumps.sort(key=lambda pair: pair[1].time, reverse=True)
    sorted_to_ui: dict[int, int] = {}
    dumps = []
    for new_idx, (orig_idx, dump) in enumerate(indexed_dumps):
        sorted_to_ui[new_idx] = orig_idx
        dump.index = new_idx
        dumps.append(dump)

    if dump_index is None:
        return ST22DumpListResult(
            dumps=dumps,
            dump_count=len(dumps),
            date_searched=date_str,
            retrieved_at=now,
        )

    # Bounds check
    if dump_index < 0 or dump_index >= len(dumps):
        return ST22DumpDetailResult.failure(
            error=f"dump_index {dump_index} out of range (0..{len(dumps) - 1})",
            detail=None,
            retrieved_at=now,
        )

    target_dump = dumps[dump_index]

    # Use the original table row position for clicking, not the sorted index
    ui_row_idx = sorted_to_ui[dump_index]
    error = await _select_dump_by_index(backend, ui_row_idx, len(dumps))
    if error:
        return ST22DumpDetailResult.failure(error=error, detail=None, retrieved_at=now)

    # Read detail screen text by scrolling through pages
    await backend.wait(1000)
    detail_text = await _capture_desktop_detail(backend)

    # Parse the detail text into structured fields
    detail = _parse_desktop_detail_text(detail_text, target_dump)

    return ST22DumpDetailResult(detail=detail, retrieved_at=now)


async def _st22_lookup(  # pylint: disable=too-many-return-statements,too-many-locals,too-many-branches
    backend: "WebGuiBackend | DesktopBackend",
    target_date: str | None,
    dump_index: int | None,
) -> ST22DumpListResult | ST22DumpDetailResult:
    """Core ST22 lookup logic."""
    now = datetime.now(UTC)
    date_str = target_date or date.today().isoformat()

    # Desktop backend: use read_table instead of ARIA snapshot parsing
    if backend.backend_type == "desktop":
        return await _st22_lookup_desktop(backend, target_date, dump_index)

    # Navigate to ST22
    error = await _navigate_to_st22(backend)
    if error:
        return ST22DumpListResult.failure(
            error=error,
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Execute search for the target date
    error = await _execute_search(backend, target_date)
    if error:
        return ST22DumpListResult.failure(
            error=error,
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Capture dump list snapshot
    list_snapshot = AriaSnapshot(await backend.get_snapshot())
    logger.debug("ST22 list snapshot captured, length=%r", len(str(list_snapshot)))

    # Check for "no dumps" message
    if is_no_dumps_message(list_snapshot):
        if dump_index is not None:
            return ST22DumpDetailResult.failure(
                error=f"No dumps found for {date_str} — cannot select dump_index {dump_index}",
                detail=None,
                retrieved_at=now,
            )
        return ST22DumpListResult(
            dumps=[],
            dump_count=0,
            date_searched=date_str,
            retrieved_at=now,
        )

    # Parse the dump list
    dumps = parse_st22_dump_list(list_snapshot)

    # If still on the initial screen (quick buttons didn't navigate), try parsing counts
    if not dumps:
        counts = parse_st22_initial_screen(list_snapshot)
        total_count = counts.get("today", 0) if target_date is None else 0
        if total_count > 0:
            logger.warning(
                "ST22 initial screen shows %d dumps but could not navigate to list",
                total_count,
            )

    # Sort dumps by time descending (newest first). Keep a mapping from
    # sorted position to original UI row index for correct DOM row selection.
    indexed_dumps = [(d.index, d) for d in dumps]  # (ui_row_idx, dump)
    indexed_dumps.sort(key=lambda pair: pair[1].time, reverse=True)
    sorted_to_ui: dict[int, int] = {}
    dumps = []
    for new_idx, (orig_ui_idx, dump) in enumerate(indexed_dumps):
        dump.index = new_idx
        sorted_to_ui[new_idx] = orig_ui_idx
        dumps.append(dump)

    # If no dump_index requested, return the list
    if dump_index is None:
        return ST22DumpListResult(
            dumps=dumps,
            dump_count=len(dumps),
            date_searched=date_str,
            retrieved_at=now,
        )

    # Select specific dump for detail view
    if not dumps:
        return ST22DumpDetailResult.failure(
            error="No dumps found to select from",
            detail=None,
            retrieved_at=now,
        )

    # Bounds check
    if dump_index < 0 or dump_index >= len(dumps):
        return ST22DumpDetailResult.failure(
            error=f"dump_index {dump_index} out of range (0..{len(dumps) - 1})",
            detail=None,
            retrieved_at=now,
        )

    target_dump = dumps[dump_index]

    # Use the original UI row position for clicking, not the sorted index
    ui_row_idx = sorted_to_ui[dump_index]
    error = await _select_dump_by_index(backend, ui_row_idx, len(dumps))
    if error:
        return ST22DumpDetailResult.failure(
            error=error,
            detail=None,
            retrieved_at=now,
        )

    # Capture detail by scrolling through pages
    detail_snapshot = await _capture_full_detail(backend)

    # Parse the detail
    detail = parse_st22_dump_detail(AriaSnapshot(detail_snapshot))

    # Enrich detail with data from the list entry
    detail.short_text = target_dump.short_text
    if not detail.program:
        detail.program = target_dump.program
    if not detail.error_type:
        detail.error_type = target_dump.error_type

    return ST22DumpDetailResult(
        detail=detail,
        retrieved_at=now,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_st22_tools(mcp: FastMCP) -> None:
    """Register ST22 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Look up ABAP short dumps (runtime errors) from ST22. "
            "If sap-adt is available, prefer its list_short_dumps/get_short_dump_details tools. "
            "USE THIS instead of sap_transaction('ST22') - faster and returns structured data. "
            "Two-step workflow: call once without dump_index to list dumps, "
            "then call again with dump_index=N to read a specific dump's detail. "
            "By default lists today's dumps. Use date parameter for other dates."
        ),
    )
    async def sap_st22_lookup(  # pylint: disable=redefined-outer-name
        date: str | None = None,
        dump_index: int | None = None,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ST22DumpListResult | ST22DumpDetailResult:
        """
        Look up short dumps from ST22.

        Args:
            date: Date to search (YYYY-MM-DD). Default: today.
                  Uses Today/Yesterday toolbar buttons when applicable.
            dump_index: Select the Nth dump from the list (0-based) to read detail.
                        If None, returns the dump list only.
            output_file: If provided, write results to this JSON file (on success only).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ST22DumpListResult (when dump_index is None) with list of dumps, or
            ST22DumpDetailResult (when dump_index is set) with full dump details
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_st22_lookup")
        except ValueError as e:
            now = datetime.now(UTC)
            error_msg = f"Session error: {e}"
            if dump_index is not None:
                return ST22DumpDetailResult.failure(error=error_msg, detail=None, retrieved_at=now)
            return ST22DumpListResult.failure(
                error=error_msg,
                dumps=[],
                dump_count=0,
                date_searched=date or "",
                retrieved_at=now,
            )

        try:
            result = await _st22_lookup(backend, date, dump_index)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("ST22 lookup failed")
            now = datetime.now(UTC)
            error_msg = f"ST22 lookup failed: {e}"
            if dump_index is not None:
                return ST22DumpDetailResult.failure(error=error_msg, detail=None, retrieved_at=now)
            return ST22DumpListResult.failure(
                error=error_msg,
                dumps=[],
                dump_count=0,
                date_searched=date or "",
                retrieved_at=now,
            )

        # Write to file if requested (only on success)
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        return result
