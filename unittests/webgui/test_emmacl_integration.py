"""Integration tests for EMMACL (Energy Market Clearing) transaction."""

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import ClickResult
from sapguimcp.models import (
    DiscoveredFields,
    FillFormResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    StatusBarInfo,
    TableCellClickResult,
    TableData,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import capture_html_snapshot


@pytest.mark.anyio
async def test_emmacl_discover_fields(sap_mcp_client: ClientSession) -> None:
    """
    Test field discovery in EMMACL transaction.

    EMMACL is an energy market clearing transaction with many input fields,
    making it ideal for testing field discovery and batch fill capabilities.

    This test:
    1. Opens EMMACL transaction
    2. Captures HTML snapshot
    3. Uses sap_discover_fields to find all fields
    4. Verifies fields are discovered with proper structure
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    # Wait for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of EMMACL initial screen
    await capture_html_snapshot(sap_mcp_client, "emmacl_initial")

    # Discover all fields on the screen
    discover_result = await call_tool_typed(sap_mcp_client, "sap_discover_fields", {}, DiscoveredFields)
    assert discover_result.success, f"sap_discover_fields failed: {discover_result.error}"

    # Verify we found some fields
    field_count = discover_result.field_count or 0
    fields = discover_result.fields or []

    assert field_count > 0, f"EMMACL should have input fields. Got: {discover_result}"
    assert len(fields) > 0, f"Fields list should not be empty. Got: {discover_result}"

    # Print discovered fields for debugging (visible in test output)
    print(f"\nDiscovered {field_count} fields in EMMACL:")
    for field in fields[:20]:  # Show first 20
        print(f"  - {field.label or 'no-label'}: {field.selector or 'no-selector'}")


@pytest.mark.anyio
async def test_emmacl_fill_form_with_discovered_fields(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form in EMMACL using discovered field selectors.

    This test:
    1. Opens EMMACL transaction
    2. Discovers fields using sap_discover_fields
    3. Uses sap_fill_form to fill some of the discovered fields
    4. Verifies all specified fields were filled
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # First discover fields to find valid selectors
    discover_result = await call_tool_typed(sap_mcp_client, "sap_discover_fields", {}, DiscoveredFields)
    assert discover_result.success, f"sap_discover_fields failed: {discover_result.error}"

    fields = discover_result.fields or []

    # Find text input fields (not readonly, not checkboxes)
    fillable_fields = [f for f in fields if f.type in ("text", None) and f.selector]

    if len(fillable_fields) < 2:
        pytest.skip("Not enough fillable fields found in EMMACL")

    # Pick first 2 fillable fields and try to fill them
    fields_to_fill = {}
    for i, field in enumerate(fillable_fields[:2]):
        selector = field.selector
        if selector:
            fields_to_fill[selector] = f"TEST{i}"

    print(f"\nTrying to fill {len(fields_to_fill)} fields: {list(fields_to_fill.keys())}")

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": fields_to_fill}, FillFormResult)

    # Log results
    print(f"Filled: {fill_result.filled}")
    print(f"Not found: {fill_result.not_found}")
    print(f"Errors: {fill_result.errors}")

    # At least some fields should have been filled
    filled = fill_result.filled or []
    assert len(filled) > 0, f"Expected at least one field to be filled. Result: {fill_result}"


@pytest.mark.anyio
async def test_emmacl_execute_without_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test executing EMMACL without any filter (F8 on initial screen).

    This test:
    1. Opens EMMACL transaction
    2. Presses F8 to execute without filters
    3. Captures result table
    4. Saves HTML snapshot of results
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Execute without any filters (F8)
    kb_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert kb_result.success, f"sap_press_key F8 failed: {kb_result.error}"

    # Wait for results to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of results
    await capture_html_snapshot(sap_mcp_client, "emmacl_results_no_filter")

    # Read result table
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 20}, TableData)

    # Print results for debugging
    print(f"\nEMMACL results without filter:")
    print(f"Headers: {table_result.headers}")
    print(f"Total rows: {table_result.total_rows}")
    for row in (table_result.rows or [])[:5]:
        print(f"  Row {row.row}: {row.data}")

    # Verify we got some results (or at least the table was read)
    assert table_result.success, f"Table read failed: {table_result}"


@pytest.mark.anyio
async def test_emmacl_execute_with_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test executing EMMACL with filter fields.

    This test:
    1. Opens EMMACL transaction
    2. Fills a filter field (Business Process Code)
    3. Presses F8 to execute
    4. Verifies the search was executed (got results or "no data" message)
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Fill filter field using discovered selector
    # Using a filter value that likely won't match many rows to test filtering works
    filter_values = {
        "input[lsdata*='BPCODE-LOW']": "ZTEST",  # Business Process Code (likely no matches)
    }

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": filter_values}, FillFormResult)
    assert fill_result.success, f"sap_fill_form failed: {fill_result.error}"

    print(f"\nFilled filter fields: {fill_result.filled}")

    # Verify filter field was filled
    assert len(fill_result.filled or []) == len(
        filter_values
    ), f"Expected {len(filter_values)} fields filled, got: {fill_result}"

    # Execute with filter (F8)
    kb_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert kb_result.success, f"sap_press_key F8 failed: {kb_result.error}"

    # Wait for results to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of filtered results
    await capture_html_snapshot(sap_mcp_client, "emmacl_results_filtered")

    # Check status bar for result message (works in DE and EN)
    status_result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print(f"\nStatus bar after F8: {status_result.message or ''}")

    # Also try reading table (may show 0 rows if filter matched nothing)
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 5}, TableData)

    print(f"Table rows: {table_result.total_rows or 0}")

    # The test passes if:
    # 1. Filter was filled successfully (already verified above)
    # 2. F8 was executed (already verified)
    # 3. We got either results or a "no data" status message
    status_msg = (status_result.message or "").lower()
    total_rows = table_result.total_rows or 0

    # Either we got some rows, or we got a status message about no data
    assert (
        total_rows > 0 or "keine" in status_msg or "no " in status_msg or status_msg == ""
    ), f"Expected either results or 'no data' message. Got rows={total_rows}, status='{status_msg}'"


@pytest.mark.anyio
async def test_emmacl_alv_grid_click_cell(sap_mcp_client: ClientSession) -> None:
    """
    Test clicking on an ALV grid cell in EMMACL to navigate to detail view.

    This test verifies the full ALV grid click workflow:
    1. Opens EMMACL transaction
    2. Presses F8 to execute (shows ALV grid with results)
    3. Reads table with sap_read_table (should get ALV metadata + cell selectors)
    4. Clicks on a case number (hotspot cell) using sap_click_table_cell
    5. Verifies navigation to the detail screen

    This is a critical test for the ALV grid click support feature.
    The test MUST succeed with an actual click + navigation for the feature to work.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Step 1: Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Step 2: Execute without filters (F8) to get the results table
    kb_result = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert kb_result.success, f"sap_press_key F8 failed: {kb_result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Step 3: Read the table - should get ALV metadata with cell selectors
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 10}, TableData)
    assert table_result.success, f"sap_read_table failed: {table_result.error}"

    print(f"\nTable data structure:")
    print(f"  Headers: {table_result.headers}")
    print(f"  Total rows: {table_result.total_rows}")
    print(f"  ALV metadata: {table_result.alv or 'NOT PRESENT'}")

    # Verify we have ALV metadata (proves ALV grid detection worked)
    assert table_result.alv is not None, f"sap_read_table should return ALV metadata for EMMACL results."

    alv_meta = table_result.alv
    assert alv_meta.table_id, f"ALV metadata should have table_id: {alv_meta}"

    # Verify we have at least one row
    rows = table_result.rows or []
    assert len(rows) >= 1, f"Expected at least one row in EMMACL results: {table_result}"

    # Verify first row has cell metadata with selectors
    first_row = rows[0]
    cells = first_row.cells or {}
    print(f"  First row cells metadata: {cells}")

    assert cells, "First row should have cells metadata with click selectors. " f"Got row: {first_row}"

    # Find a hotspot cell (one that can be clicked to navigate)
    hotspot_cell = None
    hotspot_column = None
    for col_name, cell_info in cells.items():
        if cell_info.hotspot:
            hotspot_cell = cell_info
            hotspot_column = col_name
            break

    assert hotspot_cell, (
        "EMMACL results should have at least one hotspot cell (e.g., 'Fall' column). " f"Cells: {cells}"
    )

    print(f"\n  Found hotspot in column '{hotspot_column}': {hotspot_cell}")

    # Get the page title before clicking
    info_before = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert info_before.success, f"sap_get_screen_info failed: {info_before.error}"
    title_before = info_before.title
    print(f"  Title before click: {title_before}")

    # Step 4: Click on the hotspot cell using sap_click_table_cell
    # This should navigate to the detail view
    click_data = await call_tool_typed(
        sap_mcp_client,
        "sap_click_table_cell",
        {"row": first_row.row, "column": hotspot_column},
        TableCellClickResult,
    )
    assert click_data.success, f"sap_click_table_cell failed: {click_data.error}"

    print(f"\n  Click result:")
    print(f"    Selector used: {click_data.selector_used}")
    print(f"    Was hotspot: {click_data.was_hotspot}")
    print(f"    Page title after: {click_data.page_title}")

    # Verify the click was on a hotspot
    assert click_data.was_hotspot, f"Click should have been on a hotspot cell. Result: {click_data}"

    # Step 5: Verify navigation happened (title should change)
    title_after = click_data.page_title

    # The title should change to show the detail view
    # German: "Klärungsfall XXXXXXXXX anzeigen" (Show case XXXXXXXXX)
    # English: "Display Case XXXXXXXXX"
    assert title_before != title_after, (
        f"Page title should change after clicking hotspot cell. " f"Before: '{title_before}', After: '{title_after}'"
    )

    # Verify we're on a detail screen (not still on the list)
    detail_indicators = ["anzeigen", "display", "case", "fall", "klärungsfall"]
    assert any(
        ind in title_after.lower() for ind in detail_indicators
    ), f"Should navigate to detail view. Got title: '{title_after}'"

    print(f"\n  SUCCESS: Navigated from '{title_before}' to '{title_after}'")

    # Capture the detail screen HTML for reference
    await capture_html_snapshot(sap_mcp_client, "emmacl_case_detail")

    # Press F3 to go back to the list
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F3"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})


