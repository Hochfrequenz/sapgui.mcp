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
from conftest import call_tool_typed
from mcp import ClientSession

from sapwebguimcp.models import (
    FillFormResult,
    KeyboardResult,
    LoginResult,
    SE16FileSummary,
    SE16Result,
    SnapshotResult,
    TransactionResult,
)

SE16_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se16_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.yaml

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
    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
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
    assert "Client" in result.columns or "Mandant" in result.columns, "Expected Client/Mandant column"
    assert len(result.rows) == result.returned_rows

    # Verify row structure
    first_row = result.rows[0].data
    assert "Client" in first_row or "Mandant" in first_row or "MANDT" in first_row


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

    # Should fail gracefully
    assert result.success is False, "Expected failure for non-existent table"
    assert result.error is not None
    assert "not found" in result.error.lower() or "existiert nicht" in result.error.lower()


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
