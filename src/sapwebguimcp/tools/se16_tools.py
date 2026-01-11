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


async def _fill_se16n_max_hits(max_hits: int) -> None:
    """
    Fill SE16N max hits field.

    Tries English labels first, then German. Ignores errors since
    the field has a default value.
    """
    # Try English label first
    fill_result = await sap_fill_form_impl(
        {"Max. Number of Hits": str(max_hits)}, strict=False
    )
    if "Max. Number of Hits" not in fill_result.not_found:
        return

    # Try German label
    await sap_fill_form_impl({"Maximale Trefferzahl": str(max_hits)}, strict=False)


async def _fill_se16n_filters(filters: dict[str, str] | None) -> list[str]:
    """
    Fill filter values in SE16N selection criteria grid.

    Args:
        filters: Dict of {field_name: value} to filter on.
                 Field names should be technical names (e.g., "TCODE", "PGMNA").

    Returns:
        List of error messages (empty if all filters applied successfully).
    """
    if not filters:
        return []

    errors: list[str] = []
    page = await (await get_browser_manager()).get_current_page()

    js_code = _load_js("fill_se16_filter.js")

    for field_name, value in filters.items():
        try:
            result = await page.evaluate(js_code, {"fieldName": field_name.upper(), "value": value})
            if not result.get("success"):
                error_msg = result.get("error", f"Unknown error for field {field_name}")
                debug_info = result.get("debug", {})
                if debug_info:
                    logger.warning(
                        "SE16: Filter debug - grids=%d, rows=%d, fields=%s, buttons=%s",
                        debug_info.get("gridsFound", 0),
                        debug_info.get("rowsScanned", 0),
                        debug_info.get("fieldsAvailable", []),
                        debug_info.get("buttonsFound", [])[:10],  # First 10 buttons
                    )
                errors.append(error_msg)
                logger.warning("SE16: Filter error: %s", error_msg)
            else:
                logger.info("SE16: Applied filter %s=%s", field_name, value)
        except Exception as e:  # pylint: disable=broad-exception-caught
            errors.append(f"Failed to apply filter {field_name}={value}: {e}")
            logger.warning("SE16: Filter exception for %s: %s", field_name, e)

    # Small delay to let SAP process the filter values
    if filters:
        await page.wait_for_timeout(500)

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

    # Check if still on selection screen (table doesn't exist or error occurred)
    # Selection screen has columns like "Feldname", "Option", "Von-Wert" (German) or
    # "Field Name", "Option", "From-Value" (English) - not data columns
    selection_screen_columns = {"Feldname", "Field Name", "Option", "Von-Wert", "From-Value"}
    if any(col in snapshot for col in selection_screen_columns):
        return f"Table '{table}' not found in SAP (still on selection screen)"

    return None


async def _focus_grid(page: Any) -> None:
    """Focus the ALV grid for pagination (required for PageDown to work)."""
    try:
        grid = page.locator("[role='grid']").first
        if await grid.count() > 0:
            await grid.click()
            await page.wait_for_timeout(500)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning("SE16: Could not focus grid: %s", e)


