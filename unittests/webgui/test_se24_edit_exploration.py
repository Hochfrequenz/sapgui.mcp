"""
Exploratory tests for SE24 (Class Builder) EDIT workflow.

These tests explore the SE24 edit flow against a real SAP system to understand:
1. How to navigate to the source code of a specific method
2. How to switch to change mode
3. How to modify method source code in the editor
4. How to run syntax check (Ctrl+F2) and activate (Ctrl+F3)
5. What the status bar shows at each step (DE + EN)

Prerequisites: Create a simple test class ZCL_TEST_MCP_EDIT in SAP first,
with at least one public method (e.g., DO_SOMETHING).

Note: test_se24_edit_00_setup_create_method creates the method if needed.
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se24_edit_exploration"

# SE24 field label depends on language
_LANG = os.environ.get("SAP_LANGUAGE", "de").lower()
_CLASS_FIELD = "Objekttyp" if _LANG == "de" else "Object Type"


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


# =============================================================================
# Setup Test - ensures DO_SOMETHING method exists
# =============================================================================


@pytest.mark.anyio
async def test_se24_edit_00_setup_create_method(sap_mcp_client: ClientSession) -> None:
    """Step 0: Create the DO_SOMETHING method if it doesn't exist.

    In SE24 change mode, type method name in first empty grid row,
    then activate.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("sap_fill_form", {"fields": {_CLASS_FIELD: "ZCL_TEST_MCP_EDIT"}})

    # F6 for direct change mode
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F6"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Check if DO_SOMETHING already exists in the snapshot
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se24_edit_setup_check", overwrite=True)
    if "DO_SOMETHING" in snapshot:
        print("Method DO_SOMETHING already exists, skipping setup")
        return

    # Click first grid textbox and fill the method name
    await sap_mcp_client.call_tool(
        "browser_click", {"selector": "role=grid >> role=row >> role=gridcell >> role=textbox"}
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    await sap_mcp_client.call_tool("browser_keyboard", {"key": "Control+a"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 100})
    await sap_mcp_client.call_tool(
        "browser_fill", {"selector": "role=grid >> role=textbox >> nth=0", "value": "DO_SOMETHING"}
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "Enter"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se24_edit_after_method_add", overwrite=True)
    print(f"After adding method:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")

    # Activate with Ctrl+F3
    await sap_mcp_client.call_tool("sap_press_key", {"key": "Control+F3"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se24_edit_after_setup_activate", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"After setup activate - Status: {status.message}")


# =============================================================================
# Exploration Test - display class main view
# =============================================================================


@pytest.mark.anyio
async def test_se24_edit_01_display_class_main(sap_mcp_client: ClientSession) -> None:
    """Step 1: Navigate to SE24, display ZCL_TEST_MCP_EDIT, see main view."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE24"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("sap_fill_form", {"fields": {_CLASS_FIELD: "ZCL_TEST_MCP_EDIT"}})
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F7"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se24_edit_display_main", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE24 Display Mode - Main View")
    print(f"Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:3000]}")
    print("=" * 80)


# =============================================================================
# Integration Test - Round-trip edit via sap_se24_edit tool
# =============================================================================


@pytest.mark.anyio
async def test_se24_edit_round_trip(sap_mcp_client: ClientSession) -> None:
    """
    Integration test: edit ZCL_TEST_MCP_EDIT method, check, activate, then restore original.

    1. Login to SAP
    2. Call sap_se24_edit with modified source (add a comment)
    3. Verify success and activation
    4. Restore original source via sap_se24_edit
    5. Verify restoration succeeded
    """
    from sapguimcp.models.se24_edit_models import SE24EditResult

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # First edit: add a comment line
    modified_source = "  METHOD do_something.\n* MCP edit integration test.\n  ENDMETHOD."

    edit_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_edit",
        {
            "class_name": "ZCL_TEST_MCP_EDIT",
            "method_name": "DO_SOMETHING",
            "new_source": modified_source,
        },
        SE24EditResult,
    )

    print(f"Edit result: success={edit_result.success}, activated={edit_result.activated}")
    print(f"Check messages: {edit_result.check_messages}")
    if edit_result.error:
        print(f"Error: {edit_result.error}")

    assert edit_result.success, f"Edit failed: {edit_result.error}"
    assert edit_result.activated, "Class was not activated"
    assert edit_result.backup_source, "No backup source returned"

    # Restore original source
    original_source = edit_result.backup_source
    restore_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se24_edit",
        {
            "class_name": "ZCL_TEST_MCP_EDIT",
            "method_name": "DO_SOMETHING",
            "new_source": original_source,
        },
        SE24EditResult,
    )

    print(f"Restore result: success={restore_result.success}, activated={restore_result.activated}")
    assert restore_result.success, f"Restore failed: {restore_result.error}"
    assert restore_result.activated, "Restore was not activated"
