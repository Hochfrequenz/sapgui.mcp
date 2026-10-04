# pylint: disable=too-many-lines
"""
SE16 (Data Browser) query tool for SAP table data.

This module provides a tool to query SAP table data via SE16N transaction,
returning structured row data with automatic pagination for large result sets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.se16_parser import parse_se16_columns, parse_se16_hit_count, parse_se16_rows
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import SE16_NO_ENTRIES_DE, SE16_NO_ENTRIES_EN
from sapguimcp.models import SE16FileSummary, SE16Result, SE16Row, TableData
from sapguimcp.tools.se11_tools import _lookup_object_on_initial_screen
from sapguimcp.utils import resolve_output_file_path, write_json_output_file

if TYPE_CHECKING:
    from collections.abc import Callable

    from sapguimcp.backend.desktop import DesktopBackend
    from sapguimcp.backend.webgui.backend import WebGuiBackend


logger = logging.getLogger(__name__)

__all__ = ["register_se16_tools"]


# =============================================================================
# Constants
# =============================================================================

# Default maximum rows to return
DEFAULT_MAX_HITS = 100

# Rows per page (approximate, based on ALV grid lazy loading)
ROWS_PER_PAGE = 13

# Wait time between pages
PAGE_WAIT_TIME = timedelta(seconds=1)

# Maximum pages to traverse (supports SE16N's 9999 row limit at ~13 rows/page)
MAX_PAGES = 800


# =============================================================================
# SE11 Field Order Helper
# =============================================================================


async def _get_field_order_from_se11(backend: WebGuiBackend | DesktopBackend, table: str) -> dict[str, int] | None:
    """
    Get field order from SE11 for a table.

    Returns a dict mapping field name (uppercase) to 0-based row index,
    or None if SE11 lookup fails.

    The order in SE11 matches the row order in SE16N's selection criteria grid.
    """
    try:
        # Navigate to SE11 with clean state
        await backend.enter_transaction("/n")
        await backend.wait_for_ready()
        tx_result = await backend.enter_transaction("SE11")
        if not tx_result.success:
            return None
        await backend.wait_for_ready()

        result = await _lookup_object_on_initial_screen(backend, table, "table")

        # Press F3 (Back) to exit SE11 and return to clean state
        # This prevents state issues when navigating to SE16N next
        await backend.press_key("F3")
        await backend.wait_for_ready()

        # Check if we got an SE11Entry (success) vs SE11Error
        if hasattr(result, "fields") and result.fields:
            # Build mapping: field_name -> row_index
            field_order: dict[str, int] = {}
            for idx, field in enumerate(result.fields):
                field_order[field.name.upper()] = idx
            logger.info("Got field order from SE11", extra={"table": table, "fields": len(field_order)})
            return field_order

        logger.warning("SE11 lookup returned no fields", extra={"table": table})
        return None

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("SE11 lookup failed", extra={"table": table, "error": str(e)})
        return None


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


async def _fill_se16n_table_name(backend: WebGuiBackend | DesktopBackend, table: str) -> str | None:
    """
    Fill SE16N table name field.

    Tries English labels first, then German.

    Returns:
        Error message if failed, None if successful.
    """
    # Try English label first
    try:
        await backend.fill_field("Table", table.upper())
        return None
    except ValueError:  # pylint: disable=broad-exception-caught
        pass

    # Try German label
    try:
        await backend.fill_field("Tabelle", table.upper())
        return None
    except ValueError:  # pylint: disable=broad-exception-caught
        pass

    # Fallback: fill main form input, skipping toolbar/combobox inputs.
    if await backend.fill_main_input(table.upper(), ["Table", "Tabelle"]):
        return None

    return "Failed to set table name field. Field not found with labels 'Table' or 'Tabelle'."


async def _type_table_name_with_validation(backend: WebGuiBackend | DesktopBackend, table: str) -> str | None:
    """
    Type table name in SE16N and trigger validation with Enter.

    This approach mimics user behavior to trigger SAP's table validation
    round-trip, which populates the selection criteria grid.

    Returns:
        Error message if failed, None if successful.
    """
    for textbox_name in ["Table", "Tabelle"]:
        try:
            if await backend.focus_and_type(textbox_name, table.upper(), delay_ms=50):
                logger.info("Typed table name", extra={"table": table, "field": textbox_name})
                logger.info("Pressing Enter to trigger table validation")
                await backend.press_key("Enter")
                return None
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Typing in table field", extra={"field": textbox_name, "error": str(e)})

    # Fallback to fill_field approach
    if fill_error := await _fill_se16n_table_name(backend, table):
        return fill_error
    logger.warning("Used fallback fill_field for table name")
    await backend.press_key("Enter")
    return None


async def _wait_for_grid_rows(backend: WebGuiBackend, timeout_seconds: int = 5) -> bool:
    """
    Wait for SE16N selection criteria grid to populate with data rows.

    Returns:
        True if grid has rows, False if timeout.
    """
    for i in range(timeout_seconds * 2):  # Poll every 500ms
        result = await backend.evaluate_javascript("""
            () => {
                const grids = document.querySelectorAll('[role="grid"]');
                for (const grid of grids) {
                    const rows = grid.querySelectorAll('[role="row"]');
                    for (const row of rows) {
                        if (row.querySelector('[role="columnheader"]')) continue;
                        const text = row.textContent?.trim() || '';
                        if (text && !text.match(/^(Leer\\s*)+$/)) {
                            return true;
                        }
                    }
                }
                return false;
            }
        """)
        if result:
            logger.info("Table structure loaded", extra={"poll_iteration": i})
            return True
        await backend.wait(500)

    logger.warning("Grid not populated after polling", extra={"timeout_seconds": timeout_seconds})
    return False


async def _fill_se16n_max_hits(backend: WebGuiBackend | DesktopBackend, max_hits: int) -> None:
    """
    Fill SE16N max hits field.

    Tries English labels first, then German. Ignores errors since
    the field has a default value.
    """
    # Try English label first
    try:
        await backend.fill_field("Max. Number of Hits", str(max_hits))
        return
    except ValueError:  # pylint: disable=broad-exception-caught
        pass

    # Try German label
    try:
        await backend.fill_field("Maximale Trefferzahl", str(max_hits))
    except ValueError:  # pylint: disable=broad-exception-caught
        pass


async def _fill_filter_by_locator(
    backend: WebGuiBackend, element_id: str | None, selector: str | None, value: str, field_name: str
) -> bool:
    """
    Fill a filter field using element-targeted input via protocol methods.

    Tries element ID first, then selector. Uses fill_element_by_locator()
    which clicks, clears, types slowly, and Tabs to blur.

    Returns:
        True if fill succeeded, False otherwise.
    """
    # Try by element ID first (use attribute selector for IDs with special chars)
    if element_id:
        try:
            if await backend.fill_element_by_locator(f'[id="{element_id}"]', value):
                logger.info("Filled filter via locator (id)", extra={"field": field_name, "value": value})
                return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Fill by ID failed", extra={"error": str(e)})

    # Try by CSS selector
    if selector:
        try:
            if await backend.fill_element_by_locator(selector, value):
                logger.info("Filled filter via locator (selector)", extra={"field": field_name, "value": value})
                return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Fill by selector failed", extra={"error": str(e)})

    return False


def _check_table_not_found(snapshot: str, table: str) -> str | None:
    """
    Check if snapshot indicates table not found error.

    Returns:
        Error message if table not found, None if table exists.
    """
    # Check for explicit "not found" error messages
    snapshot_lower = snapshot.lower()
    if "does not exist" in snapshot_lower or "existiert nicht" in snapshot_lower:
        return f"Table '{table}' not found in SAP"

    # No explicit error - will check columns after parsing
    return None


def _check_no_entries_found(snapshot: str) -> bool:
    """Check if snapshot contains 'no values found' message (empty but existing table)."""
    snapshot_lower = snapshot.lower()
    return SE16_NO_ENTRIES_DE in snapshot_lower or SE16_NO_ENTRIES_EN in snapshot_lower


def _check_selection_screen_columns(columns: list[str]) -> bool:
    """
    Check if parsed columns indicate we're still on the selection screen.

    SE16N selection screen has these column headers in the filter grid:
    - DE: Feldname, Option, Von-Wert, Bis-Wert, Mehr, Ausgabe, Technischer Name
    - EN: Field Name, Option, From-Value, To-Value, More, Output, Technical Name

    Returns:
        True if columns indicate selection screen, False otherwise.
    """
    # Selection screen column names (DE and EN)
    selection_columns_de = {"Feldname", "Von-Wert", "Bis-Wert", "Technischer Name"}
    selection_columns_en = {"Field Name", "From-Value", "To-Value", "Technical Name"}

    columns_set = set(columns)

    # If we see multiple selection-screen-only columns, we're on selection screen
    de_matches = len(columns_set & selection_columns_de)
    en_matches = len(columns_set & selection_columns_en)

    return de_matches >= 2 or en_matches >= 2


async def _focus_grid(backend: WebGuiBackend) -> None:
    """Focus the ALV grid for pagination (required for PageDown to work)."""
    try:
        await backend.click_element("[role='grid']")
        await backend.wait(500)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("Could not focus grid", extra={"error": str(e)})


async def _collect_rows_with_pagination(  # pylint: disable=too-many-locals
    backend: WebGuiBackend,
    total_hits: int,
    columns: list[str],
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """
    Collect all rows from SE16N results using pagination.

    Uses PageDown to scroll through lazy-loaded ALV grid, collecting
    rows from each page until all are collected or no new rows found.

    Args:
        backend: WebGuiBackend instance
        total_hits: Expected total rows (from "Number of Hits")
        columns: Column names for row parsing
        ctx: FastMCP context for progress reporting (optional)

    Returns:
        List of row dicts
    """
    all_rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()  # Track unique row keys to detect duplicates
    page_num = 0
    stuck_count = 0
    last_first_key: str | None = None
    # Deduplicate by first column only (typically the primary key). See issue #136.
    first_col = columns[0] if columns else None

    while len(all_rows) < total_hits and page_num < MAX_PAGES:
        # Get snapshot and parse rows
        snapshot = AriaSnapshot(await backend.get_snapshot())
        rows = parse_se16_rows(snapshot, columns)

        if not rows:
            logger.debug("No rows found on page", extra={"page": page_num})
            stuck_count += 1
            if stuck_count >= 3:
                logger.warning("No rows found for 3 consecutive pages, stopping")
                break
            await backend.wait(int(PAGE_WAIT_TIME.total_seconds() * 2000))
            continue

        stuck_count = 0

        # Get first row's key (first column value) for duplicate detection
        first_key = str(rows[0].get(first_col, "")) if rows and first_col else None

        # Detect if we're stuck on the same page
        if first_key == last_first_key:
            logger.debug("Same first key, likely at end", extra={"page": page_num})
            break

        last_first_key = first_key

        # Add new rows (skip duplicates by first column - see first_col above)
        new_count = 0
        for row in rows:
            if first_col:
                row_key = str(row.get(first_col, ""))
            else:
                # Fallback: empty key to avoid reintroducing column alignment issues.
                # This edge case shouldn't occur (columns validated earlier).
                row_key = ""
            if row_key not in seen_keys:
                seen_keys.add(row_key)
                all_rows.append(row)
                new_count += 1

        logger.debug(
            "Collected rows from page",
            extra={
                "page": page_num,
                "new_rows": new_count,
                "total_rows": len(all_rows),
                "total_hits": total_hits,
            },
        )

        # Report progress if context available
        if ctx:
            try:
                await ctx.report_progress(progress=len(all_rows), total=total_hits)
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # Progress reporting is optional, don't fail on errors

        # Check if we've collected all rows
        if len(all_rows) >= total_hits:
            logger.info("Collected all rows", extra={"count": len(all_rows)})
            break

        # PageDown to next page
        await backend.press_key("PageDown")
        await backend.wait(int(PAGE_WAIT_TIME.total_seconds() * 1000))
        page_num += 1

    return all_rows


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


@dataclass
class _FilterFillResult:
    """Outcome of filling the SE16N selection criteria grid on the desktop backend."""

    unapplied_fields: list[str] = dataclass_field(default_factory=list)  # requested names (as given) not in the grid
    other_errors: list[str] = dataclass_field(default_factory=list)  # non-field problems, e.g. grid not found
    offered_fields: list[str] = dataclass_field(default_factory=list)  # technical names seen in grid, deduped, ordered
    hint: str | None = None  # extra sentence for the failure message (Web GUI: the grid is only partly rendered)


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


def _find_and_set_filter_cell(
    raw_tc: Any, field_upper: str, value: str, visible: int, seen: list[str] | None = None
) -> bool:
    """Scan visible rows of an SE16N table control for a field and set its filter value.

    If ``seen`` is given, the (non-blank) field names read from the visible rows are appended to it,
    so a caller can report which fields SE16N offers when the field is not found.

    Returns True if the field was found and set, False otherwise.
    """
    for r in range(visible):
        try:
            fname_cell = raw_tc.GetCell(r, _SE16N_COL_FIELDNAME)
            text: str = fname_cell.Text
            if seen is not None and text.strip():
                seen.append(text.strip())
            if text.upper() == field_upper:
                raw_tc.GetCell(r, _SE16N_COL_LOW).Text = value
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return False


@dataclass
class _GridRow:
    """One row of the SE16N selection-criteria grid as read from the Web GUI DOM."""

    row_index: int
    label: str
    field_name: str | None  # upper-case technical name; None when the column is not in the DOM
    fillable: bool  # the From-Value cell is an input (SE16N offers the field for selection)
    element_id: str | None
    selector: str | None


@dataclass
class _FilterPlan:
    """Which grid row each requested filter goes into, plus the filters that cannot be placed."""

    targets: list[tuple[str, str, _GridRow]] = dataclass_field(default_factory=list)  # (requested, value, row)
    result: _FilterFillResult = dataclass_field(default_factory=_FilterFillResult)


def _plan_se16n_filters(
    rows: list[_GridRow],
    filters: dict[str, str],
    field_order: dict[str, int] | None,
    table: str,
    possibly_truncated: bool = False,
) -> _FilterPlan:
    """Decide which selection row each filter belongs to, without trusting positions blindly.

    SE16N does not offer every SE11 field as a selection field, so SE11 positions can be shifted
    against the grid (#924). Therefore:

    * when every row shows its technical name, filters are matched **by name**, and the offered
      fields come from the grid;
    * when the technical names are not in the DOM, the SE11 order is used only if the grid has
      exactly as many rows as SE11 has fields; any other count means a field was left out,
      positions cannot be trusted, and nothing is filled.

    The Web GUI renders only the first rows of the grid (about 30) and the grid is not scrolled, so a
    field further down the table is not among ``rows``. When the grid has no empty padding row left
    (``possibly_truncated``) or SE11 lists more fields than the grid shows, the failure says so (``hint``).
    """
    plan = _FilterPlan()
    result = plan.result
    if not rows:
        result.other_errors.append("SE16N selection criteria grid has no rows")
        return plan

    if possibly_truncated or (field_order and len(field_order) > len(rows)):
        result.hint = (
            f"SAP Web GUI renders only the first rows of the grid ({len(rows)} here) and does not scroll it, "
            f"so a field further down table {table} cannot be reached."
        )

    if all(row.field_name for row in rows):
        by_name = {str(row.field_name): row for row in rows if row.fillable}
        result.offered_fields = _dedupe_keep_order([str(row.field_name) for row in rows if row.fillable])
        for name, value in filters.items():
            row = by_name.get(name.upper())
            if row is None:
                result.unapplied_fields.append(name)
            else:
                plan.targets.append((name, value, row))
        return plan

    # Technical names are not readable from the DOM: fall back to the SE11 order, but only if it provably fits.
    if not field_order:
        result.other_errors.append(
            "SE16N does not show technical field names in the page and the SE11 field list is unavailable, "
            "so the filter row cannot be verified"
        )
        return plan
    if len(rows) != len(field_order):
        result.other_errors.append(
            f"SE16N offers {len(rows)} selection rows for table {table} but SE11 lists {len(field_order)} fields; "
            "row positions may not match field names, so no filter was applied"
        )
        return plan
    by_index = {row.row_index: row for row in rows}
    result.offered_fields = list(field_order)
    for name, value in filters.items():
        position = field_order.get(name.upper())
        row = by_index.get(position) if position is not None else None
        if row is None or not row.fillable:
            result.unapplied_fields.append(name)
        else:
            plan.targets.append((name, value, row))
    return plan


def _parse_grid_rows(raw_rows: Any) -> list[_GridRow]:
    """Convert the rows returned by ``read_se16n_selection_rows.js`` into ``_GridRow`` objects.

    The grid is padded with empty rows (no label, no name, no input); those are not fields and are dropped.
    """
    rows: list[_GridRow] = []
    for raw in raw_rows or []:
        label = str(raw.get("label") or "")
        field_name = str(raw["fieldName"]).upper() if raw.get("fieldName") else None
        fillable = bool(raw.get("fillable"))
        if not (label or field_name or fillable):
            continue
        rows.append(
            _GridRow(
                row_index=int(raw["rowIndex"]),
                label=label,
                field_name=field_name,
                fillable=fillable,
                element_id=raw.get("elementId"),
                selector=raw.get("selector"),
            )
        )
    return rows


async def _fill_se16n_filters_webgui(
    backend: WebGuiBackend, table: str, filters: dict[str, str], field_order: dict[str, int] | None
) -> _FilterFillResult:
    """Fill the SE16N selection criteria on the Web GUI backend, placing each filter by field name.

    Reads the grid rows (index, technical name, input element) from the DOM, plans which row each
    filter goes into (:func:`_plan_se16n_filters`), then fills those inputs through the protocol's
    ``fill_element_by_locator`` (click + type, which triggers the proper SAP events).

    Filters that cannot be placed, and fills that fail, are reported in the result; the caller must
    not run the query when the result is not clean.
    """
    read_js = backend.load_js("read_se16n_selection_rows.js")
    grid = await backend.evaluate_javascript(read_js, {})
    if not grid.get("success"):
        return _FilterFillResult(other_errors=[str(grid.get("error", "Could not read the SE16N selection grid"))])

    plan = _plan_se16n_filters(
        _parse_grid_rows(grid.get("rows")),
        filters,
        field_order,
        table,
        possibly_truncated=not grid.get("hasPaddingRows"),
    )
    result = plan.result
    for name, value, row in plan.targets:
        if not await _fill_filter_by_locator(backend, row.element_id, row.selector, value, name):
            result.other_errors.append(f"Found the selection row for {name} but filling it failed")
    return result


async def _fill_se16n_filters_desktop(
    backend: WebGuiBackend | DesktopBackend,
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
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return _FilterFillResult(
            other_errors=[f"Filter filling requires DesktopBackend (got {type(backend).__name__})"]
        )

    session = backend.require_session()
    com = backend.com

    def _apply_filters() -> _FilterFillResult:
        result = _FilterFillResult()
        tc = None
        for tc_id in _SE16N_TC_IDS:
            try:
                tc = session.find_by_id(tc_id)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        if tc is None:
            result.other_errors.append("SE16N selection criteria table control not found")
            return result
        # Unwrap Python wrapper to get the raw COM dispatch object
        raw: Any = getattr(tc, "com", getattr(tc, "_com", tc))

        row_count: int = raw.RowCount
        visible: int = raw.VisibleRowCount
        logger.debug("SE16N selection grid", extra={"row_count": row_count, "visible": visible})

        offered: list[str] = []
        for field_name, value in filters.items():
            field_upper = field_name.upper()
            seen: list[str] = []

            # Try visible rows first
            if _find_and_set_filter_cell(raw, field_upper, value, visible, seen):
                logger.info("SE16N desktop filter set", extra={"field_name": field_upper, "value": value})
                continue

            # Field not in visible range - scroll through the table (unless everything is visible already)
            if row_count > visible and _set_filter_with_scrolling(raw, field_upper, value, visible, seen):
                continue

            result.unapplied_fields.append(field_name)
            offered.extend(seen)

        result.offered_fields = _dedupe_keep_order(offered)
        return result

    return await com.run(_apply_filters)


def _set_filter_with_scrolling(
    raw_tc: Any, field_upper: str, value: str, visible: int, seen: list[str] | None = None
) -> bool:
    """Scroll through an SE16N table control to find and set a filter value.

    Field names read while scrolling are appended to ``seen`` (may contain duplicates from overlapping windows).
    """
    scroll_max = raw_tc.VerticalScrollbar.Maximum
    found = False
    for scroll_pos in range(1, scroll_max + 1):
        try:
            raw_tc.VerticalScrollbar.Position = scroll_pos
        except Exception:  # pylint: disable=broad-exception-caught
            break
        if _find_and_set_filter_cell(raw_tc, field_upper, value, visible, seen):
            logger.info(
                "SE16N desktop filter set (scrolled)",
                extra={"field_name": field_upper, "value": value, "scroll": scroll_pos},
            )
            found = True
            break
    # Scroll back to top
    try:
        raw_tc.VerticalScrollbar.Position = 0
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return found


# Status bar fragments meaning "query ran, nothing found" (lower case, DE + EN)
_SE16N_NO_ENTRIES_KEYWORDS = ("keine werte", "no values", "keine einträge", "no entries")


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


def _se16n_result_displayed(before_status: str) -> Callable[[Any], bool]:
    """Build a predicate: True once F8 produced a result grid, a popup, or a status bar text that is new.

    ``before_status`` is the status bar text read right before F8; text identical to it predates the keypress
    and is ignored. Language-independent: error and "no entries" messages both carry status bar text; the
    caller's checks classify the outcome.
    """

    def _predicate(session: Any) -> bool:
        if session.find_by_id("wnd[0]/shellcont/shell", raise_error=False) is not None:
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
    backend: WebGuiBackend | DesktopBackend,
    table: str,
    filters: dict[str, str] | None,
    max_hits: int,
    now: datetime,
    ctx: Context | None = None,  # TODO: progress reporting via ctx not yet implemented on desktop
) -> SE16Result:
    """Desktop-specific SE16N query using read_table instead of ARIA parsing."""
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    # Always empty today (filter failures return early); kept for the status-bar error pass-through below.
    filter_warnings: list[str] = []

    # Navigate to SE16N
    tx = await backend.enter_transaction("SE16N")
    if not tx.success:
        return _empty_failure(f"Failed to navigate to SE16N: {tx.error}", table, now)

    await backend.wait_for_ready()
    if isinstance(backend, DesktopBackend):  # always true on this desktop-only path; narrows the type
        await backend.wait_for_condition(_se16n_initial_screen_ready)

    # Fill table name using focus_and_type (field name is GD-TAB in SE16N)
    screen = await backend.get_screen_info()
    logger.debug(
        "se16_desktop_fill", extra={"screen": screen.title, "tcode": screen.transaction, "program": screen.program}
    )

    filled = False
    for field_label in ["GD-TAB", "Table", "Tabelle"]:
        try:
            result_fill = await backend.focus_and_type(field_label, table.upper(), delay_ms=50)
            logger.debug("se16_desktop_focus_result", extra={"field": field_label, "result": result_fill})
            if result_fill:
                filled = True
                break
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    if not filled:
        # Last resort: try fill_field
        try:
            await backend.fill_field("Table", table.upper())
            filled = True
        except ValueError:
            pass
        if not filled:
            try:
                await backend.fill_field("Tabelle", table.upper())
                filled = True
            except ValueError:
                pass

    if not filled:
        return _empty_failure(f"Could not fill table name field for '{table}'", table, now)

    # Filters: press Enter to validate table and load selection criteria grid,
    # then fill filter values via the table control's cell manipulation.
    if filters:
        before_enter = (await backend.get_status_bar()).message.strip()
        await backend.press_key("Enter")
        await backend.wait_for_ready()
        if isinstance(backend, DesktopBackend):
            await backend.wait_for_condition(_se16n_selection_grid_loaded(before_enter))
        fill = await _fill_se16n_filters_desktop(backend, filters)
        if fill.unapplied_fields or fill.other_errors:
            logger.warning(
                "Desktop filters could not be applied, not running the query",
                extra={"unapplied": fill.unapplied_fields, "errors": fill.other_errors},
            )
            return _filter_fill_failure(fill, table, now)

    # Set max hits (best effort)
    for max_label in ["GD-MAX_LINES", "Max. Number of Hits", "Maximale Trefferzahl"]:
        try:
            if await backend.focus_and_type(max_label, str(max_hits), delay_ms=50):
                break
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # Execute (F8); snapshot the status bar first so a message from before the keypress is not mistaken for the result
    before_f8 = (await backend.get_status_bar()).message.strip()
    await backend.press_key("F8")
    await backend.wait_for_ready()
    if isinstance(backend, DesktopBackend):
        await backend.wait_for_condition(_se16n_result_displayed(before_f8))

    # Check for errors in status bar
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return _empty_failure(f"SE16N error: {sbar.message}", table, now, filter_warnings=filter_warnings)

    # Check for "no entries found"
    if sbar.message and any(msg in sbar.message.lower() for msg in _SE16N_NO_ENTRIES_KEYWORDS):
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
        if any(kw in title.lower() for kw in ["treffer", "hits", "entries"]):
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
    backend: WebGuiBackend | DesktopBackend,
    table: str,
    filters: dict[str, str] | None,
    max_hits: int,
    ctx: Context | None = None,
) -> SE16Result:
    """
    Execute SE16N query and collect results.

    Args:
        backend: WebGuiBackend | DesktopBackend instance
        table: Table name to query
        filters: Optional filter dict {field_name: value}
        max_hits: Maximum rows to return
        ctx: FastMCP context for progress reporting

    Returns:
        SE16Result with collected data
    """
    now = datetime.now(UTC)
    filter_warnings: list[str] = []

    # Desktop backend: use read_table instead of ARIA snapshot parsing
    if backend.backend_type == "desktop":
        return await _execute_se16_query_desktop(backend, table, filters, max_hits, now, ctx)

    from sapguimcp.backend.webgui.backend import WebGuiBackend as _WG  # pylint: disable=import-outside-toplevel

    assert isinstance(backend, _WG)

    # If filters are provided, get field order from SE11 FIRST
    # (before navigating to SE16N, since SE11 lookup changes the screen).
    # It is only used when SE16N's grid does not show technical field names, and then only if
    # the row count matches (#924); otherwise filters are placed by the name read from the grid.
    field_order: dict[str, int] | None = None
    if filters:
        logger.info("Getting field order from SE11", extra={"table": table})
        field_order = await _get_field_order_from_se11(backend, table)
        if field_order is None:
            logger.warning("Could not get field order from SE11, filters may not work")

    # Navigate to SE16N
    tx_result = await backend.enter_transaction("SE16N")
    if not tx_result.success:
        return _empty_failure(f"Failed to navigate to SE16N: {tx_result.error}", table, now)

    await backend.wait(1000)  # Wait for SE16N screen to render

    # Fill table name - with validation trigger if filters are provided
    fill_error: str | None = None
    if filters:
        fill_error = await _type_table_name_with_validation(backend, table)
        if not fill_error:
            await _wait_for_grid_rows(backend, timeout_seconds=5)
            fill = await _fill_se16n_filters_webgui(backend, table, filters, field_order)
            if fill.unapplied_fields or fill.other_errors:
                logger.warning(
                    "WebGUI filters could not be applied, not running the query",
                    extra={"unapplied": fill.unapplied_fields, "errors": fill.other_errors},
                )
                return _filter_fill_failure(fill, table, now)
            # Re-fill table name after filter filling — filter input via
            # page.keyboard could have corrupted it (fixes #289, #290)
            refill_error = await _fill_se16n_table_name(backend, table)
            if refill_error:
                logger.warning("Could not re-fill table name after filters", extra={"error": refill_error})
    else:
        fill_error = await _fill_se16n_table_name(backend, table)

    if fill_error:
        return _empty_failure(fill_error, table, now)

    # Set max hits
    await _fill_se16n_max_hits(backend, max_hits)

    # Best-effort: click table name field to move focus out of filter grid
    # (focus in filter grid can interfere with F8).
    try:
        clicked = await backend.click_element("input[title*='Table'], input[aria-label*='Table']")
        if not clicked:
            await backend.click_element("input[title*='Tabelle'], input[aria-label*='Tabelle']")
        await backend.wait(200)
    except Exception:  # pylint: disable=broad-exception-caught
        pass  # Best effort - continue with F8

    # Execute query (F8) and wait for results
    logger.info("Executing query with F8")
    await backend.press_key("F8")
    await backend.wait(3000)

    # Get snapshot to check for errors and parse results
    snapshot = AriaSnapshot(await backend.get_snapshot())
    snapshot_str = str(snapshot)

    # Check for table not found errors
    if table_error := _check_table_not_found(snapshot_str, table):
        # Log first 500 chars of snapshot for debugging
        logger.warning("Check failed", extra={"snapshot_preview": snapshot_str[:500]})
        return _empty_failure(table_error, table, now)

    # Parse hit count and columns
    total_hits = parse_se16_hit_count(snapshot)
    columns = parse_se16_columns(snapshot)

    if not columns:
        return _empty_failure(
            "Could not parse column headers from SE16N results",
            table,
            now,
            total_hits=total_hits,
        )

    # Check if we're still on selection screen (parsed filter grid instead of results)
    if _check_selection_screen_columns(columns):
        # Distinguish empty table from non-existent table:
        # SAP shows "No values found" / "Keine Werte gefunden" for existing tables with no data
        if _check_no_entries_found(snapshot_str):
            logger.info("Table exists but has no entries", extra={"table": table})
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
        logger.info("Parsed selection screen columns, table likely doesn't exist", extra={"table": table})
        return _empty_failure(
            f"Table '{table}' not found in SAP (still on selection screen)",
            table,
            now,
        )

    # Handle empty results
    if total_hits == 0:
        return SE16Result(
            table=table,
            total_hits=0,
            returned_rows=0,
            truncated=False,
            columns=columns,
            rows=[],
            filter_warnings=filter_warnings,
            retrieved_at=now,
        )

    # Focus grid and collect all rows with pagination
    await _focus_grid(backend)
    rows = [SE16Row(data=row) for row in await _collect_rows_with_pagination(backend, total_hits, columns, ctx)]

    return SE16Result(
        table=table,
        total_hits=total_hits,
        returned_rows=len(rows),
        truncated=total_hits >= max_hits,
        columns=columns,
        rows=rows,
        filter_warnings=filter_warnings,
        retrieved_at=now,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


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
            "**Filters:** On the desktop backend, if a filter cannot be applied (e.g. the field is unknown "
            "or not offered by SE16N), the call fails before running the query; the error lists the "
            "SE16N selection fields when they could be read.\n\n"
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
            filters: Optional filter dict {field_name: value} - uses technical field names. On the desktop
                backend, a field that is unknown or not offered by SE16N makes the call fail.
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
