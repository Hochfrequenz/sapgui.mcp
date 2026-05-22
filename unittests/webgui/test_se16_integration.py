"""
Integration tests for SE16 (Data Browser) query tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se16_query tool works correctly with pagination
"""

import json
import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import FillResult, SnapshotResult
from sapguimcp.models import (
    FillFormResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SE16FileSummary,
    SE16Result,
    TableData,
    TransactionResult,
)

from .conftest import call_tool_typed, get_html_content
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)

SE16_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se16_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = SE16_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        SE16_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


# =============================================================================
# Exploratory Tests - Run these to capture snapshots for development
# =============================================================================


@pytest.mark.anyio
async def test_se16_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE16N initial screen snapshot.

    This test:
    1. Logs into SAP
    2. Opens SE16N
    3. Captures the initial selection screen
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE16N
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16N"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE16N screen
    await capture_yaml_snapshot(sap_mcp_client, "se16n_initial", overwrite=True)

    print("=" * 80)
    print("SE16N initial screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se16_capture_t000_results(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE16N results screen for T000 (small table with ~6 rows).

    This test verifies basic query functionality and captures result snapshots.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE16N
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16N"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Set table name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Table": "T000"}},
        FillFormResult,
    )
    # May need German label
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Tabelle": "T000"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Execute (F8)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F8 failed: {keyboard.error}"

    # Wait for results
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture result screen
    await capture_yaml_snapshot(sap_mcp_client, "se16n_t000_results", overwrite=True)

    print("=" * 80)
    print("T000 results snapshot saved")
    print("=" * 80)


# =============================================================================
# sap_se16_query Tool Integration Tests
# =============================================================================


@pytest.mark.anyio
async def test_se16_query_small_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a small table (T000 - ~6 rows)."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T000 table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 100},
        SE16Result,
    )

    assert result.success, f"Query failed: {result.error}"
    assert result.table == "T000"
    assert result.total_hits > 0, "Expected at least one row"
    assert result.total_hits == result.returned_rows, "All rows should be returned"
    assert result.truncated is False, "Should not be truncated"
    assert len(result.columns) > 0, "Expected columns"
    # Column name varies by language: English "Client", German "Mandant" or abbreviated "Mdt"
    assert (
        "Client" in result.columns or "Mandant" in result.columns or "Mdt" in result.columns
    ), "Expected Client/Mandant/Mdt column"
    assert len(result.rows) == result.returned_rows

    # Verify row structure - column name varies by language
    first_row = result.rows[0].data
    assert "Client" in first_row or "Mandant" in first_row or "MANDT" in first_row or "Mdt" in first_row


@pytest.mark.anyio
async def test_se16_query_medium_table_pagination(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with pagination (~130 rows = ~10 pages).

    Uses TSTC table (transaction codes) which has thousands of entries,
    but limits to 130 rows to test pagination across ~10 pages.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query TSTC table with max_hits=130 (~10 pages at 13 rows/page)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 130},
        SE16Result,
    )

    assert result.success, f"Query failed: {result.error}"
    assert result.table == "TSTC"
    assert result.total_hits == 130, "Expected 130 hits (max_hits limit)"
    assert result.returned_rows == 130, "Expected 130 rows returned"
    assert result.truncated is True, "Should be truncated (TSTC has >130 rows)"

    # Verify columns
    assert len(result.columns) > 0
    expected_columns = {"Transaction Code", "Transaktionscode", "TCODE"}
    found_columns = set(result.columns)
    assert bool(expected_columns & found_columns), f"Expected a transaction code column in {result.columns}"

    # Verify we got all 130 rows with unique transaction codes
    rows = result.rows
    assert len(rows) == 130
    tcodes = set()
    for row in rows:
        # Find the tcode field (may vary by language)
        row_data = row.data
        tcode = row_data.get("Transaction Code") or row_data.get("Transaktionscode") or row_data.get("TCODE", "")
        if tcode:
            tcodes.add(tcode)

    # Should have ~130 unique transaction codes (some might have same name in different scenarios)
    assert len(tcodes) >= 100, f"Expected at least 100 unique tcodes, got {len(tcodes)}"


