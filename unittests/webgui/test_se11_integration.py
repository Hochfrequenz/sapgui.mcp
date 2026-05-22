"""
Integration tests for SE11 lookup tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se11_lookup tool works correctly
"""

import json
import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import ClickResult, SnapshotResult
from sapguimcp.models import (
    FillFormResult,
    KeyboardResult,
    LoginResult,
    SE11FileSummary,
    SE11Result,
    StatusBarInfo,
    TransactionResult,
)

from .conftest import call_tool_typed, get_html_content
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)

HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"
YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "yaml_snapshots"


async def capture_html_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture HTML snapshot for unit tests."""
    html_content = await get_html_content(client)

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
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"Saved YAML snapshot: {filepath}")

    return yaml_content


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
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE11
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE11 screen
    await capture_html_snapshot(sap_mcp_client, "se11_initial", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_initial", overwrite=True)

    # Fill table name using sap_fill_form
    # The field label is "Tabellenname, 16-stellig" in German
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Tabellenname": "T000"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 (Display)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    # Wait a moment for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar for errors
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar after F7: {status.message}")

    # Capture the result screen
    await capture_html_snapshot(sap_mcp_client, "se11_t000_fields", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_t000_fields", overwrite=True)

    # YAML snapshot saved to file
    print("=" * 80)
    print("YAML SNAPSHOT saved")
    print("=" * 80)

    # Go back with F3
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F3 failed: {keyboard.error}"


@pytest.mark.anyio
async def test_se11_capture_structure_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE11 snapshots for a structure (BAPIRET2) to understand the YAML structure.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE11
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Fill structure name - need to select the Structure radio button first
    # First, let's see the screen structure
    await capture_yaml_snapshot(sap_mcp_client, "se11_before_structure_select", overwrite=True)

    # Fill the Datentyp (Data type) field with structure name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Datentyp": "BAPIRET2"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 (Display)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    # Wait a moment for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar for errors
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar after F7: {status.message}")

    # Capture the result screen
    await capture_html_snapshot(sap_mcp_client, "se11_bapiret2_fields", overwrite=True)
    await capture_yaml_snapshot(sap_mcp_client, "se11_bapiret2_fields", overwrite=True)

    # YAML snapshot saved to file
    print("=" * 80)
    print("YAML SNAPSHOT saved")
    print("=" * 80)

    # Go back with F3
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F3 failed: {keyboard.error}"


@pytest.mark.anyio
async def test_se11_table_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test SE11 behavior when table doesn't exist - capture error state.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE11
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Fill with non-existent table
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Datenbanktabelle": "ZZZNOTEXIST"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 (Display)
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    # This might return an error - that's expected

    # Wait a moment
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar - should show error
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar for non-existent table: {status.message}")

    # Capture the error state
    await capture_yaml_snapshot(sap_mcp_client, "se11_table_not_found", overwrite=True)


# =============================================================================
# sap_se11_lookup Tool Integration Tests
# =============================================================================


@pytest.mark.anyio
async def test_se11_lookup_single_table(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with a single table."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up T000 table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": "T000", "object_type": "table"},
        SE11Result,
    )

    assert result.success is True, f"Lookup failed: {result.error}"
    assert len(result.entries) == 1, f"Expected 1 entry, got {len(result.entries)}"
    assert len(result.errors) == 0, f"Unexpected errors: {result.errors}"

    entry = result.entries[0]
    assert entry.name == "T000"
    assert entry.object_type == "table"
    # Accept German "Mandant" or English "Client" description
    desc = entry.description.lower()
    assert "mandant" in desc or "client" in desc, f"Unexpected description: {entry.description}"
    assert len(entry.fields) > 0

    # Check MANDT field
    mandt = next((f for f in entry.fields if f.name == "MANDT"), None)
    assert mandt is not None, "MANDT field not found"
    assert mandt.datatype == "CLNT"
    assert mandt.is_key is True


@pytest.mark.anyio
async def test_se11_lookup_table_list(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with a list of tables."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up multiple tables directly (no prior lookup)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": ["T000", "T001"], "object_type": "table"},
        SE11Result,
    )

    assert result.success is True, f"Lookup failed: {result.error}"
    assert len(result.entries) == 2, f"Expected 2 entries, got {len(result.entries)}. Errors: {result.errors}"

    names = {e.name for e in result.entries}
    assert "T000" in names
    assert "T001" in names


@pytest.mark.anyio
async def test_se11_lookup_table_not_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with non-existent table."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up non-existent table
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": "ZZZNOTEXIST99", "object_type": "table"},
        SE11Result,
    )

    # Should have success=False since all lookups failed
    assert result.success is False
    assert len(result.entries) == 0
    assert len(result.errors) == 1

    error = result.errors[0]
    assert error.name == "ZZZNOTEXIST99"
    assert "not found" in error.error.lower()


@pytest.mark.anyio
async def test_se11_lookup_mixed_results(sap_mcp_client: ClientSession) -> None:
    """Test sap_se11_lookup with mix of existing and non-existing tables."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Look up mix of tables
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": ["T000", "ZZZNOTEXIST99"], "object_type": "table"},
        SE11Result,
    )

    # Should have success=True since at least one succeeded
    assert result.success is True
    assert len(result.entries) == 1
    assert len(result.errors) == 1

    assert result.entries[0].name == "T000"
    assert result.errors[0].name == "ZZZNOTEXIST99"


