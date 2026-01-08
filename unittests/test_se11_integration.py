"""
Integration tests for SE11 lookup tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se11_lookup tool works correctly
"""

import os
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession

HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"
YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "yaml_snapshots"


def _get_content_text(content_item: Any) -> str:
    """Extract text from MCP content item."""
    import base64

    if hasattr(content_item, "text"):
        return content_item.text
    elif hasattr(content_item, "resource") and hasattr(content_item.resource, "blob"):
        return base64.b64decode(content_item.resource.blob).decode("utf-8")
    return str(content_item)


async def capture_html_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture HTML snapshot for unit tests."""
    result = await client.call_tool("browser_get_html", {})
    if not result.content:
        raise RuntimeError("browser_get_html returned no content")

    html_content = _get_content_text(result.content[0])
    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.html"
    filepath = HTML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        HTML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(html_content, encoding="utf-8")
        print(f"Saved HTML snapshot: {filepath}")

    return html_content


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
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


def assert_tool_success(result: Any, tool_name: str) -> str:
    """Assert tool call succeeded and return the text content."""
    import json

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
async def test_se11_capture_table_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE11 snapshots for a table (T000) to understand the YAML structure.

    This test:
    1. Logs into SAP
    2. Opens SE11
    3. Enters table name T000
    4. Presses F7 (Display)
    5. Captures both HTML and YAML snapshots
    """
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Go to SE11
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11"})
    assert_tool_success(result, "sap_transaction")

    # Capture initial SE11 screen
    await capture_html_snapshot(sap_mcp_client, "se11_initial", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_initial", overwrite=True)

    # Fill table name using sap_fill_form
    # The field label is "Tabellenname, 16-stellig" in German
    result = await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Tabellenname": "T000"}},
    )
    assert_tool_success(result, "sap_fill_form")

    # Press F7 (Display)
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F7"})
    assert_tool_success(result, "sap_keyboard F7")

    # Wait a moment for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar for errors
    result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    status_text = _get_content_text(result.content[0]) if result.content else ""
    print(f"Status bar after F7: {status_text}")

    # Capture the result screen
    await capture_html_snapshot(sap_mcp_client, "se11_t000_fields", overwrite=True)
    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se11_t000_fields", overwrite=True)

    # YAML snapshot saved to file
    print("=" * 80)
    print("YAML SNAPSHOT saved")
    print("=" * 80)

    # Go back with F3
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})
    assert_tool_success(result, "sap_keyboard F3")


@pytest.mark.anyio
async def test_se11_capture_structure_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE11 snapshots for a structure (BAPIRET2) to understand the YAML structure.
    """
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Go to SE11
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11"})
    assert_tool_success(result, "sap_transaction")

    # Fill structure name - need to select the Structure radio button first
    # First, let's see the screen structure
    await capture_yaml_snapshot(sap_mcp_client, "se11_before_structure_select", overwrite=True)

    # Fill the Datentyp (Data type) field with structure name
    result = await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Datentyp": "BAPIRET2"}},
    )
    assert_tool_success(result, "sap_fill_form")

    # Press F7 (Display)
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F7"})
    assert_tool_success(result, "sap_keyboard F7")

    # Wait a moment for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar for errors
    result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    status_text = _get_content_text(result.content[0]) if result.content else ""
    print(f"Status bar after F7: {status_text}")

    # Capture the result screen
    await capture_html_snapshot(sap_mcp_client, "se11_bapiret2_fields", overwrite=True)
    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se11_bapiret2_fields", overwrite=True)

    # YAML snapshot saved to file
    print("=" * 80)
    print("YAML SNAPSHOT saved")
    print("=" * 80)

    # Go back with F3
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})
    assert_tool_success(result, "sap_keyboard F3")


@pytest.mark.anyio
async def test_se11_table_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test SE11 behavior when table doesn't exist - capture error state.
    """
    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Go to SE11
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11"})
    assert_tool_success(result, "sap_transaction")

    # Fill with non-existent table
    result = await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Datenbanktabelle": "ZZZNOTEXIST"}},
    )
    assert_tool_success(result, "sap_fill_form")

    # Press F7 (Display)
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F7"})
    # This might return an error - that's expected

    # Wait a moment
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar - should show error
    result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    status_text = _get_content_text(result.content[0]) if result.content else ""
    print(f"Status bar for non-existent table: {status_text}")

    # Capture the error state
    await capture_yaml_snapshot(sap_mcp_client, "se11_table_not_found", overwrite=True)


# =============================================================================
# sap_se11_lookup Tool Integration Tests
# =============================================================================


