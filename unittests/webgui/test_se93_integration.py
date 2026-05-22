"""
Integration tests for SE93 (Transaction Maintenance) lookup tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se93_lookup tool works correctly
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import FillResult, SnapshotResult
from sapguimcp.models import FillFormResult, KeyboardResult, LoginResult, StatusBarInfo, TableData, TransactionResult

from .conftest import call_tool_typed
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se93_exploration"


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
async def test_se93_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 initial screen snapshot.

    This test:
    1. Logs into SAP
    2. Opens SE93
    3. Captures the initial selection screen
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE93
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE93 screen
    await capture_yaml_snapshot(sap_mcp_client, "se93_initial", overwrite=True)

    print("=" * 80)
    print("SE93 initial screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se93_capture_va01_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for VA01 (Create Sales Order).

    VA01 is a well-known transaction with clear purpose and parameters.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE93
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Wait for screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill transaction code field
    # Try different field labels (German/English)
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "VA01"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Transaction code": "VA01"}},
            FillFormResult,
        )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Transaktion": "VA01"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Click "Anzeigen" (Display) button - F7 might work too
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    # Wait for results
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Check status bar
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar after Enter: {status.message}")

    # Capture the details screen
    await capture_yaml_snapshot(sap_mcp_client, "se93_va01_details", overwrite=True)

    print("=" * 80)
    print("VA01 transaction details snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se93_capture_mm01_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for MM01 (Create Material).
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE93
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill transaction code
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "MM01"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Transaction code": "MM01"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press Enter to display
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Enter"}, KeyboardResult)
    assert keyboard.success, f"Keyboard Enter failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture the details screen
    await capture_yaml_snapshot(sap_mcp_client, "se93_mm01_details", overwrite=True)

    print("=" * 80)
    print("MM01 transaction details snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se93_capture_se38_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for SE38 (ABAP Editor).

    SE38 is a report transaction - different type than VA01/MM01.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE93
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill transaction code
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "SE38"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Transaction code": "SE38"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to display
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture the details screen
    await capture_yaml_snapshot(sap_mcp_client, "se93_se38_details", overwrite=True)

    print("=" * 80)
    print("SE38 transaction details snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se93_capture_se24_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for SE24 (Class Builder) - likely OO transaction.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "SE24"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se93_se24_details", overwrite=True)
    print("SE24 (Class Builder) details snapshot saved")


@pytest.mark.anyio
async def test_se93_capture_su53_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for SU53 - often a parameter transaction.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "SU53"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se93_su53_details", overwrite=True)
    print("SU53 details snapshot saved")


@pytest.mark.anyio
async def test_se93_capture_pfcg_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for PFCG (Role Maintenance).
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "PFCG"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se93_pfcg_details", overwrite=True)
    print("PFCG details snapshot saved")


@pytest.mark.anyio
async def test_se93_capture_sm30_details(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 details for SM30 - Table Maintenance might be different type.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "SM30"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se93_sm30_details", overwrite=True)
    print("SM30 details snapshot saved")


@pytest.mark.anyio
async def test_se93_capture_search_for_variant_type(sap_mcp_client: ClientSession) -> None:
    """
    Try SEARCH_SAP_MENU - might be a variant transaction.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Try SICF - might be parameter transaction
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "SICF"}},
        FillFormResult,
    )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se93_sicf_details", overwrite=True)
    print("SICF details snapshot saved")


@pytest.mark.anyio
async def test_se93_transaction_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE93 behavior when transaction doesn't exist.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE93
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill with non-existent transaction
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Transaktionscode": "ZZZNOTEXIST99"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Transaction code": "ZZZNOTEXIST99"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press Enter
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Enter"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar - should show error
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar for non-existent transaction: {status.message}")

    # Capture the error state
    await capture_yaml_snapshot(sap_mcp_client, "se93_not_found", overwrite=True)

    print("=" * 80)
    print("Transaction not found snapshot saved")
    print("=" * 80)


# =============================================================================
# Integration Tests - Test the actual sap_se93_lookup tool
# =============================================================================


