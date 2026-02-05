"""
SE16 (Data Browser) query tool for SAP table data.

This module provides a tool to query SAP table data via SE16N transaction,
returning structured row data with automatic pagination for large result sets.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations

from sapwebguimcp.models import SE16FileSummary, SE16Result, SE16Row, get_browser_manager
from sapwebguimcp.parsers.se16_parser import parse_se16_columns, parse_se16_hit_count, parse_se16_rows
from sapwebguimcp.tools.sap_tool_impl import (
    _load_js,
    sap_fill_form_impl,
    sap_keyboard_impl,
    sap_transaction_impl,
)
from sapwebguimcp.tools.se11_tools import _lookup_single_object

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


async def _get_field_order_from_se11(table: str) -> dict[str, int] | None:
    """
    Get field order from SE11 for a table.

    Returns a dict mapping field name (uppercase) to 0-based row index,
    or None if SE11 lookup fails.

    The order in SE11 matches the row order in SE16N's selection criteria grid.
    """
    page = await (await get_browser_manager()).get_current_page()

    try:
        result = await _lookup_single_object(page, table, "table")

        # Press F3 (Back) to exit SE11 and return to clean state
        # This prevents state issues when navigating to SE16N next
        await page.keyboard.press("F3")
        await page.wait_for_timeout(500)

        # Check if we got an SE11Entry (success) vs SE11Error
        if hasattr(result, "fields") and result.fields:
            # Build mapping: field_name -> row_index
            field_order: dict[str, int] = {}
            for idx, field in enumerate(result.fields):
                field_order[field.name.upper()] = idx
            logger.info("SE16: Got %d fields from SE11 for table %s", len(field_order), table)
            return field_order

        logger.warning("SE16: SE11 lookup returned no fields for %s", table)
        return None

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("SE16: SE11 lookup failed for %s: %s", table, e)
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


async def _fill_se16n_table_name(table: str) -> str | None:
    """
    Fill SE16N table name field.

    Tries English labels first, then German.

    Returns:
        Error message if failed, None if successful.
    """
    # Try English label first
    fill_result = await sap_fill_form_impl({"Table": table.upper()}, strict=False)
    if "Table" not in fill_result.not_found:
        return None

    # Try German label
    fill_result = await sap_fill_form_impl({"Tabelle": table.upper()}, strict=False)
    if "Tabelle" in fill_result.not_found:
        return f"Failed to set table name field. Not found: {fill_result.not_found}"

    return None


async def _type_table_name_with_validation(page: Any, table: str) -> str | None:
    """
    Type table name in SE16N and trigger validation with Enter.

    This approach mimics user behavior to trigger SAP's table validation
    round-trip, which populates the selection criteria grid.

    Returns:
        Error message if failed, None if successful.
    """
    # Find and click on the table textbox, then type the table name
    for textbox_name in ["Table", "Tabelle"]:
        try:
            textbox = page.get_by_role("textbox", name=textbox_name).first
            if await textbox.count() > 0:
                await textbox.click()
                await textbox.fill("")  # Clear first
                await textbox.type(table.upper(), delay=50)  # Type slowly
                logger.info("SE16: Typed table name '%s' in field '%s'", table, textbox_name)

                # Use sap_keyboard_impl to send Enter - waits for networkidle
                logger.info("SE16: Pressing Enter to trigger table validation")
                await sap_keyboard_impl("Enter")
                return None
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SE16: Error typing in table field %s: %s", textbox_name, e)

    # Fallback to fill_form approach
    if fill_error := await _fill_se16n_table_name(table):
        return fill_error
    logger.warning("SE16: Used fallback fill_form for table name")
    await sap_keyboard_impl("Enter")
    return None


async def _wait_for_grid_rows(page: Any, timeout_seconds: int = 5) -> bool:
    """
    Wait for SE16N selection criteria grid to populate with data rows.

    Returns:
        True if grid has rows, False if timeout.
    """
    for i in range(timeout_seconds * 2):  # Poll every 500ms
        result = await page.evaluate("""
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
            logger.info("SE16: Table structure loaded (poll iteration %d)", i)
            return True
        await page.wait_for_timeout(500)

    logger.warning("SE16: Grid not populated after %ds polling", timeout_seconds)
    return False


async def _fill_se16n_max_hits(max_hits: int) -> None:
    """
    Fill SE16N max hits field.

    Tries English labels first, then German. Ignores errors since
    the field has a default value.
    """
    # Try English label first
    fill_result = await sap_fill_form_impl({"Max. Number of Hits": str(max_hits)}, strict=False)
    if "Max. Number of Hits" not in fill_result.not_found:
        return

    # Try German label
    await sap_fill_form_impl({"Maximale Trefferzahl": str(max_hits)}, strict=False)