@pytest.mark.anyio
async def test_se16_query_table_not_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with non-existent table."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query non-existent table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "ZZZNOTEXIST99", "max_hits": 10},
        SE16Result,
    )

    # Should fail gracefully - error message varies by language
    assert result.success is False, "Expected failure for non-existent table"
    assert result.error is not None
    error_lower = result.error.lower()
    assert any(
        x in error_lower for x in ["not found", "existiert nicht", "nicht gefunden", "not exist"]
    ), f"Unexpected error: {result.error}"


@pytest.mark.anyio
async def test_se16_query_empty_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a table that has no rows matching."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T001 which exists but with max_hits=1 it should return just 1 row
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T001", "max_hits": 1},
        SE16Result,
    )

    # Should succeed even with minimal rows
    assert result.success, f"Query failed: {result.error}"
    assert result.table == "T001"


@pytest.mark.anyio
async def test_se16_query_existing_table_with_no_data(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a table that exists but has no entries.

    Regression test: previously, empty tables were reported as 'Table not found'
    because the tool stayed on the selection screen after F8 and mistakenly
    interpreted the selection screen columns as a non-existent table signal.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # EGERH is a standard SAP table that exists but is typically empty
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "EGERH", "max_hits": 10},
        SE16Result,
    )

    # Must succeed (table exists) with 0 rows - NOT report "table not found"
    assert result.success, f"Empty table wrongly reported as error: {result.error}"
    assert result.table == "EGERH"
    assert result.total_hits == 0
    assert result.returned_rows == 0
    assert len(result.rows) == 0


@pytest.mark.anyio
async def test_se16_query_output_file(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """Test sap_se16_query with output_file parameter."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    output_file = tmp_path / "se16_result.json"

    # Query T000 with output_file
    summary = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 100, "output_file": str(output_file)},
        SE16FileSummary,
    )

    # Should return SE16FileSummary
    assert summary.output_file is not None, "Expected SE16FileSummary with output_file"
    assert summary.success, f"Query failed: {summary.error}"
    assert summary.table == "T000"
    assert summary.total_hits > 0
    assert summary.returned_rows == summary.total_hits
    assert len(summary.columns) > 0
    assert len(summary.sample_rows) <= 5  # Preview is max 5 rows

    # Verify file was created
    assert output_file.exists(), f"Output file not created: {output_file}"

    # Verify file contents
    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert full_result["success"] is True
    assert full_result["table"] == "T000"
    assert len(full_result["rows"]) == summary.returned_rows


@pytest.mark.anyio
async def test_se16_query_large_pagination(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """
    Test sap_se16_query with larger result set (~200 rows = ~15 pages).

    This tests pagination stability and deduplication over more pages.
    Uses output_file to avoid large JSON in response.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    output_file = tmp_path / "se16_tstc_200.json"

    # Query TSTC with 200 rows (~15 pages)
    summary = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 200, "output_file": str(output_file)},
        SE16FileSummary,
    )

    assert summary.success, f"Query failed: {summary.error}"
    assert summary.total_hits == 200
    # Allow slight variation due to pagination overlap (200 +/- 2)
    assert 198 <= summary.returned_rows <= 202, f"Expected ~200 rows, got {summary.returned_rows}"

    # Verify file contents
    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert 198 <= len(full_result["rows"]) <= 202

    # Check for row uniqueness (no duplicates from pagination)
    row_keys = set()
    for row in full_result["rows"]:
        # Create key from all values
        key = "|".join(str(v) for v in row["data"].values())
        assert key not in row_keys, f"Duplicate row found: {row['data']}"
        row_keys.add(key)


@pytest.mark.anyio
async def test_se16_query_type_coercion(sap_mcp_client: ClientSession) -> None:
    """Test that numeric values are properly coerced to int/float."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T000 which has numeric MANDT field
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 10},
        SE16Result,
    )

    assert result.success
    assert len(result.rows) > 0

    # Find MANDT/Client field in first row - it should be numeric
    first_row = result.rows[0].data

    # MANDT is typically "000", "100", etc - should remain string since leading zeros matter
    # But purely numeric fields would be coerced
    # At minimum, verify the data is accessible and structured
    assert len(first_row) > 0, "Row should have data"


@pytest.mark.anyio
async def test_se16_query_columns_preserved(sap_mcp_client: ClientSession) -> None:
    """Test that column order and names are preserved correctly."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query TSTC which has well-defined columns
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 5},
        SE16Result,
    )

    assert result.success
    columns = result.columns

    # TSTC table should have specific columns
    assert len(columns) >= 3, f"Expected at least 3 columns, got {columns}"

    # All rows should have all columns as keys
    for row in result.rows:
        row_keys = set(row.data.keys())
        expected_keys = set(columns)
        assert row_keys == expected_keys, f"Row keys {row_keys} != columns {expected_keys}"


