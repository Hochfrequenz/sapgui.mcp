# pylint: disable=too-many-lines
"""
SE16 (Data Browser) query tool for SAP table data.

This module provides a tool to query SAP table data via SE16N transaction,
returning structured row data with automatic pagination for large result sets.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from sapguimcp.backend.manager import get_backend
from sapguimcp.backend.webgui.parsers.se16_parser import parse_se16_columns, parse_se16_hit_count, parse_se16_rows
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.lang import SE16_NO_ENTRIES_DE, SE16_NO_ENTRIES_EN
from sapguimcp.models import SE16FileSummary, SE16Result, SE16Row, TableData
from sapguimcp.tools.se11_tools import _lookup_object_on_initial_screen

if TYPE_CHECKING:
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


async def _fill_filter_by_index(
    backend: WebGuiBackend, find_js: str, field_name: str, value: str, row_index: int
) -> str | None:
    """
    Fill a single filter field using index-based approach.

    Uses JS to find the element, then fills it via protocol methods.

    Returns:
        Error message if failed, None if successful.
    """
    # Find the element using JS
    result = await backend.evaluate_javascript(find_js, {"rowIndex": row_index, "fieldName": field_name})

    if not result.get("success"):
        error_msg = str(result.get("error", f"Could not find element for {field_name}"))
        debug_info = result.get("debug", {})
        logger.warning("Find element failed", extra={"error": error_msg, "debug": debug_info})
        return error_msg

    # Extract element info
    element_id = result.get("elementId")
    selector = result.get("selector")
    strategy = result.get("strategy", "unknown")
    element_type = result.get("elementType", "unknown")

    logger.info(
        "Found element",
        extra={
            "field": field_name,
            "row_index": row_index,
            "element_id": element_id,
            "element_type": element_type,
            "strategy": strategy,
        },
    )

    # Fill using locator-based approach
    if await _fill_filter_by_locator(backend, element_id, selector, value, field_name):
        return None

    return f"Found element for {field_name} but fill by locator failed"


async def _fill_se16n_filters(  # pylint: disable=too-many-locals
    backend: WebGuiBackend, filters: dict[str, str] | None, field_order: dict[str, int] | None
) -> list[str]:
    """
    Fill filter values in SE16N selection criteria grid using row indices.

    Uses SE11 field order mapping to find the correct row index for each field,
    avoiding the need to search for field names in the DOM (which fails due to
    SAP Web GUI's lazy column rendering).

    Uses a two-step approach:
    1. JavaScript finds the target element's ID/selector
    2. Protocol's fill_element_by_locator clicks + types the value (triggers proper SAP events)

    Args:
        backend: WebGuiBackend instance
        filters: Dict of {field_name: value} to filter on.
                 Field names should be technical names (e.g., "TCODE", "PGMNA").
        field_order: Dict mapping field names to row indices from SE11.
                     If None, falls back to name-based search (may fail).

    Returns:
        List of error messages (empty if all filters applied successfully).
    """
    if not filters:
        return []

    errors: list[str] = []

    find_js = backend.load_js("find_se16_filter_input.js") if field_order else None
    fill_js = backend.load_js("fill_se16_filter.js") if not field_order else None

    if not field_order:
        logger.warning("No field order available, falling back to name-based filter search")

    for field_name, value in filters.items():
        field_upper = field_name.upper()

        try:
            if field_order and find_js:
                # Check if field exists in table
                if field_upper not in field_order:
                    available = list(field_order.keys())[:10]
                    errors.append(f"Field '{field_name}' not found in table (available: {available})")
                    continue

                # Fill using index-based approach
                error = await _fill_filter_by_index(backend, find_js, field_upper, value, field_order[field_upper])
                if error:
                    errors.append(error)

            elif fill_js:
                # Fall back to name-based JavaScript approach
                result = await backend.evaluate_javascript(fill_js, {"fieldName": field_upper, "value": value})

                if not result.get("success"):
                    error_msg = result.get("error", f"Unknown error for field {field_name}")
                    errors.append(error_msg)
                    logger.warning("Filter error (name-based)", extra={"error": error_msg})
                else:
                    logger.info("Applied filter via JS (name-based)", extra={"field": field_name, "value": value})

        except Exception as e:  # pylint: disable=broad-exception-caught
            errors.append(f"Failed to apply filter {field_name}={value}: {e}")
            logger.warning("Filter exception", extra={"field": field_name, "error": str(e)})

    return errors


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


def _find_and_set_filter_cell(raw_tc: Any, field_upper: str, value: str, visible: int) -> bool:
    """Scan visible rows of an SE16N table control for a field and set its filter value.

    Returns True if the field was found and set, False otherwise.
    """
    for r in range(visible):
        try:
            fname_cell = raw_tc.GetCell(r, _SE16N_COL_FIELDNAME)
            if fname_cell.Text.upper() == field_upper:
                raw_tc.GetCell(r, _SE16N_COL_LOW).Text = value
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return False


async def _fill_se16n_filters_desktop(
    backend: WebGuiBackend | DesktopBackend,
    filters: dict[str, str],
) -> list[str]:
    """Fill SE16N filter values via the selection criteria table control (COM).

    SE16N uses a GuiTableControl for its selection criteria grid.  Each row
    represents a table field; column 6 holds the technical field name and
    column 2 holds the "From-Value" (Von-Wert) filter input.

    The table control only exposes currently visible rows via ``GetCell``.
    If a field is beyond the visible range, the vertical scrollbar is
    repositioned to bring it into view.
    """
    from sapguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return [f"Filter filling requires DesktopBackend (got {type(backend).__name__})"]

    session = backend.require_session()
    com = backend.com

    def _apply_filters() -> list[str]:
        errors: list[str] = []
        tc = None
        for tc_id in _SE16N_TC_IDS:
            try:
                tc = session.find_by_id(tc_id)
                break
            except Exception:  # pylint: disable=broad-exception-caught
                continue
        if tc is None:
            return ["SE16N selection criteria table control not found"]
        # Unwrap Python wrapper to get the raw COM dispatch object
        raw: Any = getattr(tc, "com", getattr(tc, "_com", tc))

        row_count: int = raw.RowCount
        visible: int = raw.VisibleRowCount
        logger.debug("SE16N selection grid", extra={"row_count": row_count, "visible": visible})

        for field_name, value in filters.items():
            field_upper = field_name.upper()

            # Try visible rows first
            if _find_and_set_filter_cell(raw, field_upper, value, visible):
                logger.info("SE16N desktop filter set", extra={"field_name": field_upper, "value": value})
                continue

            # Field not in visible range — scroll through the table
            if row_count <= visible:
                errors.append(f"Field '{field_name}' not found in SE16N selection criteria")
                continue

            found = _set_filter_with_scrolling(raw, field_upper, value, visible)
            if not found:
                errors.append(f"Field '{field_name}' not found in SE16N selection criteria")

        return errors

    return await com.run(_apply_filters)


def _set_filter_with_scrolling(raw_tc: Any, field_upper: str, value: str, visible: int) -> bool:
    """Scroll through an SE16N table control to find and set a filter value."""
    scroll_max = raw_tc.VerticalScrollbar.Maximum
    found = False
    for scroll_pos in range(1, scroll_max + 1):
        try:
            raw_tc.VerticalScrollbar.Position = scroll_pos
        except Exception:  # pylint: disable=broad-exception-caught
            break
        if _find_and_set_filter_cell(raw_tc, field_upper, value, visible):
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


async def _execute_se16_query_desktop(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements,too-many-branches,too-many-statements,unused-argument
    backend: WebGuiBackend | DesktopBackend,
    table: str,
    filters: dict[str, str] | None,
    max_hits: int,
    now: datetime,
    ctx: Context | None = None,  # TODO: progress reporting via ctx not yet implemented on desktop
) -> SE16Result:
    """Desktop-specific SE16N query using read_table instead of ARIA parsing."""
    # Navigate to SE16N
    tx = await backend.enter_transaction("SE16N")
    if not tx.success:
        return _empty_failure(f"Failed to navigate to SE16N: {tx.error}", table, now)

    await backend.wait_for_ready()
    await backend.wait(2000)

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
        await backend.press_key("Enter")
        await backend.wait(2000)
        filter_errors = await _fill_se16n_filters_desktop(backend, filters)
        if filter_errors:
            logger.warning("Some desktop filters could not be applied", extra={"errors": filter_errors})

    # Set max hits (best effort)
    for max_label in ["GD-MAX_LINES", "Max. Number of Hits", "Maximale Trefferzahl"]:
        try:
            if await backend.focus_and_type(max_label, str(max_hits), delay_ms=50):
                break
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # Execute (F8)
    await backend.press_key("F8")
    await backend.wait(2000)

    # Check for errors in status bar
    sbar = await backend.get_status_bar()
    if sbar.type == "E":
        return _empty_failure(f"SE16N error: {sbar.message}", table, now)

    # Check for "no entries found"
    if sbar.message and any(
        msg in sbar.message.lower() for msg in ["keine werte", "no values", "keine einträge", "no entries"]
    ):
        return SE16Result(
            table=table,
            total_hits=0,
            returned_rows=0,
            truncated=False,
            columns=[],
            rows=[],
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

    # Desktop backend: use read_table instead of ARIA snapshot parsing
    if backend.backend_type == "desktop":
        return await _execute_se16_query_desktop(backend, table, filters, max_hits, now, ctx)

    from sapguimcp.backend.webgui.backend import WebGuiBackend as _WG  # pylint: disable=import-outside-toplevel

    assert isinstance(backend, _WG)

    # If filters are provided, get field order from SE11 FIRST
    # (before navigating to SE16N, since SE11 lookup changes the screen)
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
            filter_errors = await _fill_se16n_filters(backend, filters, field_order)
            if filter_errors:
                logger.warning("Some filters could not be applied", extra={"errors": filter_errors})
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
        retrieved_at=now,
    )


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_se16_tools(mcp: FastMCP) -> None:
    """Register SE16 tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Query SAP table data via SE16N (Data Browser). "
            "If sap-adt is available, prefer its run_query tool for simple queries. "
            "USE THIS for complex queries with dynamic filtering or when ADT is unavailable.\n\n"
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
            filters: Optional filter dict {field_name: value} - uses technical field names
            max_hits: Maximum rows to return (default 100)
            output_file: If provided, write full results to this JSON file and return summary
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SE16Result with all rows (inline), or
            SE16FileSummary with file path and preview (when output_file provided)
        """
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
        if output_file and result.success:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

            return SE16FileSummary(
                success=True,
                output_file=str(output_path.absolute()),
                table=result.table,
                total_hits=result.total_hits,
                returned_rows=result.returned_rows,
                truncated=result.truncated,
                columns=result.columns,
                sample_rows=result.rows[:5],  # First 5 rows as preview
            )

        return result