@pytest.mark.anyio
async def test_emmacl_alv_click_with_browser_click(sap_mcp_client: ClientSession) -> None:
    """
    Test clicking on an ALV grid cell using browser_click with the selector from sap_read_table.

    This is an alternative approach to sap_click_table_cell - using the
    pre-escaped CSS selector directly with browser_click.

    This test verifies:
    1. sap_read_table returns properly escaped CSS selectors
    2. browser_click can use these selectors directly
    3. Navigation works when clicking hotspot cells
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open EMMACL and get results
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Read table with ALV metadata
    table_data = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 5}, TableData)
    assert table_data.success, f"sap_read_table failed: {table_data.error}"

    rows = table_data.rows or []
    assert len(rows) >= 1, "Expected at least one row"

    # Find a hotspot cell selector
    first_row = rows[0]
    cells = first_row.cells or {}

    hotspot_selector = None
    for col_name, cell_info in cells.items():
        if cell_info.hotspot:
            hotspot_selector = cell_info.selector
            print(f"Found hotspot selector for '{col_name}': {hotspot_selector}")
            break

    assert hotspot_selector, "Expected a hotspot cell with selector"

    # Get title before click
    screen_info = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert screen_info.success, f"sap_get_screen_info failed: {screen_info.error}"
    title_before = screen_info.title

    # Use browser_click with the selector directly
    click_data = await call_tool_typed(sap_mcp_client, "browser_click", {"selector": hotspot_selector}, ClickResult)
    assert click_data.success, f"browser_click with ALV selector failed: {click_data.error}"

    # Wait for navigation
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Verify navigation
    screen_info_after = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert screen_info_after.success, f"sap_get_screen_info failed: {screen_info_after.error}"
    title_after = screen_info_after.title

    print(f"Title before: {title_before}")
    print(f"Title after: {title_after}")

    assert title_before != title_after, (
        f"Page title should change after clicking hotspot. " f"Before: '{title_before}', After: '{title_after}'"
    )

    # Go back
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F3"})


@pytest.mark.anyio
async def test_emmacl_manual_iteration_15_cases(sap_mcp_client: ClientSession) -> None:
    """
    Test manually iterating through 15 EMMACL cases.

    This test establishes a baseline for:
    1. How long it takes to click through cases manually
    2. What the navigation pattern looks like (list -> detail -> back)
    3. Context consumption of individual tool calls

    This test documents the manual iteration pattern for EMMACL cases,
    showing navigation and context consumption per iteration.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL and execute without filters
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Read table to get available cases
    table_data = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 20}, TableData)
    assert table_data.success, f"sap_read_table failed: {table_data.error}"

    rows = table_data.rows or []
    total_available = len(rows)

    if total_available < 1:
        pytest.skip("No EMMACL cases available to click through")

    # Limit to 15 cases (or fewer if not enough)
    cases_to_process = min(15, total_available)
    print(f"\nProcessing {cases_to_process} of {total_available} available cases")

    successful_clicks = 0
    failed_clicks = 0
    results: list[dict[str, str]] = []

    # Process each case: click -> verify navigation -> go back
    for i in range(cases_to_process):
        row = rows[i]
        row_num = row.row
        cells = row.cells or {}

        # Find a hotspot column (typically "Fall" or similar)
        hotspot_col = None
        for col_name, cell_info in cells.items():
            if cell_info.hotspot:
                hotspot_col = col_name
                break

        if not hotspot_col:
            print(f"  Row {row_num}: No hotspot found, skipping")
            failed_clicks += 1
            continue

        # Get title before click
        screen_before = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
        title_before = screen_before.title if screen_before.success else ""

        # Click on the hotspot cell
        try:
            click_data = await call_tool_typed(
                sap_mcp_client,
                "sap_click_table_cell",
                {"row": row_num, "column": hotspot_col},
                TableCellClickResult,
            )

            if not click_data.success:
                print(f"  Row {row_num}: Click failed - {click_data.error}")
                failed_clicks += 1
                continue

            # Wait for navigation
            await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

            # Get title after click
            screen_after = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
            title_after = screen_after.title if screen_after.success else ""

            # Verify navigation happened
            if title_before != title_after:
                successful_clicks += 1
                results.append({"row": str(row_num), "title": title_after})
                print(f"  Row {row_num}: Navigated to '{title_after}'")
            else:
                failed_clicks += 1
                print(f"  Row {row_num}: Title unchanged, navigation may have failed")

            # Go back to the list
            await sap_mcp_client.call_tool("sap_press_key", {"key": "F3"})
            await sap_mcp_client.call_tool("browser_wait", {"timeout": 1500})

        except Exception as e:  # pylint: disable=broad-exception-caught
            failed_clicks += 1
            print(f"  Row {row_num}: Error - {e}")

    print(f"\n=== EMMACL Manual Iteration Summary ===")
    print(f"Processed: {cases_to_process} cases")
    print(f"Successful: {successful_clicks}")
    print(f"Failed: {failed_clicks}")

    # At least half should succeed for the test to pass
    assert (
        successful_clicks >= cases_to_process // 2
    ), f"Expected at least {cases_to_process // 2} successful clicks, got {successful_clicks}"

    # This test documents the context cost of manual iteration:
    # - Each sap_click_table_cell call: ~300 tokens (call + result)
    # - Each sap_get_screen_info call: ~200 tokens
    # - Each sap_press_key call: ~200 tokens
    # - Each browser_wait call: ~150 tokens
    # For 15 cases: ~15 * (300 + 200 + 200 + 150 + 200 + 150) = ~18,000 tokens
    #
    print("\n=== Context Estimation (Manual vs Workflow) ===")
    print(f"Manual approach: ~{cases_to_process * 1200:,} tokens")
    print(f"Workflow approach: ~2,000 tokens (estimated)")
    print(f"Estimated savings: ~{(cases_to_process * 1200 - 2000):,} tokens")