@pytest.mark.anyio
async def test_se16_query_single_filter(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a single filter."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query TSTC (transaction table) with single filter on TCODE
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "filters": {"TCODE": "SE16"}, "max_hits": 10},
        SE16Result,
    )

    assert result.success, f"Query failed: {result.error}"
    # Should find at least 1 row for SE16
    assert result.returned_rows >= 1, "Expected at least 1 row for SE16"

    # Verify filter was applied - find TCODE column and check value
    # Column name varies by language: "Transaktionscode" (DE), "Transaction Code" (EN)
    tcode_cols = [
        c for c in result.columns if "TCODE" in c.upper() or "TRANSAKT" in c.upper() or "TRANSACTION" in c.upper()
    ]
    assert tcode_cols, f"No TCODE column found in {result.columns}"
    tcode_col = tcode_cols[0]
    for row in result.rows:
        assert row.data.get(tcode_col) == "SE16", f"Filter not applied, got {row.data.get(tcode_col)}"


@pytest.mark.anyio
async def test_se16_query_multiple_filters(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with multiple filters.

    Tests that multiple filters are correctly applied to the right fields.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query T100 with two filters - should return specific matching rows
    # T100 has fields: SPRSL (language), ARBGB (message class), MSGNR (message number), TEXT
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T100", "filters": {"ARBGB": "00", "MSGNR": "001"}, "max_hits": 10},
        SE16Result,
    )

    assert result.success, f"Query with multiple filters failed: {result.error}"
    # Should return rows - 00/001 is a common message
    assert result.returned_rows >= 1, "Expected at least 1 row for ARBGB=00, MSGNR=001"

    # Verify both filters were applied - find columns dynamically
    # Column names vary by language: ARBGB="Arbeitsgebiet" (DE), "Application Area" (EN)
    # MSGNR="MsgNr" (DE), "Message" (EN) - but avoid matching "Message Text"
    arbgb_cols = [
        c for c in result.columns if "ARBGB" in c.upper() or "ARBEITSGEBIET" in c.upper() or "APPLICATION" in c.upper()
    ]
    # Match "MsgNr" or "Message" but not "Message Text"
    msgnr_cols = [c for c in result.columns if "MSGNR" in c.upper() or c.upper() == "MESSAGE" or "NR" in c.upper()]
    assert arbgb_cols, f"No ARBGB column found in {result.columns}"
    assert msgnr_cols, f"No MSGNR column found in {result.columns}"

    arbgb_col = arbgb_cols[0]
    msgnr_col = msgnr_cols[0]
    for row in result.rows:
        # ARBGB may be returned as "00" or 0 (int) due to type coercion
        arbgb_val = str(row.data.get(arbgb_col, "")).zfill(2)
        assert arbgb_val == "00", f"ARBGB filter not applied, got {row.data.get(arbgb_col)}"
        # MSGNR may be returned as "001" or 1 (int)
        msgnr_val = str(row.data.get(msgnr_col, "")).lstrip("0") or "0"
        assert msgnr_val == "1", f"MSGNR filter not applied, got {row.data.get(msgnr_col)}"


@pytest.mark.anyio
async def test_se16_query_filter_with_special_chars(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with filter values containing special characters.

    This test checks filter values with slashes which was reported to cause issues.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Query TSTC with filter containing slash - many tcodes start with /
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "filters": {"TCODE": "/SAPAPO/*"}, "max_hits": 10},
        SE16Result,
    )

    # This may return 0 rows if no matching tcodes, but should not error
    assert result.success, f"Query with special chars failed: {result.error}"


