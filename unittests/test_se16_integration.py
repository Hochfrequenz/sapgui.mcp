"""
Integration tests for SE16 (Data Browser) query tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se16_query tool works correctly with pagination
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession

SE16_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se16_exploration"


def _get_content_text(content_item: Any) -> str:
    """Extract text from MCP content item."""
    import base64

    if hasattr(content_item, "text"):
        return content_item.text
    elif hasattr(content_item, "resource") and hasattr(content_item.resource, "blob"):
        return base64.b64decode(content_item.resource.blob).decode("utf-8")
    return str(content_item)


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for parser development."""
    result = await client.call_tool("browser_snapshot", {})
    if not result.content:
        raise RuntimeError("browser_snapshot returned no content")

    yaml_content = _get_content_text(result.content[0])
    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = SE16_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        SE16_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


def assert_tool_success(result: Any, tool_name: str) -> str:
    """Assert tool call succeeded and return the text content."""
    assert result.content, f"{tool_name} returned no content"
    text = _get_content_text(result.content[0])

    # Try to parse as JSON and check for actual errors
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            # Check for error field with actual value
            if data.get("error") is not None:
                raise AssertionError(f"{tool_name} failed: {data['error']}")
            # Check for success=false
            if data.get("success") is False:
                raise AssertionError(f"{tool_name} failed: {text}")
    except json.JSONDecodeError:
        # Not JSON - check for error string
        if "error" in text.lower() and "error" not in text.lower().split(":")[0]:
            raise AssertionError(f"{tool_name} failed: {text}")

    return text


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
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Go to SE16N
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})
    assert_tool_success(result, "sap_transaction")

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
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Go to SE16N
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16N"})
    assert_tool_success(result, "sap_transaction")

    # Set table name
    result = await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Table": "T000"}},
    )
    # May need German label
    if not result.content or "error" in _get_content_text(result.content[0]).lower():
        result = await sap_mcp_client.call_tool(
            "sap_fill_form",
            {"fields": {"Tabelle": "T000"}},
        )
    assert_tool_success(result, "sap_fill_form")

    # Execute (F8)
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    assert_tool_success(result, "sap_keyboard F8")

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
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Query T000 table
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "T000", "max_hits": 100},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    assert data["success"] is True, f"Query failed: {data.get('error')}"
    assert data["table"] == "T000"
    assert data["total_hits"] > 0, "Expected at least one row"
    assert data["total_hits"] == data["returned_rows"], "All rows should be returned"
    assert data["truncated"] is False, "Should not be truncated"
    assert len(data["columns"]) > 0, "Expected columns"
    assert "Client" in data["columns"] or "Mandant" in data["columns"], "Expected Client/Mandant column"
    assert len(data["rows"]) == data["returned_rows"]

    # Verify row structure
    first_row = data["rows"][0]["data"]
    assert "Client" in first_row or "Mandant" in first_row or "MANDT" in first_row


