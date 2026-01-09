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

from sapwebguimcp.models import (
    FillFormResult,
    KeyboardResult,
    LoginResult,
    SnapshotResult,
    StatusBarInfo,
    TransactionResult,
)

from .conftest import call_tool_typed

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
    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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
    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "Enter"}, KeyboardResult)
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
    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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

    keyboard = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
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
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "Enter"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check status bar - should show error
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"Status bar for non-existent transaction: {status.message}")

    # Capture the error state
    await capture_yaml_snapshot(sap_mcp_client, "se93_not_found", overwrite=True)

    print("=" * 80)
    print("Transaction not found snapshot saved")
    print("=" * 80)