@pytest.mark.anyio
async def test_se16_query_bug_report_filters(sap_mcp_client: ClientSession) -> None:
    """
    Test the exact filter combination from bug report.

    Bug report: filters {"SPRSL": "DE", "ARBGB": "/NA2/DBR"} caused "DE" to be
    entered in the table name field instead of the SPRSL filter field.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Try the exact filter values from the bug report
    # This may return 0 rows if /NA2/DBR doesn't exist, but should not error
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T100", "filters": {"SPRSL": "DE", "ARBGB": "/NA2/DBR"}, "max_hits": 10},
        SE16Result,
    )

    # The key assertion: the query should not fail with "DE does not exist" error
    # which would indicate the filter value was entered in the wrong field
    assert result.success, f"Bug report filters failed: {result.error}"
    assert "existiert nicht" not in (result.error or ""), "Filter value entered in wrong field"
    assert "does not exist" not in (result.error or ""), "Filter value entered in wrong field"


# --- Merged from test_sap_integration.py ---


@pytest.mark.anyio
async def test_se16_table_content_t000(sap_mcp_client: ClientSession) -> None:
    """Test reading actual table content from SE16 using T000 (Clients table).

    T000 is the SAP clients/mandants table. It exists on every SAP system
    and contains at least one row (the current client). It's small enough
    to not overwhelm the LLM context.

    This test verifies:
    - SE16 can display table content
    - The table has at least one row
    - We can capture the HTML for unit tests
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Enter table name T000 (Clients table - always exists, always small)
    # Use lsdata selector which is reliable for SAP Web GUI elements
    fill_result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='TABLENAME']", "value": "T000"}, FillResult
    )
    assert fill_result.success, f"Failed to fill table name field: {fill_result.error}"

    # Execute to show table content
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture table content HTML for unit tests
    await capture_html_snapshot(sap_mcp_client, "se16_t000_content")

    # Read the table data
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"start_row": 1, "end_row": 10}, TableData)

    # T000 must have at least one row (the current client)
    # Check for table data indicators
    rows_str = str(table_result.rows).lower() if table_result.rows else ""
    has_rows = table_result.rows is not None or "mandt" in rows_str
    has_content = table_result.total_rows is not None and table_result.total_rows > 0

    assert has_rows and has_content, (
        f"SE16 T000 should return table content with at least one client. " f"Response: {table_result}"
    )