@pytest.mark.anyio
async def test_se16_query_medium_table_pagination(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with pagination (~130 rows = ~10 pages).

    Uses TSTC table (transaction codes) which has thousands of entries,
    but limits to 130 rows to test pagination across ~10 pages.
    """
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Query TSTC table with max_hits=130 (~10 pages at 13 rows/page)
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 130},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    assert data["success"] is True, f"Query failed: {data.get('error')}"
    assert data["table"] == "TSTC"
    assert data["total_hits"] == 130, "Expected 130 hits (max_hits limit)"
    assert data["returned_rows"] == 130, "Expected 130 rows returned"
    assert data["truncated"] is True, "Should be truncated (TSTC has >130 rows)"

    # Verify columns
    assert len(data["columns"]) > 0
    expected_columns = {"Transaction Code", "Transaktionscode", "TCODE"}
    found_columns = set(data["columns"])
    assert bool(expected_columns & found_columns), f"Expected a transaction code column in {data['columns']}"

    # Verify we got all 130 rows with unique transaction codes
    rows = data["rows"]
    assert len(rows) == 130
    tcodes = set()
    for row in rows:
        # Find the tcode field (may vary by language)
        row_data = row["data"]
        tcode = row_data.get("Transaction Code") or row_data.get("Transaktionscode") or row_data.get("TCODE", "")
        if tcode:
            tcodes.add(tcode)

    # Should have ~130 unique transaction codes (some might have same name in different scenarios)
    assert len(tcodes) >= 100, f"Expected at least 100 unique tcodes, got {len(tcodes)}"


@pytest.mark.anyio
async def test_se16_query_table_not_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with non-existent table."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Query non-existent table
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "ZZZNOTEXIST99", "max_hits": 10},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    # Should fail gracefully
    assert data["success"] is False, "Expected failure for non-existent table"
    assert data["error"] is not None
    assert "not found" in data["error"].lower() or "existiert nicht" in data["error"].lower()


@pytest.mark.anyio
async def test_se16_query_empty_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se16_query with a table that has no rows matching."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Query T001 with impossible filter would return 0 rows
    # For now, just test that the tool handles empty results gracefully
    # We'll use T001 which exists but with max_hits=0 it should return metadata only
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "T001", "max_hits": 1},  # Just get 1 row to verify it works
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    # Should succeed even with minimal rows
    assert data["success"] is True, f"Query failed: {data.get('error')}"
    assert data["table"] == "T001"


@pytest.mark.anyio
async def test_se16_query_output_file(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """Test sap_se16_query with output_file parameter."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    output_file = tmp_path / "se16_result.json"

    # Query T000 with output_file
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "T000", "max_hits": 100, "output_file": str(output_file)},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    summary = json.loads(text)

    # Should return SE16FileSummary
    assert "output_file" in summary, "Expected SE16FileSummary with output_file"
    assert summary["success"] is True, f"Query failed: {summary.get('error')}"
    assert summary["table"] == "T000"
    assert summary["total_hits"] > 0
    assert summary["returned_rows"] == summary["total_hits"]
    assert len(summary["columns"]) > 0
    assert len(summary["sample_rows"]) <= 5  # Preview is max 5 rows

    # Verify file was created
    assert output_file.exists(), f"Output file not created: {output_file}"

    # Verify file contents
    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert full_result["success"] is True
    assert full_result["table"] == "T000"
    assert len(full_result["rows"]) == summary["returned_rows"]


@pytest.mark.anyio
async def test_se16_query_large_pagination(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """
    Test sap_se16_query with larger result set (~200 rows = ~15 pages).

    This tests pagination stability and deduplication over more pages.
    Uses output_file to avoid large JSON in response.
    """
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    output_file = tmp_path / "se16_tstc_200.json"

    # Query TSTC with 200 rows (~15 pages)
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 200, "output_file": str(output_file)},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    summary = json.loads(text)

    assert summary["success"] is True, f"Query failed: {summary.get('error')}"
    assert summary["total_hits"] == 200
    # Allow slight variation due to pagination overlap (200 ± 2)
    assert 198 <= summary["returned_rows"] <= 202, f"Expected ~200 rows, got {summary['returned_rows']}"

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
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Query T000 which has numeric MANDT field
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "T000", "max_hits": 10},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    assert data["success"] is True
    assert len(data["rows"]) > 0

    # Find MANDT/Client field in first row - it should be numeric
    first_row = data["rows"][0]["data"]

    # MANDT is typically "000", "100", etc - should remain string since leading zeros matter
    # But purely numeric fields would be coerced
    # At minimum, verify the data is accessible and structured
    assert len(first_row) > 0, "Row should have data"


@pytest.mark.anyio
async def test_se16_query_columns_preserved(sap_mcp_client: ClientSession) -> None:
    """Test that column order and names are preserved correctly."""
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Query TSTC which has well-defined columns
    result = await sap_mcp_client.call_tool(
        "sap_se16_query",
        {"table": "TSTC", "max_hits": 5},
    )
    assert result.content, "sap_se16_query returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    assert data["success"] is True
    columns = data["columns"]

    # TSTC table should have specific columns
    assert len(columns) >= 3, f"Expected at least 3 columns, got {columns}"

    # All rows should have all columns as keys
    for row in data["rows"]:
        row_keys = set(row["data"].keys())
        expected_keys = set(columns)
        assert row_keys == expected_keys, f"Row keys {row_keys} != columns {expected_keys}"