async def _collect_rows_with_pagination(
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
        first_key = str(rows[0].get(columns[0], "")) if rows and columns else None

        # Detect if we're stuck on the same page
        if first_key == last_first_key:
            logger.debug("SE16: Page %d - same first key, likely at end", page_num)
            break

        last_first_key = first_key

        # Add new rows (skip duplicates)
        new_count = 0
        for row in rows:
            # Create a key from all values for deduplication
            row_key = "|".join(str(v) for v in row.values())
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


async def _execute_se16_query(
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

    # Navigate to SE16N
    if not (await sap_transaction_impl("SE16N")).success:
        return _empty_failure("Failed to navigate to SE16N", table, now)

    page = await (await get_browser_manager()).get_current_page()
    await page.wait_for_timeout(1000)  # Wait for SE16N screen to render

    # If filters are provided, we need to fill the table name differently
    # to ensure SAP's validation is triggered and the selection criteria grid
    # gets populated with table fields
    if filters:
        # Find and click on the table textbox, then type the table name
        # This mimics user behavior and properly triggers SAP validation
        table_filled = False
        for textbox_name in ["Table", "Tabelle"]:
            try:
                textbox = page.get_by_role("textbox", name=textbox_name).first
                if await textbox.count() > 0:
                    await textbox.click()
                    await textbox.fill("")  # Clear first
                    await textbox.type(table.upper(), delay=50)  # Type slowly
                    logger.info("SE16: Typed table name '%s' in field '%s'", table, textbox_name)
                    table_filled = True
                    break
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("SE16: Error typing in table field %s: %s", textbox_name, e)

        if not table_filled:
            # Fallback to fill_form approach
            if fill_error := await _fill_se16n_table_name(table):
                return _empty_failure(fill_error, table, now)
            logger.warning("SE16: Used fallback fill_form for table name")

        # Use sap_keyboard_impl to send Enter - this waits for networkidle
        # which ensures SAP processes the table validation round-trip
        logger.info("SE16: Pressing Enter to trigger table validation (with network wait)")
        await sap_keyboard_impl("Enter")

        # Wait for SAP to load table structure using JavaScript poll
        # Check for buttons with technical field names (all caps like TCODE, PGMNA)
        # SAP Web GUI uses both <button> elements and elements with role="button"
        async def check_grid_populated() -> bool:
            result = await page.evaluate("""
                () => {
                    const grids = document.querySelectorAll('[role="grid"]');
                    for (const grid of grids) {
                        // Look for both actual buttons AND elements with role="button"
                        const buttons = grid.querySelectorAll('button, [role="button"]');
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim();
                            // Check for technical field names (all caps, at least 3 chars)
                            if (text && /^[A-Z0-9_]{3,}$/.test(text)) {
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """)
            return result

        # Poll for up to 10 seconds
        for i in range(20):
            if await check_grid_populated():
                logger.info("SE16: Table structure loaded (poll iteration %d)", i)
                break
            await page.wait_for_timeout(500)
        else:
            logger.warning("SE16: Grid not populated after 10s polling")

        # Debug: take a screenshot to see actual screen state
        try:
            screenshot_path = Path(__file__).parent.parent.parent.parent / "unittests" / "se16_debug.png"
            await page.screenshot(path=str(screenshot_path))
            logger.info("SE16: Debug screenshot saved to %s", screenshot_path)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SE16: Could not take screenshot: %s", e)

        # Debug: capture the full page ARIA snapshot
        try:
            full_snapshot = await page.locator("body").aria_snapshot()
            snapshot_path = Path(__file__).parent.parent.parent.parent / "unittests" / "se16_debug.yaml"
            snapshot_path.write_text(full_snapshot, encoding="utf-8")
            logger.info("SE16: Debug ARIA snapshot saved to %s", snapshot_path)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SE16: Could not capture snapshot: %s", e)

        # Debug: check input elements' lsdata for field name info
        try:
            input_debug = await page.evaluate("""
                () => {
                    const grid = document.querySelector('[role="grid"]');
                    const rows = grid?.querySelectorAll('[role="row"]') || [];
                    const debugInputs = [];
                    for (let i = 1; i < rows.length && i < 4; i++) {
                        const row = rows[i];
                        const inputs = row.querySelectorAll('input');
                        for (const input of inputs) {
                            const lsdata = input.getAttribute('lsdata');
                            const id = input.id;
                            if (lsdata || id) {
                                debugInputs.push({
                                    rowIdx: i,
                                    inputId: id?.substring(0, 100),
                                    lsdata: lsdata?.substring(0, 300)
                                });
                            }
                        }
                    }
                    return debugInputs;
                }
            """)
            logger.info("SE16: Input lsdata debug: %s", input_debug)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("SE16: Could not get input lsdata: %s", e)

        filter_errors = await _fill_se16n_filters(filters)
        if filter_errors:
            logger.warning("SE16: Some filters could not be applied: %s", filter_errors)
    else:
        # No filters - just fill table name normally
        if fill_error := await _fill_se16n_table_name(table):
            return _empty_failure(fill_error, table, now)

    # Set max hits
    await _fill_se16n_max_hits(max_hits)

    # Execute query (F8) and wait for results
    await sap_keyboard_impl("F8")
    await page.wait_for_timeout(3000)

    # Get snapshot to check for errors and parse results
    snapshot = await page.locator("body").aria_snapshot()

    # Check for table not found errors
    if table_error := _check_table_not_found(snapshot, table):
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
    async def sap_se16_query(
        ctx: Context,
        table: str,
        filters: dict[str, str] | None = None,
        max_hits: int = DEFAULT_MAX_HITS,
        output_file: str | None = None,
    ) -> SE16Result | SE16FileSummary:
        """
        Query SAP table data via SE16N.

        Args:
            ctx: FastMCP context (injected)
            table: Table name to query (e.g., "MARA", "T000", "TSTC")
            filters: Optional filter dict {field_name: value} - uses technical field names
            max_hits: Maximum rows to return (default 100)
            output_file: If provided, write full results to this JSON file and return summary

        Returns:
            SE16Result with all rows (inline), or
            SE16FileSummary with file path and preview (when output_file provided)
        """
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
