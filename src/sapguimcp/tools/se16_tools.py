# pylint: disable=too-many-lines
"""
SE16 (Data Browser) query tool for SAP table data.

This module provides a tool to query SAP table data via SE16N transaction,
returning structured row data with automatic pagination for large result sets.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from sapguimcp import lang
from sapguimcp.backend.desktop._com_thread import _get_com_error_code
from sapguimcp.backend.manager import get_backend
from sapguimcp.models import SE16FileSummary, SE16Result, SE16Row, TableData
from sapguimcp.tools.table_helpers import _get_raw_tc
from sapguimcp.utils import resolve_output_file_path, write_json_output_file

if TYPE_CHECKING:
    from collections.abc import Callable

    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.lang.schema import LanguagePack


logger = logging.getLogger(__name__)

__all__ = ["register_se16_tools"]


# =============================================================================
# Constants
# =============================================================================

# Default maximum rows to return
DEFAULT_MAX_HITS = 100

# =============================================================================
# SE16 Query Implementation
# =============================================================================


def _empty_failure(
    error: str,
    table: str,
    retrieved_at: datetime,
    total_hits: int = 0,
    columns: list[str] | None = None,
    filter_warnings: list[str] | None = None,
) -> SE16Result:
    """Create a failure SE16Result with empty rows."""
    return SE16Result.failure(
        error=error,
        table=table,
        total_hits=total_hits,
        returned_rows=0,
        truncated=False,
        columns=columns or [],
        rows=[],
        filter_warnings=filter_warnings or [],
        retrieved_at=retrieved_at,
    )


# SE16N selection criteria table control IDs — S/4 nests it in a subscreen, R/3 puts it directly in usr
_SE16N_TC_IDS = [
    "wnd[0]/usr/subTAB_SUB:SAPLSE16N:0121/tblSAPLSE16NSELFIELDS_TC",  # S/4
    "wnd[0]/usr/tblSAPLSE16NSELFIELDS_TC",  # R/3
]
# Column indices in the SE16N selection criteria table control
_SE16N_COL_FIELDNAME = 6  # GS_SELFIELDS-FIELDNAME (technical name)
_SE16N_COL_LOW = 2  # GS_SELFIELDS-LOW (Von-Wert / From-Value)
# Maximum number of offered SE16N selection fields named in a filter failure message
_SE16N_MAX_OFFERED_FIELDS = 50
# A grid window right after a scroll may be stale or half-refreshed: bounded re-reads, ~0.5 s in total
_SE16N_SETTLE_ATTEMPTS = 10
_SE16N_SETTLE_POLL_S = 0.05
# COM errors that a fresh read of the control can get past. Deliberately local, not _com_thread's retry set: the
# re-fetch retry must not change when that set does.
_SE16N_STALE_PROXY_COM_ERRORS = frozenset(
    {
        -2147417851,  # 0x80010105 RPC_E_SERVERFAULT: what a proxy fetched before a scroll raises
        -2147023179,  # 0x800706B5 RPC_S_UNKNOWN_IF
    }
)
_SE16N_BUSY_COM_ERRORS = frozenset(
    {
        -2147417846,  # 0x8001010A RPC_E_SERVERCALL_RETRYLATER
        -2147418111,  # 0x80010001 RPC_E_CALL_REJECTED
    }
)
_SE16N_RETRY_CODES = _SE16N_STALE_PROXY_COM_ERRORS | _SE16N_BUSY_COM_ERRORS
# DISP_E_EXCEPTION: what GetCell raises for a row beyond the data and for a cell that is not an input
_COM_DISP_E_EXCEPTION = -2147352567


@dataclass
class _FilterFillResult:
    """Outcome of filling the SE16N selection criteria grid on the desktop backend."""

    unapplied_fields: list[str] = dataclass_field(default_factory=list)  # requested names (as given) not in the grid
    other_errors: list[str] = dataclass_field(default_factory=list)  # non-field problems, e.g. grid not found
    offered_fields: list[str] = dataclass_field(default_factory=list)  # technical names seen in grid, deduped, ordered
    hint: str | None = None  # extra sentence for the failure message


def _dedupe_keep_order(names: list[str]) -> list[str]:
    """Remove duplicates from ``names`` while keeping first-seen order."""
    return list(dict.fromkeys(names))


def _format_offered_fields(offered: list[str]) -> str:
    """Join offered field names, capped at 50 with a '… (+N more)' suffix. Empty list -> empty string."""
    shown = ", ".join(offered[:_SE16N_MAX_OFFERED_FIELDS])
    extra = len(offered) - _SE16N_MAX_OFFERED_FIELDS
    if extra > 0:
        shown += f", … (+{extra} more)"
    return shown


def _filter_fill_failure(fill: _FilterFillResult, table: str, now: datetime) -> SE16Result:
    """Build the failure result for filters that could not be applied (the query is not run)."""
    warnings = [f"Field '{name}' not found in SE16N selection criteria" for name in fill.unapplied_fields]
    warnings.extend(fill.other_errors)
    if not fill.unapplied_fields:
        error = "Could not apply filters: " + "; ".join(fill.other_errors)
        if fill.hint:
            error += f" {fill.hint}"
        return _empty_failure(error, table, now, filter_warnings=warnings)

    names = ", ".join(f"'{name}'" for name in fill.unapplied_fields)
    error = f"Filter field(s) {names} not available as SE16N selection criteria for table {table}."
    offered = _format_offered_fields(fill.offered_fields)
    if offered:
        error += f" Offered fields: {offered}."
    error += (
        " A field can exist in the table without being an SE16N selection field; use sap-adt `run_query` if available."
    )
    if fill.hint:
        error += f" {fill.hint}"
    return _empty_failure(error, table, now, filter_warnings=warnings)


class _GridScanError(Exception):
    """Reading or scrolling the SE16N selection grid failed (a technical failure, not 'field not found')."""


def _resolve_se16n_tc_id(session: Any) -> str | None:
    """Return the ID of the SE16N selection grid that exists on this release, or None."""
    for tc_id in _SE16N_TC_IDS:
        try:
            session.find_by_id(tc_id)
            return tc_id
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return None


def _row_is_readable(get_tc: Callable[[], Any], row: int) -> bool:
    """True if the field name of a grid row can be read through a fresh control (confirms or refutes the data end)."""
    try:
        str(get_tc().GetCell(row, _SE16N_COL_FIELDNAME).Text)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if _get_com_error_code(exc) in (_COM_DISP_E_EXCEPTION, *_SE16N_RETRY_CODES):
            return False
        raise
    return True


def _read_window_names(get_tc: Callable[[], Any], count: int, settle: bool) -> list[str | None]:
    """Read the field names of the first ``count`` rows of the grid's current window.

    The control is re-fetched for every read. Right after a scroll the window may not be refreshed yet (#387 busy
    errors, #937 half-empty windows): with ``settle`` a window counts once two consecutive reads agree and it is not
    half-refreshed (first row filled, all other readable rows blank). Busy and stale-proxy errors are retried a
    bounded number of times; any other COM error is raised at once. The grid's ``RowCount`` can exceed its data
    rows: a row beyond the data raises ``DISP_E_EXCEPTION`` on ``GetCell`` and reads as ``None``. ``None`` is only
    accepted as a contiguous tail of the window; an unreadable row followed by a readable one is a scan error.
    """
    previous: list[str | None] | None = None
    last_exc: Exception | None = None
    for attempt in range(_SE16N_SETTLE_ATTEMPTS):
        if attempt:
            time.sleep(_SE16N_SETTLE_POLL_S)
        try:
            tc = get_tc()
            names: list[str | None] = []
            for row in range(count):
                try:
                    names.append(str(tc.GetCell(row, _SE16N_COL_FIELDNAME).Text).strip())
                except Exception as cell_exc:  # pylint: disable=broad-exception-caught
                    if _get_com_error_code(cell_exc) != _COM_DISP_E_EXCEPTION:
                        raise  # busy, stale or a lost connection: not a row beyond the data
                    names.append(None)  # beyond the data rows
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if _get_com_error_code(exc) not in _SE16N_RETRY_CODES:
                raise
            logger.warning("SE16N selection grid busy while reading", extra={"error": str(exc), "attempt": attempt})
            last_exc, previous = exc, None
            continue
        readable = [name for name in names if name is not None]
        if names[len(readable) :] != [None] * (len(names) - len(readable)):
            raise _GridScanError(f"a row inside the data cannot be read ({len(readable)} of {count} rows readable)")
        if len(readable) < count and _row_is_readable(get_tc, len(readable)):
            # DISP_E_EXCEPTION is SAP GUI's generic error: the tail was only transiently unreadable, read again
            logger.warning("SE16N selection grid tail readable on re-read", extra={"row": len(readable)})
            previous = None
            continue
        # A half-refreshed window (#937) reads blank below its first row; rows beyond the data are None, not blank
        half_empty = len(readable) > 1 and bool(readable[0]) and not any(readable[1:])
        if not settle or not names or not readable or (not half_empty and names == previous):
            return names
        previous = names
    raise _GridScanError(f"the window did not settle ({last_exc})" if last_exc else "the window did not settle")


def _set_filter_value(get_tc: Callable[[], Any], row: int, field_upper: str, value: str) -> bool:
    """Write the From-value of a grid row through a fresh control. False if the row verifiably takes no value.

    SE16N lists fields it does not offer for selection, too; their From-value cell is not changeable and a write
    raises ``DISP_E_EXCEPTION``. That error is SAP GUI's generic one, though, so it only counts as "not offered" when
    a fresh control reports the cell as not ``Changeable``. After any other failure the cell is read back (a write
    that raised may have landed), then written once more after a short sleep; a second failure, or an ambiguous
    one, is raised as a scan error. The read-back compares stripped and case-insensitive, as SE16N may upper-case or
    reformat a value; a value reformatted beyond that is written again, which is harmless.
    """
    last_exc: Exception | None = None
    for attempt in range(2):
        if attempt:
            time.sleep(_SE16N_SETTLE_POLL_S)
        try:
            get_tc().GetCell(row, _SE16N_COL_LOW).Text = value
            return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            last_exc = exc
            logger.warning(
                "SE16N value write failed", extra={"field_name": field_upper, "error": str(exc), "attempt": attempt}
            )
        try:
            cell = get_tc().GetCell(row, _SE16N_COL_LOW)
            if str(cell.Text).strip().casefold() == value.strip().casefold():
                return True  # the write raised but landed
            if _get_com_error_code(last_exc) == _COM_DISP_E_EXCEPTION and cell.Changeable is False:
                logger.warning("SE16N field row is not changeable", extra={"field_name": field_upper})
                return False
        except Exception as exc:  # pylint: disable=broad-exception-caught
            last_exc = exc
    raise _GridScanError(f"Setting the SE16N filter {field_upper} failed: {last_exc}")


def _fill_window(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    get_tc: Callable[[], Any],
    first_row: int,
    count: int,
    known_end: int,
    settle: bool,
    pending: list[tuple[str, str, str]],
    seen: list[str],
) -> tuple[list[tuple[str, str, str]], int]:
    """Set the filters of ``pending`` (requested name, upper-case name, value) whose field is in the current window.

    The window starts at grid row ``first_row``; rows below ``known_end`` were already read as data, so an unreadable
    one there is a scan error. The non-blank names read are appended to ``seen``. Returns the filters that are still
    pending and the new ``known_end``, which stays below ``first_row + count`` when the window reaches past the data.
    """
    raw_names = _read_window_names(get_tc, count, settle)
    names = [name or "" for name in raw_names]
    readable = sum(name is not None for name in raw_names)
    if first_row + readable < known_end:
        raise _GridScanError(f"row {first_row + readable} of the data cannot be read")
    seen.extend(name for name in names if name)
    upper_names = [name.upper() for name in names]
    still_pending = []
    for requested, field_upper, value in pending:
        if field_upper not in upper_names or not _set_filter_value(
            get_tc, upper_names.index(field_upper), field_upper, value
        ):
            still_pending.append((requested, field_upper, value))
            continue
        logger.info("SE16N desktop filter set", extra={"field_name": field_upper, "value": value})
    return still_pending, max(known_end, first_row + readable)


def _scroll_grid(get_tc: Callable[[], Any], position: int) -> int:
    """Set the scroll position and return the one the control reports afterwards (SAP may clamp or ignore it)."""
    try:
        get_tc().VerticalScrollbar.Position = position
        return int(get_tc().VerticalScrollbar.Position)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise _GridScanError(f"Scrolling the SE16N selection grid failed at position {position}: {exc}") from exc


def _scan_grid_for_filters(
    get_tc: Callable[[], Any],
    row_count: int,
    visible: int,
    known_end: int,
    pending: list[tuple[str, str, str]],
    seen: list[str],
) -> list[tuple[str, str, str]]:
    """Walk the grid one window (page) at a time, setting the pending filters; returns those never found.

    Every window is read through a freshly fetched control: the proxy that was valid before a scroll is dead after it.
    ``known_end`` is the number of leading rows already read as data.
    """
    maximum = _scrollbar_value(get_tc, "Maximum")
    if maximum <= 0:
        raise _GridScanError(
            f"the SE16N selection grid reports no scroll range (Maximum {maximum}) for {row_count} rows, "
            f"{visible} visible"
        )
    position = 0
    while pending and position < maximum:
        target = min(position + visible, maximum)
        actual = _scroll_grid(get_tc, target)
        if actual <= position:
            raise _GridScanError(f"Scrolling the SE16N selection grid failed at position {target}: stayed at {actual}")
        position = actual
        count = min(visible, row_count - position)
        try:
            pending, known_end = _fill_window(get_tc, position, count, known_end, True, pending, seen)
        except _GridScanError:
            raise
        except Exception as exc:  # pylint: disable=broad-exception-caught
            raise _GridScanError(f"Reading the SE16N selection grid failed at position {position}: {exc}") from exc
        if known_end < position + count:  # RowCount can exceed the data rows: the rest of the grid is empty
            break
    return pending


def _scrollbar_value(get_tc: Callable[[], Any], name: str) -> int:
    """Read ``VerticalScrollbar.<name>`` of the grid through a fresh control; a failure is a scan error."""
    try:
        return int(getattr(get_tc().VerticalScrollbar, name))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise _GridScanError(f"Reading the SE16N selection grid scroll {name.lower()} failed: {exc}") from exc


def _reset_grid_to_top(get_tc: Callable[[], Any], result: _FilterFillResult) -> None:
    """Scroll the grid back to the top through a fresh control; a failure is logged and reported, never swallowed."""
    try:
        get_tc().VerticalScrollbar.Position = 0
        position = int(get_tc().VerticalScrollbar.Position)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Could not reset the SE16N selection grid", extra={"error": str(exc)})
        result.other_errors.append(f"Could not return the SE16N selection grid to the top: {exc}")
        return
    if position != 0:
        logger.warning("SE16N selection grid not at the top after reset", extra={"position": position})
        result.other_errors.append(f"Could not return the SE16N selection grid to the top (stayed at {position})")


async def _fill_se16n_filters_desktop(
    backend: DesktopBackend,
    filters: dict[str, str],
) -> _FilterFillResult:
    """Fill SE16N filter values via the selection criteria table control (COM).

    SE16N uses a GuiTableControl for its selection criteria grid.  Each row
    represents a table field; column 6 holds the technical field name and
    column 2 holds the "From-Value" (Von-Wert) filter input.

    The table control only exposes currently visible rows via ``GetCell``.
    If a field is beyond the visible range, the vertical scrollbar is
    repositioned to bring it into view.

    Fields that cannot be found are reported in ``unapplied_fields``; for them the names of all
    fields the grid offers are collected into ``offered_fields`` (successful fills cost nothing extra).
    """

    session = backend.require_session()
    com = backend.com

    def _apply_filters() -> _FilterFillResult:
        result = _FilterFillResult()
        tc_id = _resolve_se16n_tc_id(session)
        if tc_id is None:
            result.other_errors.append("SE16N selection criteria table control not found")
            return result

        def get_tc() -> Any:
            return _get_raw_tc(session, tc_id)

        raw = get_tc()
        row_count: int = raw.RowCount
        visible: int = raw.VisibleRowCount
        logger.debug("SE16N selection grid", extra={"row_count": row_count, "visible": visible})

        pending = [(name, name.upper(), value) for name, value in filters.items()]
        seen: list[str] = []
        scan_failed = False
        scrolled = False
        try:
            if (
                row_count > visible and _scrollbar_value(get_tc, "Position") != 0
            ):  # left over from an earlier failed call
                scrolled = True
                _scroll_grid(get_tc, 0)
            count = min(visible, row_count)
            try:
                pending, known_end = _fill_window(get_tc, 0, count, 0, scrolled, pending, seen)
            except _GridScanError:
                raise
            except Exception as exc:  # pylint: disable=broad-exception-caught
                raise _GridScanError(f"Reading the SE16N selection grid failed at position 0: {exc}") from exc
            if known_end == 0 and count:
                raise _GridScanError("Reading the SE16N selection grid failed at position 0: the first row is empty")
            # Field not in the visible rows - scroll through the grid (unless everything is visible already)
            if pending and row_count > visible:
                scrolled = True
                pending = _scan_grid_for_filters(get_tc, row_count, visible, known_end, pending, seen)
        except _GridScanError as exc:
            logger.warning("SE16N selection grid scan failed", extra={"error": str(exc)})
            result.other_errors.append(str(exc))
            scan_failed = True
        finally:
            if scrolled:
                _reset_grid_to_top(get_tc, result)

        # Only a complete scan may claim a field is not offered; after a technical failure that would be untrue.
        if not scan_failed:
            result.unapplied_fields = [requested for requested, _, _ in pending]
            if pending:
                result.offered_fields = _dedupe_keep_order(seen)
        return result

    return await com.run(_apply_filters)


# Status bar message (class, number) meaning "query ran, nothing found"; language-independent
_SE16N_NO_VALUES_MESSAGE = ("WUSL", "002")  # "No values found", same message ID on both releases


def _statusbar_is_new_error(session: Any, before_status: str) -> bool:
    """True if the main window's status bar shows an error whose text differs from the pre-keypress snapshot."""
    sbar = session.find_by_id("wnd[0]/sbar", raise_error=False)
    return sbar is not None and str(sbar.message_type) == "E" and str(sbar.text).strip() != before_status


def _se16n_initial_screen_ready(session: Any) -> bool:
    """True once the SE16N table-name field exists."""
    return any(session.find_by_id(f"wnd[0]/usr/{p}GD-TAB", raise_error=False) is not None for p in ("ctxt", "txt"))


def _se16n_selection_grid_loaded(before_status: str) -> Callable[[Any], bool]:
    """Build a predicate: True once the selection grid lists the fields of the entered table (or a new error shows).

    The grid already exists, with blank rows, before a table is validated, so presence alone is not enough:
    the first row's field name must be filled. An error only counts if its text differs from ``before_status``
    (the status bar text read right before Enter), so a stale error cannot end the wait early.
    """

    def _predicate(session: Any) -> bool:
        if _statusbar_is_new_error(session, before_status):
            return True
        for tc_id in _SE16N_TC_IDS:
            tc = session.find_by_id(tc_id, raise_error=False)
            if tc is not None:
                raw: Any = getattr(tc, "com", getattr(tc, "_com", tc))
                return bool(str(raw.GetCell(0, _SE16N_COL_FIELDNAME).Text).strip())
        return False

    return _predicate


# Where the ALV result grid sits depends on the release: directly in the window on one, inside the ``usr`` area's
# RESULT_LIST container on another. A predicate that only knew the first one waited the full timeout (10 s) for every
# result without a new status bar text.
_SE16N_RESULT_GRID_IDS = ("wnd[0]/shellcont/shell", "wnd[0]/usr/cntlRESULT_LIST/shellcont/shell")


def _se16n_result_displayed(before_status: str) -> Callable[[Any], bool]:
    """Build a predicate: True once F8 produced a result grid, a popup, or a status bar text that is new.

    ``before_status`` is the status bar text read right before F8; text identical to it predates the keypress
    and is ignored. Language-independent: error and "no entries" messages both carry status bar text; the
    caller's checks classify the outcome.
    """

    def _predicate(session: Any) -> bool:
        if any(session.find_by_id(grid_id, raise_error=False) is not None for grid_id in _SE16N_RESULT_GRID_IDS):
            return True
        if session.find_by_id("wnd[1]", raise_error=False) is not None:
            return True
        sbar = session.find_by_id("wnd[0]/sbar", raise_error=False)
        if sbar is None:
            return False
        text = str(sbar.text).strip()
        return bool(text) and text != before_status

    return _predicate


async def _execute_se16_query_desktop(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements,too-many-branches,too-many-statements,unused-argument
    backend: DesktopBackend,
    table: str,
    filters: dict[str, str] | None,
    max_hits: int,
    now: datetime,
    t: LanguagePack,
    ctx: Context | None = None,  # TODO: progress reporting via ctx not yet implemented on desktop
) -> SE16Result:
    """SE16N query using read_table."""
    # Always empty today (filter failures return early); kept for the status-bar error pass-through below.
    filter_warnings: list[str] = []

    # Navigate to SE16N
    tx = await backend.enter_transaction("SE16N")
    if not tx.success:
        return _empty_failure(f"Failed to navigate to SE16N: {tx.error}", table, now)

    await backend.wait_for_ready()
    await backend.wait_for_condition(_se16n_initial_screen_ready)

    # Fill table name using focus_and_type (field name is GD-TAB in SE16N)
    screen = await backend.get_screen_info()
    logger.debug(
        "se16_desktop_fill", extra={"screen": screen.title, "tcode": screen.transaction, "program": screen.program}
    )

    # The table name field is addressed by its technical name
    filled = False
    try:
        filled = bool(await backend.focus_and_type("GD-TAB", table.upper(), delay_ms=50))
        logger.debug("se16_desktop_focus_result", extra={"field": "GD-TAB", "result": filled})
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    if not filled:
        return _empty_failure(f"Could not fill table name field for '{table}'", table, now)

    # Filters: press Enter to validate table and load selection criteria grid,
    # then fill filter values via the table control's cell manipulation.
    if filters:
        before_enter = (await backend.get_status_bar()).message.strip()
        await backend.press_key("Enter")
        await backend.wait_for_ready()
        await backend.wait_for_condition(_se16n_selection_grid_loaded(before_enter))
        fill = await _fill_se16n_filters_desktop(backend, filters)
        if fill.unapplied_fields or fill.other_errors:
            logger.warning(
                "Desktop filters could not be applied, not running the query",
                extra={"unapplied": fill.unapplied_fields, "errors": fill.other_errors},
            )
            return _filter_fill_failure(fill, table, now)

    # Set max hits (best effort)
    try:
        await backend.focus_and_type("GD-MAX_LINES", str(max_hits), delay_ms=50)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Execute (F8); snapshot the status bar first so a message from before the keypress is not mistaken for the result
    before_f8 = (await backend.get_status_bar()).message.strip()
    await backend.press_key("F8")
    await backend.wait_for_ready()
    await backend.wait_for_condition(_se16n_result_displayed(before_f8))

    # Check for errors in status bar
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return _empty_failure(f"SE16N error: {sbar.message}", table, now, filter_warnings=filter_warnings)

    # Check for "no entries found"
    if (sbar.message_id, sbar.message_number) == _SE16N_NO_VALUES_MESSAGE or (
        sbar.message and t.common.no_entries.contains(sbar.message)
    ):
        return SE16Result(
            table=table,
            total_hits=0,
            returned_rows=0,
            truncated=False,
            columns=[],
            rows=[],
            filter_warnings=filter_warnings,
            retrieved_at=now,
        )

    # Read table data using read_table (searches full window including dock shells)
    table_data: TableData = await backend.read_table(start_row=1, max_rows=max_hits)

    if not table_data.headers:
        # Check title for hit count hint
        title = await backend.get_page_title()
        if t.se16.results_title.contains(title):
            return _empty_failure(
                "SE16N results displayed but could not read table (list report format?)",
                table,
                now,
            )
        return _empty_failure("Could not read SE16N results", table, now)

    # Convert to SE16Row format
    rows: list[SE16Row] = []
    for tr in table_data.rows:
        rows.append(SE16Row(data=tr.data))

    total_hits = table_data.total_rows or len(rows)

    return SE16Result(
        table=table,
        total_hits=total_hits,
        returned_rows=len(rows),
        truncated=len(rows) < total_hits,
        columns=table_data.headers,
        rows=rows,
        filter_warnings=filter_warnings,
        retrieved_at=now,
    )


async def _execute_se16_query(  # pylint: disable=too-many-locals,too-many-branches,too-many-return-statements,too-many-statements
    backend: DesktopBackend,
    table: str,
    filters: dict[str, str] | None,
    max_hits: int,
    ctx: Context | None = None,
) -> SE16Result:
    """
    Execute SE16N query and collect results.

    Args:
        backend: DesktopBackend instance
        table: Table name to query
        filters: Optional filter dict {field_name: value}
        max_hits: Maximum rows to return
        ctx: FastMCP context for progress reporting

    Returns:
        SE16Result with collected data
    """
    now = datetime.now(UTC)
    # Resolved once, outside every try: an UnsupportedLanguageError must reach the caller
    t = lang.current("sap_se16_query")

    return await _execute_se16_query_desktop(backend, table, filters, max_hits, now, t, ctx)


def register_se16_tools(mcp: FastMCP) -> None:
    """Register SE16 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            read_only_hint=True,
            open_world_hint=False,
        ),
        description=(
            "Query SAP table data via SE16N (Data Browser). "
            "If sap-adt is available, prefer its run_query tool for simple queries. "
            "USE THIS for complex queries with dynamic filtering or when ADT is unavailable.\n\n"
            "**Filters:** If a filter cannot be applied (e.g. the field is unknown or not offered by "
            "SE16N), the call fails before running the query; the error lists the SE16N selection "
            "fields when they could be read.\n\n"
            "**Performance:** ~7 rows/second due to pagination.\n"
            "- 100 rows: ~14 seconds\n"
            "- 500 rows: ~1.5 minutes\n"
            "- 1000 rows: ~2.5 minutes\n"
            "- 5000 rows: ~12 minutes\n\n"
            "For large results, use `output_file` to write JSON to disk and receive a summary."
        ),
    )
    async def sap_se16_query(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        ctx: Context,
        table: str,
        filters: dict[str, str] | None = None,
        max_hits: int = DEFAULT_MAX_HITS,
        output_file: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE16Result | SE16FileSummary:
        """
        Query SAP table data via SE16N.

        Args:
            ctx: FastMCP context (injected)
            table: Table name to query (e.g., "MARA", "T000", "TSTC")
            filters: Optional filter dict {field_name: value} - uses technical field names. A field that is
                unknown or not offered by SE16N makes the call fail.
            max_hits: Maximum rows to return (default 100)
            output_file: If provided, write full results to this JSON file within the
                configured output directory (OUTPUT_DIR, default: current working
                directory) and return summary
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE16Result with all rows (inline), or
            SE16FileSummary with file path and preview (when output_file provided)
        """
        if output_file:
            try:
                output_path = resolve_output_file_path(output_file)
            except ValueError as e:
                now = datetime.now(UTC)
                return SE16Result.failure(
                    error=str(e),
                    table=table,
                    total_hits=0,
                    returned_rows=0,
                    truncated=False,
                    columns=[],
                    rows=[],
                    retrieved_at=now,
                )
        else:
            output_path = None

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se16_query")
        except ValueError as e:
            now = datetime.now(UTC)
            return SE16Result.failure(
                error=f"Session error: {e}",
                table=table,
                total_hits=0,
                returned_rows=0,
                truncated=False,
                columns=[],
                rows=[],
                retrieved_at=now,
            )

        logger.info("Querying table", extra={"table": table, "max_hits": max_hits})

        result = await _execute_se16_query(backend, table, filters, max_hits, ctx)

        # Write to file if requested
        if output_file and output_path and result.success:
            try:
                output_path = write_json_output_file(output_file, result.model_dump(mode="json"))
            except (ValueError, OSError) as e:
                failure_payload = result.model_dump(mode="python")
                failure_payload["success"] = False
                failure_payload["error"] = str(e)
                return SE16Result(**failure_payload)

            return SE16FileSummary(
                success=True,
                output_file=str(output_path.absolute()),
                table=result.table,
                total_hits=result.total_hits,
                returned_rows=result.returned_rows,
                truncated=result.truncated,
                columns=result.columns,
                sample_rows=result.rows[:5],  # First 5 rows as preview
                filter_warnings=result.filter_warnings,
            )

        return result
