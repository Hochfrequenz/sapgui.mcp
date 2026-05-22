"""
Exploratory tests for SE37 (Function Module) EDIT workflow.

These tests explore the SE37 edit flow against a real SAP system to understand:
1. How to navigate to the source code tab
2. How to switch to change mode
3. How to modify source code in the editor
4. How to run syntax check (Ctrl+F2) and activate (Ctrl+F3)
5. What the status bar shows at each step (DE + EN)

Prerequisites: Create a simple test function module Z_TEST_MCP_EDIT in SAP first.
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se37_edit_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for edit workflow development."""
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


async def _login_and_navigate_to_fm(client: ClientSession, fm_name: str = "Z_TEST_MCP_EDIT") -> None:
    """Login, navigate to SE37, fill FM name, press F7 to display."""
    login = await call_tool_typed(client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success

    await client.call_tool("browser_wait", {"timeout": 1000})
    await client.call_tool("sap_fill_form", {"fields": {"Funktionsbaustein": fm_name}})
    await client.call_tool("sap_press_key", {"key": "F7"})
    await client.call_tool("browser_wait", {"timeout": 2000})


# =============================================================================
# Exploration Tests
# =============================================================================


@pytest.mark.anyio
async def test_se37_edit_01_display_fm_source(sap_mcp_client: ClientSession) -> None:
    """Step 1: Navigate to SE37, display Z_TEST_MCP_EDIT, go to Quelltext tab."""
    await _login_and_navigate_to_fm(sap_mcp_client)

    # Click Quelltext tab
    await sap_mcp_client.call_tool("browser_click", {"selector": "tab", "text": "Quelltext"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se37_edit_display_source")
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE37 Display Mode - Source Tab")
    print(f"Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_edit_02_change_mode_via_f6(sap_mcp_client: ClientSession) -> None:
    """Step 2: Use F6 from initial screen for direct change mode."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("sap_fill_form", {"fields": {"Funktionsbaustein": "Z_TEST_MCP_EDIT"}})

    # F6 for direct change mode (same as SE38)
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F6"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click Quelltext tab
    await sap_mcp_client.call_tool("browser_click", {"selector": "tab", "text": "Quelltext"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se37_edit_change_mode_f6")
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE37 Change Mode via F6 - Source Tab")
    print(f"Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_se37_edit_03_check_and_activate(sap_mcp_client: ClientSession) -> None:
    """Step 3: In change mode, run syntax check (Ctrl+F2) and activate (Ctrl+F3)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE37"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("sap_fill_form", {"fields": {"Funktionsbaustein": "Z_TEST_MCP_EDIT"}})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F6"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "tab", "text": "Quelltext"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Syntax check
    await sap_mcp_client.call_tool("sap_press_key", {"key": "Control+F2"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se37_edit_after_check")
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"After Check - Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")

    # Activate
    await sap_mcp_client.call_tool("sap_press_key", {"key": "Control+F3"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se37_edit_after_activate")
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"After Activate - Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")

    print("=" * 80)
    print("SE37 Check + Activate complete")
    print("=" * 80)


# =============================================================================
# Integration Test - Round-trip edit via sap_se37_edit tool
# =============================================================================


@pytest.mark.anyio
async def test_se37_edit_round_trip(sap_mcp_client: ClientSession) -> None:
    """
    Integration test: edit Z_TEST_MCP_EDIT FM, check, activate, then restore original.

    1. Login to SAP
    2. Call sap_se37_edit with modified source (add a comment)
    3. Verify success and activation
    4. Restore original source via sap_se37_edit
    5. Verify restoration succeeded
    """
    from sapguimcp.models.se37_edit_models import SE37EditResult

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # First edit: add a comment line
    modified_source = (
        "FUNCTION Z_TEST_MCP_EDIT.\n"
        '*"----------------------------------------------------------------------\n'
        '*"*"Lokale Schnittstelle:\n'
        '*"----------------------------------------------------------------------\n'
        "* MCP edit integration test.\n"
        "ENDFUNCTION."
    )

    edit_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se37_edit",
        {"function_module": "Z_TEST_MCP_EDIT", "new_source": modified_source},
        SE37EditResult,
    )

    print(f"Edit result: success={edit_result.success}, activated={edit_result.activated}")
    print(f"Check messages: {edit_result.check_messages}")
    if edit_result.error:
        print(f"Error: {edit_result.error}")

    assert edit_result.success, f"Edit failed: {edit_result.error}"
    assert edit_result.activated, "Function module was not activated"
    assert edit_result.backup_source, "No backup source returned"

    # Restore original source
    original_source = edit_result.backup_source
    restore_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se37_edit",
        {"function_module": "Z_TEST_MCP_EDIT", "new_source": original_source},
        SE37EditResult,
    )

    print(f"Restore result: success={restore_result.success}, activated={restore_result.activated}")
    assert restore_result.success, f"Restore failed: {restore_result.error}"
    assert restore_result.activated, "Restore was not activated"