@pytest.mark.anyio
async def test_se11_lookup_single_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with a single table."""
    import json

    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Look up T000 table
    result = await sap_mcp_client.call_tool(
        "sap_se11_lookup",
        {"names": "T000", "object_type": "table"},
    )
    assert result.content, "sap_se11_lookup returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    assert data["success"] is True, f"Lookup failed: {data.get('error')}"
    assert len(data["entries"]) == 1, f"Expected 1 entry, got {len(data['entries'])}"
    assert len(data["errors"]) == 0, f"Unexpected errors: {data['errors']}"

    entry = data["entries"][0]
    assert entry["name"] == "T000"
    assert entry["object_type"] == "table"
    # Accept German "Mandant" or English "Client" description
    desc = entry["description"].lower()
    assert "mandant" in desc or "client" in desc, f"Unexpected description: {entry['description']}"
    assert len(entry["fields"]) > 0

    # Check MANDT field
    mandt = next((f for f in entry["fields"] if f["name"] == "MANDT"), None)
    assert mandt is not None, "MANDT field not found"
    assert mandt["datatype"] == "CLNT"
    assert mandt["is_key"] is True


@pytest.mark.anyio
async def test_se11_lookup_table_list(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with a list of tables."""
    import json

    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Look up multiple tables directly (no prior lookup)
    result = await sap_mcp_client.call_tool(
        "sap_se11_lookup",
        {"names": ["T000", "T001"], "object_type": "table"},
    )
    assert result.content, "sap_se11_lookup returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    assert data["success"] is True, f"Lookup failed: {data.get('error')}"
    assert len(data["entries"]) == 2, f"Expected 2 entries, got {len(data['entries'])}. Errors: {data['errors']}"

    names = {e["name"] for e in data["entries"]}
    assert "T000" in names
    assert "T001" in names


@pytest.mark.anyio
async def test_se11_lookup_table_not_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with non-existent table."""
    import json

    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Look up non-existent table
    result = await sap_mcp_client.call_tool(
        "sap_se11_lookup",
        {"names": "ZZZNOTEXIST99", "object_type": "table"},
    )
    assert result.content, "sap_se11_lookup returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    # Should have success=False since all lookups failed
    assert data["success"] is False
    assert len(data["entries"]) == 0
    assert len(data["errors"]) == 1

    error = data["errors"][0]
    assert error["name"] == "ZZZNOTEXIST99"
    assert "not found" in error["error"].lower()


@pytest.mark.anyio
async def test_se11_lookup_mixed_results(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with mix of existing and non-existing tables."""
    import json

    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # Look up mix of tables
    result = await sap_mcp_client.call_tool(
        "sap_se11_lookup",
        {"names": ["T000", "ZZZNOTEXIST99"], "object_type": "table"},
    )
    assert result.content, "sap_se11_lookup returned no content"

    text = _get_content_text(result.content[0])
    data = json.loads(text)

    # Should have success=True since at least one succeeded
    assert data["success"] is True
    assert len(data["entries"]) == 1
    assert len(data["errors"]) == 1

    assert data["entries"][0]["name"] == "T000"
    assert data["errors"][0]["name"] == "ZZZNOTEXIST99"


@pytest.mark.anyio
async def test_se11_lookup_large_batch_to_file(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """Test sap_se11_lookup with >10 tables using output_file parameter."""
    import json

    # Login
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(result, "sap_login")

    # 11 ERCH* tables to trigger file output
    tables = [
        "ERCH",
        "ERCHARC",
        "ERCHC",
        "ERCHC_DISP",
        "ERCHC_DISP_SEL",
        "ERCHC_SHORT",
        "ERCHC_STABLE",
        "ERCHE",
        "ERCHE_I1",
        "ERCHE_M18",
        "ERCHE_STABLE",
    ]
    output_file = tmp_path / "se11_batch_result.json"

    # Look up tables with output_file
    result = await sap_mcp_client.call_tool(
        "sap_se11_lookup",
        {"names": tables, "object_type": "table", "output_file": str(output_file)},
    )
    assert result.content, "sap_se11_lookup returned no content"

    text = _get_content_text(result.content[0])
    summary = json.loads(text)

    # Should return SE11FileSummary, not SE11Result
    assert "output_file" in summary, "Expected SE11FileSummary with output_file"
    assert summary["total_requested"] == 11
    assert summary["successful"] + summary["failed"] == 11
    assert summary["success"] is True, f"Batch lookup failed: {summary}"

    # Verify file was created and contains full results
    assert output_file.exists(), f"Output file not created: {output_file}"

    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert full_result["success"] is True
    assert len(full_result["entries"]) == summary["successful"]
    assert len(full_result["errors"]) == summary["failed"]

    # Verify all requested tables are accounted for
    found_names = {e["name"] for e in full_result["entries"]}
    error_names = {e["name"] for e in full_result["errors"]}
    assert found_names | error_names == set(tables)