@pytest.mark.anyio
async def test_se11_lookup_large_batch_to_file(sap_mcp_client: ClientSession, tmp_path: Path) -> None:
    """Test sap_se11_lookup with >10 tables using output_file parameter."""
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

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
    summary = await call_tool_typed(
        sap_mcp_client,
        "sap_se11_lookup",
        {"names": tables, "object_type": "table", "output_file": str(output_file)},
        SE11FileSummary,
    )

    # Should return SE11FileSummary, not SE11Result
    assert summary.output_file is not None, "Expected SE11FileSummary with output_file"
    assert summary.total_requested == 11
    assert summary.successful + summary.failed == 11
    assert summary.success is True, f"Batch lookup failed: {summary}"

    # Verify file was created and contains full results
    assert output_file.exists(), f"Output file not created: {output_file}"

    with open(output_file, encoding="utf-8") as f:
        full_result = json.load(f)

    assert full_result["success"] is True
    assert len(full_result["entries"]) == summary.successful
    assert len(full_result["errors"]) == summary.failed

    # Verify all requested tables are accounted for
    found_names = {e["name"] for e in full_result["entries"]}
    error_names = {e["name"] for e in full_result["errors"]}
    assert found_names | error_names == set(tables)


# --- Merged from test_sap_integration.py ---


@pytest.mark.anyio
async def test_se11_table_definition_t000(sap_mcp_client: ClientSession) -> None:
    """Test viewing table definition in SE11 using T000 (Clients table).

    SE11 (ABAP Dictionary) shows table structure/definition, not content.
    T000 is a simple table with well-known fields like MANDT, CCCATEGORY, etc.

    This test verifies:
    - SE11 can display table definition
    - The table fields are shown
    - We can capture the HTML for unit tests
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Capture SE11 initial screen
    await capture_html_snapshot(sap_mcp_client, "se11_initial")

    # "Datenbanktabelle" is a radio button, click it then Tab to the text field
    await call_tool_typed(sap_mcp_client, "browser_click", {"selector": "text=Datenbanktabelle"}, ClickResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 300})
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Tab"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_keyboard", {"text": "T000"})

    # Press F7 (Anzeigen/Display) to view table definition
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture table structure HTML
    await capture_html_snapshot(sap_mcp_client, "se11_t000_content")

    # Verify we're on the table definition screen
    page_html = (await get_html_content(sap_mcp_client)).upper()

    # T000 definition should show field names like MANDT, CCCATEGORY
    has_mandt = "MANDT" in page_html
    has_fields = "FIELD" in page_html or "COMPONENT" in page_html or "CCCATEGORY" in page_html

    assert has_mandt or has_fields, (
        "SE11 T000 definition should show table fields. " "Expected MANDT or other field indicators in the page."
    )