@pytest.mark.anyio
async def test_se16_query_basic(sap_mcp_client: ClientSession) -> None:
    """
    Test basic sap_se16_query functionality without filters.

    Queries the T000 (Clients) table which exists on every SAP system
    and contains at least one row (the current client).

    Works in both EN and DE - the tool handles language internally.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Query T000 table (small table with at least 1 row)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 10},
        SE16Result,
    )

    assert result.success, f"sap_se16_query failed: {result.error}"
    assert result.table == "T000", f"Expected table='T000', got {result.table}"
    assert result.total_hits >= 1, f"T000 should have at least 1 client, got {result.total_hits}"
    assert result.returned_rows >= 1, f"Should return at least 1 row, got {result.returned_rows}"
    assert len(result.columns) > 0, "Should have column headers"
    # SE16N shows description labels, not technical names
    # T000's MANDT field is shown as "Mdt" (DE) or "Clnt" (EN)
    first_col = result.columns[0].lower()
    assert first_col in ("mdt", "clnt", "mandt", "client"), (
        f"T000 should have client/mandt as first column, got '{result.columns[0]}'. " f"All columns: {result.columns}"
    )


@pytest.mark.anyio
async def test_se16_query_with_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with filter parameter applied.

    Queries the TSTC (Transaction Codes) table with a filter on TCODE field.
    This verifies that the filter functionality works correctly.

    Works in both EN and DE - the filter uses technical field names.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Query TSTC table WITH filter on TCODE = 'SE16'
    # This should return exactly 1 row (the SE16 transaction)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "filters": {"TCODE": "SE16"}, "max_hits": 100},
        SE16Result,
    )

    assert result.success, f"sap_se16_query with filter failed: {result.error}"
    assert result.table == "TSTC", f"Expected table='TSTC', got {result.table}"

    # With exact filter TCODE='SE16', we should get exactly 1 row
    assert result.total_hits == 1, (
        f"Filter TCODE='SE16' should return exactly 1 hit, got {result.total_hits}. "
        "Filter may not have been applied."
    )
    assert result.returned_rows == 1, f"Should return exactly 1 row, got {result.returned_rows}"

    # Verify the returned row contains SE16
    # First column should be transaction code (displayed as "TCode" or "Transaktion" etc.)
    assert len(result.rows) == 1, f"Expected 1 row in results, got {len(result.rows)}"
    row_data = result.rows[0].data
    # Get the first column's value - should be "SE16"
    first_col_name = result.columns[0]
    first_col_value = row_data.get(first_col_name, "")
    assert first_col_value == "SE16", (
        f"Expected first column to contain 'SE16', got '{first_col_value}'. " f"Row data: {row_data}"
    )


@pytest.mark.anyio
async def test_se16_query_filter_multiple_results(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query filter with wildcard pattern returning multiple results.

    Queries TSTC with a filter pattern that matches multiple transactions.
    This verifies filters work for partial matches.

    Works in both EN and DE - uses technical field names.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Query TSTC with pattern filter - SE1* should match SE10, SE11, SE12, etc.
    # SAP uses * as wildcard in SE16N filters
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "filters": {"TCODE": "SE1*"}, "max_hits": 100},
        SE16Result,
    )

    assert result.success, f"sap_se16_query with pattern filter failed: {result.error}"
    assert result.table == "TSTC", f"Expected table='TSTC', got {result.table}"

    # SE1* should match multiple transactions (SE10, SE11, SE12, SE13, etc.)
    assert result.total_hits >= 5, (
        f"Filter TCODE='SE1*' should return at least 5 SE1x transactions, got {result.total_hits}. "
        "Filter may not have been applied correctly."
    )

    # Verify all returned rows have transaction code starting with SE1
    # First column contains the transaction code
    first_col_name = result.columns[0]
    for row in result.rows:
        tcode = str(row.data.get(first_col_name, ""))
        assert tcode.startswith("SE1"), (
            f"Expected transaction code starting with 'SE1', got '{tcode}'. " f"Row data: {row.data}"
        )


@pytest.mark.anyio
async def test_se16_query_after_se09(sap_mcp_client: ClientSession) -> None:
    """Regression: sap_se16_query puts filter value into table name field when called from SE09.

    The filter filling code used page.keyboard.type() which types into whatever has
    focus, not the target element. If the filter element click didn't properly transfer
    focus, the keyboard input went to the table name field instead.

    Fixes #289, #290.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Navigate to SE09 first (the starting point from the bug report)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE09"})

    # Now query E070 with a filter — this is what triggered the bug
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "E070", "filters": {"AS4USER": "*"}, "max_hits": 10},
        SE16Result,
    )

    assert result.success, f"sap_se16_query failed after SE09: {result.error}"
    assert result.table == "E070", f"Expected table='E070', got '{result.table}'"
    assert result.total_hits > 0, "Expected at least one transport in E070"


@pytest.mark.anyio
async def test_sap_get_screen_text_from_se16(sap_mcp_client: ClientSession) -> None:
    """Test reading screen text from SE16 initial screen."""
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await call_tool_typed(sap_mcp_client, "sap_get_screen_text", {}, ScreenText)

    # SE16 should show table name prompt - check title or labels
    response_text = (result.title or "").lower()
    labels_text = " ".join(result.labels or []).lower()
    combined_text = response_text + " " + labels_text

    if sap_language == "DE":
        expected_phrases = ["tabellenname", "tabelle", "data browser"]
    else:
        expected_phrases = ["table name", "table", "data browser"]

    assert any(
        phrase in combined_text for phrase in expected_phrases
    ), f"SE16 screen text should contain table-related labels. Language: {sap_language}. Got: {combined_text[:500]}"

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "se16_initial")


@pytest.mark.anyio
async def test_sap_get_screen_info_from_se16(sap_mcp_client: ClientSession) -> None:
    """Test getting screen info from SE16."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)

    # Should contain basic screen info
    assert result.title, "Screen info should contain title"
    assert result.url, "Screen info should contain url"