async def _fill_filter_with_playwright(
    page: Any, element_id: str | None, selector: str | None, value: str, field_name: str
) -> bool:
    """
    Fill a filter field using Playwright's native click + type.

    Tries element ID first, then selector. Uses Ctrl+A to clear before typing.
    After typing, clicks on body to blur and commit the value to SAP.

    Returns:
        True if fill succeeded, False otherwise.
    """
    # Try by element ID first (use attribute selector for IDs with special chars)
    if element_id:
        try:
            element = page.locator(f'[id="{element_id}"]')
            if await element.count() > 0:
                await element.click()
                await page.wait_for_timeout(100)
                await page.keyboard.press("Control+a")
                await page.keyboard.type(value, delay=30)
                # Click body to blur and commit the value
                await page.locator("body").click(position={"x": 10, "y": 10})
                await page.wait_for_timeout(300)
                logger.info("SE16: Filled filter %s=%s via Playwright (id)", field_name, value)
                return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SE16: Playwright fill by ID failed: %s", e)

    # Try by CSS selector
    if selector:
        try:
            element = page.locator(selector)
            if await element.count() > 0:
                await element.click()
                await page.wait_for_timeout(100)
                await page.keyboard.press("Control+a")
                await page.keyboard.type(value, delay=30)
                # Click body to blur and commit the value
                await page.locator("body").click(position={"x": 10, "y": 10})
                await page.wait_for_timeout(300)
                logger.info("SE16: Filled filter %s=%s via Playwright (selector)", field_name, value)
                return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SE16: Playwright fill by selector failed: %s", e)

    return False


async def _fill_filter_by_index(page: Any, find_js: str, field_name: str, value: str, row_index: int) -> str | None:
    """
    Fill a single filter field using index-based approach.

    Uses JS to find the element, then Playwright to fill it.

    Returns:
        Error message if failed, None if successful.
    """
    # Find the element using JS
    result = await page.evaluate(find_js, {"rowIndex": row_index, "fieldName": field_name})

    if not result.get("success"):
        error_msg = str(result.get("error", f"Could not find element for {field_name}"))
        debug_info = result.get("debug", {})
        logger.warning("SE16: Find element failed - %s, debug=%s", error_msg, debug_info)
        return error_msg

    # Extract element info
    element_id = result.get("elementId")
    selector = result.get("selector")
    strategy = result.get("strategy", "unknown")
    element_type = result.get("elementType", "unknown")

    logger.info(
        "SE16: Found element for %s (row %d): id=%s, type=%s, strategy=%s",
        field_name,
        row_index,
        element_id,
        element_type,
        strategy,
    )

    # Fill using Playwright
    if await _fill_filter_with_playwright(page, element_id, selector, value, field_name):
        return None

    return f"Found element for {field_name} but Playwright fill failed"


async def _fill_se16n_filters(filters: dict[str, str] | None, field_order: dict[str, int] | None) -> list[str]:
    """
    Fill filter values in SE16N selection criteria grid using row indices.

    Uses SE11 field order mapping to find the correct row index for each field,
    avoiding the need to search for field names in the DOM (which fails due to
    SAP Web GUI's lazy column rendering).

    Uses a two-step approach:
    1. JavaScript finds the target element's ID/selector
    2. Playwright's native click + type fills the value (triggers proper SAP events)

    Args:
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
    page = await (await get_browser_manager()).get_current_page()

    # Load appropriate JS based on whether we have field order
    find_js = _load_js("find_se16_filter_input.js") if field_order else None
    fill_js = _load_js("fill_se16_filter.js") if not field_order else None

    if not field_order:
        logger.warning("SE16: No field order available, falling back to name-based filter search")

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
                error = await _fill_filter_by_index(page, find_js, field_upper, value, field_order[field_upper])
                if error:
                    errors.append(error)

            elif fill_js:
                # Fall back to name-based JavaScript approach
                result = await page.evaluate(fill_js, {"fieldName": field_upper, "value": value})

                if not result.get("success"):
                    error_msg = result.get("error", f"Unknown error for field {field_name}")
                    errors.append(error_msg)
                    logger.warning("SE16: Filter error (name-based): %s", error_msg)
                else:
                    logger.info("SE16: Applied filter %s=%s via JS (name-based)", field_name, value)

        except Exception as e:  # pylint: disable=broad-exception-caught
            errors.append(f"Failed to apply filter {field_name}={value}: {e}")
            logger.warning("SE16: Filter exception for %s: %s", field_name, e)

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


async def _focus_grid(page: Any) -> None:
    """Focus the ALV grid for pagination (required for PageDown to work)."""
    try:
        grid = page.locator("[role='grid']").first
        if await grid.count() > 0:
            await grid.click()
            await page.wait_for_timeout(500)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("SE16: Could not focus grid: %s", e)


async def _collect_rows_with_pagination(  # pylint: disable=too-many-locals
    page: Any,
    total_hits: int,
    columns: list[str],
    ctx: Context | None = None,
) -> list[dict[str, Any]]:
    """
    Collect all rows from SE16N results using pagination.

    Uses PageDown to scroll through lazy-loaded ALV grid, collecting
    rows from each page until all are collected or no new rows found.

    Args:
        page: Playwright page object
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
        snapshot = await page.locator("body").aria_snapshot()
        rows = parse_se16_rows(snapshot, columns)

        if not rows:
            logger.debug("SE16: Page %d - no rows found", page_num)
            stuck_count += 1
            if stuck_count >= 3:
                logger.warning("SE16: No rows found for 3 consecutive pages, stopping")
                break
            await page.wait_for_timeout(int(PAGE_WAIT_TIME.total_seconds() * 2000))
            continue

        stuck_count = 0

        # Get first row's key (first column value) for duplicate detection
        first_key = str(rows[0].get(first_col, "")) if rows and first_col else None

        # Detect if we're stuck on the same page
        if first_key == last_first_key:
            logger.debug("SE16: Page %d - same first key, likely at end", page_num)
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
            "SE16: Page %d - collected %d new rows (total: %d/%d)",
            page_num,
            new_count,
            len(all_rows),
            total_hits,
        )

        # Report progress if context available
        if ctx:
            try:
                await ctx.report_progress(progress=len(all_rows), total=total_hits)
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # Progress reporting is optional, don't fail on errors

        # Check if we've collected all rows
        if len(all_rows) >= total_hits:
            logger.info("SE16: Collected all %d rows", len(all_rows))
            break

        # PageDown to next page
        await sap_keyboard_impl("PageDown")
        await page.wait_for_timeout(int(PAGE_WAIT_TIME.total_seconds() * 1000))
        page_num += 1

    return all_rows