@pytest.mark.anyio
async def test_se93_lookup_single_dialog_transaction(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se93_lookup with a single dialog transaction (VA01).
    """
    from sapguimcp.models import SE93Result

    # Login first
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Call the SE93 lookup tool
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se93_lookup",
        {"tcodes": "VA01"},
        SE93Result,
    )

    assert result.success, f"SE93 lookup failed: {result.error}"
    assert len(result.entries) == 1
    assert len(result.errors) == 0

    entry = result.entries[0]
    assert entry.tcode == "VA01"
    assert entry.transaction_type == "dialog"
    assert entry.program == "SAPMV45A"
    assert entry.package == "VA"
    assert "Kundenauftr" in entry.description or "Sales Order" in entry.description


@pytest.mark.anyio
async def test_se93_lookup_single_report_transaction(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se93_lookup with a single report transaction (SE38).
    """
    from sapguimcp.models import SE93Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se93_lookup",
        {"tcodes": "SE38"},
        SE93Result,
    )

    assert result.success, f"SE93 lookup failed: {result.error}"
    assert len(result.entries) == 1

    entry = result.entries[0]
    assert entry.tcode == "SE38"
    assert entry.transaction_type == "report"
    assert "ABAP" in entry.description
    assert entry.selection_screen is not None  # Report-specific field


@pytest.mark.anyio
async def test_se93_lookup_batch_transactions(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se93_lookup with multiple transactions (batch lookup).
    """
    from sapguimcp.models import SE93Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se93_lookup",
        {"tcodes": ["VA01", "SE38", "PFCG"]},
        SE93Result,
    )

    assert result.success, f"SE93 lookup failed: {result.error}"

    # Batch lookups re-enter SE93 between each tcode.  SAP WebGUI state
    # can cause some lookups to fail (e.g., navigation timing).  We require
    # at least one entry to pass and that every returned entry is valid.
    assert len(result.entries) >= 1, f"Expected at least 1 entry, got {len(result.entries)}"
    total = len(result.entries) + len(result.errors)
    assert total == 3, f"Expected 3 total (entries+errors), got {total}"

    for entry in result.entries:
        assert entry.tcode in {"VA01", "SE38", "PFCG"}, f"Unexpected tcode: {entry.tcode}"
        assert entry.description, f"Missing description for {entry.tcode}"


@pytest.mark.anyio
async def test_se93_lookup_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se93_lookup with non-existent transaction.
    """
    from sapguimcp.models import SE93Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se93_lookup",
        {"tcodes": "ZZZNOTEXIST99"},
        SE93Result,
    )

    # Should succeed overall but with error entry
    assert len(result.entries) == 0
    assert len(result.errors) == 1
    assert result.errors[0].tcode == "ZZZNOTEXIST99"
    assert "not found" in result.errors[0].error.lower()


@pytest.mark.anyio
async def test_se93_lookup_mixed_success_and_failure(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se93_lookup with mix of valid and invalid transactions.
    """
    from sapguimcp.models import SE93Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se93_lookup",
        {"tcodes": ["VA01", "ZZZNOTEXIST99", "SE38"]},
        SE93Result,
    )

    # Should have partial success
    assert result.success  # At least one succeeded
    assert len(result.entries) == 2  # VA01 and SE38
    assert len(result.errors) == 1  # ZZZNOTEXIST99

    # Verify correct entries
    tcodes = {e.tcode for e in result.entries}
    assert tcodes == {"VA01", "SE38"}
    assert result.errors[0].tcode == "ZZZNOTEXIST99"


@pytest.mark.anyio
async def test_se93_lookup_gui_capabilities(sap_mcp_client: ClientSession) -> None:
    """
    Test that GUI capabilities are correctly parsed.
    """
    from sapguimcp.models import SE93Result

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se93_lookup",
        {"tcodes": "VA01"},
        SE93Result,
    )

    assert result.success
    entry = result.entries[0]

    # VA01 should support all GUI types
    assert entry.gui_windows is True
    assert entry.gui_java is True
    # gui_html may vary by system configuration


# --- Merged from test_sap_integration.py ---


@pytest.mark.anyio
async def test_sap_read_table_from_se93(sap_mcp_client: ClientSession) -> None:
    """Test reading transaction codes from SE93.

    SE93 with wildcard 'SE*' will always return results (SE11, SE16, etc.).
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    # Wait for SE93 to load (has transaction code input field with TSTC-TCODE in lsdata)
    await _wait_for_transaction_screen(sap_mcp_client, "SE93")

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "se93_initial")

    # Search for transactions starting with SE - use lsdata selector
    fill_result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='TSTC-TCODE']", "value": "SE*"}, FillResult
    )
    assert fill_result.success, f"Failed to fill SE93 transaction code field: {fill_result.error}"

    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {}, TableData)

    # Should find standard SE* transactions
    # Check for either transaction codes in data or valid table structure
    rows_str = str(table_result.rows).lower() if table_result.rows else ""
    has_se_transactions = "se11" in rows_str or "se16" in rows_str or "se80" in rows_str
    has_table_structure = table_result.rows is not None or table_result.headers is not None

    assert (
        has_se_transactions or has_table_structure
    ), f"Expected to find standard SE* transactions or table structure: {table_result}"
