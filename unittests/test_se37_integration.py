"""
Integration tests for SE37 (Function Builder) lookup tool.

These tests run against a real SAP system to:
1. Capture YAML snapshots for parser development
2. Verify the sap_se37_lookup tool works correctly
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapwebguimcp.models import (
    FillFormResult,
    KeyboardResult,
    LoginResult,
    SnapshotResult,
    StatusBarInfo,
    TransactionResult,
)

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se37_exploration"


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
async def test_se37_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 initial screen snapshot.

    This test:
    1. Logs into SAP
    2. Opens SE37
    3. Captures the initial selection screen
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE37
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    # Capture initial SE37 screen
    await capture_yaml_snapshot(sap_mcp_client, "se37_initial", overwrite=True)

    print("=" * 80)
    print("SE37 initial screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_capture_rfc_read_table(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 details for RFC_READ_TABLE function module.

    RFC_READ_TABLE is a well-known function module for reading table data.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE37
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill function module name field
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "RFC_READ_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "RFC_READ_TABLE"}},
            FillFormResult,
        )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function Module": "RFC_READ_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to display
    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture the main details screen (Properties tab)
    await capture_yaml_snapshot(sap_mcp_client, "se37_rfc_read_table_main", overwrite=True)

    # Check status bar
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar: {status.message}")

    print("=" * 80)
    print("RFC_READ_TABLE main screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_capture_rfc_read_table_import(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 Import parameters tab for RFC_READ_TABLE.
    """
    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Go to SE37
    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill function module name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "RFC_READ_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "RFC_READ_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to display
    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Import tab using CSS selector for tab role
    # German tab names: Import, Export, Changing, Tabellen, Ausnahmen
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Import')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture the Import parameters screen
    await capture_yaml_snapshot(sap_mcp_client, "se37_rfc_read_table_import", overwrite=True)

    print("=" * 80)
    print("RFC_READ_TABLE Import parameters snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_capture_rfc_read_table_export(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 Export parameters tab for RFC_READ_TABLE.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "RFC_READ_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "RFC_READ_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Export tab
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Export')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await capture_yaml_snapshot(sap_mcp_client, "se37_rfc_read_table_export", overwrite=True)

    print("=" * 80)
    print("RFC_READ_TABLE Export parameters snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_capture_rfc_read_table_tables(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 Tables parameters tab for RFC_READ_TABLE.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "RFC_READ_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "RFC_READ_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Tables tab (German: Tabellen)
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Tabellen')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await capture_yaml_snapshot(sap_mcp_client, "se37_rfc_read_table_tables", overwrite=True)

    print("=" * 80)
    print("RFC_READ_TABLE Tables parameters snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_capture_rfc_read_table_exceptions(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 Exceptions tab for RFC_READ_TABLE.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "RFC_READ_TABLE"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "RFC_READ_TABLE"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on Exceptions tab (German: Ausnahmen)
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='tab']:has-text('Ausnahmen')"},
    )

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await capture_yaml_snapshot(sap_mcp_client, "se37_rfc_read_table_exceptions", overwrite=True)

    print("=" * 80)
    print("RFC_READ_TABLE Exceptions snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_capture_bapi_user_get_detail(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 details for BAPI_USER_GET_DETAIL function module.

    This is a common BAPI for user data retrieval.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "BAPI_USER_GET_DETAIL"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "BAPI_USER_GET_DETAIL"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    await capture_yaml_snapshot(sap_mcp_client, "se37_bapi_user_get_detail_main", overwrite=True)

    print("=" * 80)
    print("BAPI_USER_GET_DETAIL main screen snapshot saved")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_function_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE37 behavior when function module doesn't exist.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill with non-existent function module
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Funktionsbaustein": "ZZZNOTEXIST_FM_99"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Function module": "ZZZNOTEXIST_FM_99"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to try to display
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar - should show error
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar for non-existent FM: {status.message}")

    await capture_yaml_snapshot(sap_mcp_client, "se37_not_found", overwrite=True)

    print("=" * 80)
    print("Function module not found snapshot saved")
    print("=" * 80)