async def _execute_se16_query(  # pylint: disable=too-many-locals,too-many-branches,too-many-return-statements
    table: str,
    filters: dict[str, str] | None,
    max_hits: int,
    ctx: Context | None = None,
) -> SE16Result:
    """
    Execute SE16N query and collect results.

    Args:
        table: Table name to query
        filters: Optional filter dict {field_name: value}
        max_hits: Maximum rows to return
        ctx: FastMCP context for progress reporting

    Returns:
        SE16Result with collected data
    """
    now = datetime.now(UTC)

    # If filters are provided, get field order from SE11 FIRST
    # (before navigating to SE16N, since SE11 lookup changes the screen)
    field_order: dict[str, int] | None = None
    if filters:
        logger.info("SE16: Getting field order from SE11 for table %s", table)
        field_order = await _get_field_order_from_se11(table)
        if field_order is None:
            logger.warning("SE16: Could not get field order from SE11, filters may not work")

    # Navigate to SE16N
    if not (await sap_transaction_impl("SE16N")).success:
        return _empty_failure("Failed to navigate to SE16N", table, now)

    page = await (await get_browser_manager()).get_current_page()
    await page.wait_for_timeout(1000)  # Wait for SE16N screen to render

    # Fill table name - with validation trigger if filters are provided
    fill_error: str | None = None
    if filters:
        fill_error = await _type_table_name_with_validation(page, table)
        if not fill_error:
            await _wait_for_grid_rows(page, timeout_seconds=5)
            filter_errors = await _fill_se16n_filters(filters, field_order)
            if filter_errors:
                logger.warning("SE16: Some filters could not be applied: %s", filter_errors)
    else:
        fill_error = await _fill_se16n_table_name(table)

    if fill_error:
        return _empty_failure(fill_error, table, now)

    # Set max hits
    await _fill_se16n_max_hits(max_hits)

    # Click on the table name field to ensure focus is in the main screen area
    # (not stuck in filter grid which can interfere with F8)
    try:
        for field_name in ["Table", "Tabelle"]:
            textbox = page.get_by_role("textbox", name=field_name).first
            if await textbox.count() > 0:
                await textbox.click()
                await page.wait_for_timeout(200)
                break
    except Exception:  # pylint: disable=broad-exception-caught
        pass  # Best effort - continue with F8

    # Execute query (F8) and wait for results
    logger.info("SE16: Executing query with F8")
    await sap_keyboard_impl("F8")
    await page.wait_for_timeout(3000)

    # Get snapshot to check for errors and parse results
    snapshot = await page.locator("body").aria_snapshot()

    # Check for table not found errors
    if table_error := _check_table_not_found(snapshot, table):
        # Log first 500 chars of snapshot for debugging
        logger.warning("SE16: Check failed, snapshot preview: %s", snapshot[:500])
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
        logger.info("SE16: Parsed selection screen columns, table '%s' likely doesn't exist", table)
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
    await _focus_grid(page)
    rows = [SE16Row(data=row) for row in await _collect_rows_with_pagination(page, total_hits, columns, ctx)]

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
            "USE THIS instead of sap_transaction('SE16') - faster and returns structured data.\n\n"
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
        browser_manager = await get_browser_manager()

        # Validate session exists and check agent binding at entry point
        try:
            browser_manager.get_session_page_checked(session, agent_id, "sap_se16_query")
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

        logger.info("SE16: Querying table %s with max_hits=%d", table, max_hits)

        result = await _execute_se16_query(table, filters, max_hits, ctx)

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
