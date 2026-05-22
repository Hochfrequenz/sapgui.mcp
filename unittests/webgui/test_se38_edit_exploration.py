"""
Exploratory tests for SE38 (ABAP Report Editor) EDIT workflow.

These tests explore the SE38 edit flow against a real SAP system to understand:
1. How to switch from display to edit mode
2. How to modify source code in the editor
3. How to run syntax check (Ctrl+F2)
4. How to activate (Ctrl+F3)
5. What the status bar shows at each step

Prerequisites: Create a simple test report ZTEST_MCP_EDIT in SAP first.
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import FillFormResult, KeyboardResult, LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se38_edit_exploration"


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


async def capture_screenshot(
    client: ClientSession,
    name: str,
) -> None:
    """Capture a screenshot for visual verification."""
    screenshot_dir = YAML_SNAPSHOTS_DIR / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    filepath = screenshot_dir / f"{name}.png"
    await client.call_tool("browser_screenshot", {"path": str(filepath)})
    print(f"Saved screenshot: {filepath}")


# =============================================================================
# SE38 Edit Exploration Tests
# =============================================================================


@pytest.mark.anyio
async def test_se38_edit_01_display_report(sap_mcp_client: ClientSession) -> None:
    """
    Step 1: Navigate to SE38 and display the test report ZTEST_MCP_EDIT.
    Capture the display-mode screen.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture initial SE38 screen
    await capture_yaml_snapshot(sap_mcp_client, "se38_edit_initial", overwrite=True)

    # Fill program name
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "ZTEST_MCP_EDIT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Program": "ZTEST_MCP_EDIT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to display source code
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F7 failed: {keyboard.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture display mode
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se38_edit_display_mode", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE38 Display Mode")
    print(f"Status bar: {status.message}")
    print("=" * 80)


@pytest.mark.anyio
async def test_se38_edit_02_switch_to_edit_mode(sap_mcp_client: ClientSession) -> None:
    """
    Step 2: Display the report then switch to edit mode.
    In SE38, you can press the "Edit" pencil button or use Ctrl+F1 (Change/Display toggle).
    Capture the edit-mode screen to see what changes.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "ZTEST_MCP_EDIT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Program": "ZTEST_MCP_EDIT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F7 to display first
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F7"}, KeyboardResult)
    assert keyboard.success, f"F7 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Now try to switch to edit mode with Ctrl+F1 (Change/Display toggle)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Control+F1"}, KeyboardResult)
    assert keyboard.success, f"Ctrl+F1 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture edit mode
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se38_edit_edit_mode", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE38 Edit Mode (after Ctrl+F1)")
    print(f"Status bar: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_se38_edit_03_direct_change_mode(sap_mcp_client: ClientSession) -> None:
    """
    Step 3: Try going directly into change mode by pressing F6 (Change) instead of F7 (Display)
    from the SE38 initial screen. This might be a faster path.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "ZTEST_MCP_EDIT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Program": "ZTEST_MCP_EDIT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Press F6 to go directly into change mode (instead of F7 for display)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F6"}, KeyboardResult)
    assert keyboard.success, f"F6 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se38_edit_change_mode_direct", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE38 Change Mode (direct via F6)")
    print(f"Status bar: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")
    print("=" * 80)


@pytest.mark.anyio
async def test_se38_edit_04_read_editor_content(sap_mcp_client: ClientSession) -> None:
    """
    Step 4: Open in change mode and try to read the editor text content.
    Uses browser_get_html and browser_evaluate to inspect the editor element.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "ZTEST_MCP_EDIT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Program": "ZTEST_MCP_EDIT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Go into change mode
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F6"}, KeyboardResult)
    assert keyboard.success, f"F6 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Try to read editor content via JavaScript
    result = await sap_mcp_client.call_tool(
        "browser_evaluate",
        {"script": """
            (() => {
                // Try multiple strategies to find the editor content
                const strategies = [];

                // Strategy 1: textarea elements
                const textareas = document.querySelectorAll('textarea');
                for (const ta of textareas) {
                    if (ta.value && ta.value.trim().length > 0) {
                        strategies.push({strategy: 'textarea', id: ta.id, value: ta.value.substring(0, 500)});
                    }
                }

                // Strategy 2: elements with contenteditable
                const editables = document.querySelectorAll('[contenteditable="true"]');
                for (const el of editables) {
                    strategies.push({strategy: 'contenteditable', id: el.id, text: el.innerText?.substring(0, 500)});
                }

                // Strategy 3: SAP-specific editor elements
                const sapEditors = document.querySelectorAll('[id*="textedit"], [id*="TEC_cnt"], [id*="editor"]');
                for (const el of sapEditors) {
                    strategies.push({
                        strategy: 'sap-editor',
                        id: el.id,
                        tagName: el.tagName,
                        text: (el.value || el.innerText || el.textContent || '').substring(0, 500)
                    });
                }

                // Strategy 4: Check iframes
                const iframes = document.querySelectorAll('iframe');
                for (const iframe of iframes) {
                    try {
                        const doc = iframe.contentDocument;
                        if (doc) {
                            const body = doc.body;
                            strategies.push({
                                strategy: 'iframe',
                                id: iframe.id,
                                text: body?.innerText?.substring(0, 500)
                            });
                        }
                    } catch(e) {
                        strategies.push({strategy: 'iframe-blocked', id: iframe.id, error: e.message});
                    }
                }

                return JSON.stringify(strategies, null, 2);
            })()
        """},
    )
    print("=" * 80)
    print("Editor Content Discovery")
    for content in result.content:
        print(content.text if hasattr(content, "text") else str(content))
    print("=" * 80)


@pytest.mark.anyio
async def test_se38_edit_05_check_and_activate(sap_mcp_client: ClientSession) -> None:
    """
    Step 5: Open in change mode, then try:
    - Ctrl+F2 (Syntax Check)
    - Ctrl+F3 (Activate)
    Capture status bar after each to see the messages.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "ZTEST_MCP_EDIT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Program": "ZTEST_MCP_EDIT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Go into change mode
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F6"}, KeyboardResult)
    assert keyboard.success, f"F6 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Try syntax check (Ctrl+F2)
    print("--- Attempting Ctrl+F2 (Syntax Check) ---")
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Control+F2"}, KeyboardResult)
    assert keyboard.success, f"Ctrl+F2 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot_check = await capture_yaml_snapshot(sap_mcp_client, "se38_edit_after_check", overwrite=True)
    status_check = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"After Check - Status: {status_check.message}")
    print(f"Snapshot preview:\n{snapshot_check.encode('ascii', 'replace').decode()[:2000]}")

    # Try activate (Ctrl+F3)
    print("\n--- Attempting Ctrl+F3 (Activate) ---")
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Control+F3"}, KeyboardResult)
    assert keyboard.success, f"Ctrl+F3 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot_activate = await capture_yaml_snapshot(sap_mcp_client, "se38_edit_after_activate", overwrite=True)
    status_activate = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    print(f"After Activate - Status: {status_activate.message}")
    print(f"Snapshot preview:\n{snapshot_activate.encode('ascii', 'replace').decode()[:2000]}")

    print("=" * 80)
    print("SE38 Check + Activate complete")
    print("=" * 80)


@pytest.mark.anyio
async def test_se38_edit_06_select_all_and_replace(sap_mcp_client: ClientSession) -> None:
    """
    Step 6: Open in change mode, select all text (Ctrl+A), delete it,
    then type new source code. Verify the replacement worked.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "ZTEST_MCP_EDIT"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Program": "ZTEST_MCP_EDIT"}},
            FillFormResult,
        )
    assert fill.success, f"Fill form failed: {fill.error}"

    # Go into change mode
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F6"}, KeyboardResult)
    assert keyboard.success, f"F6 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click on the editor area first to ensure focus
    # Try clicking on a known editor element
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[id*='textedit'], [id*='TEC_cnt'], textarea, [contenteditable='true']"},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Select all text (Ctrl+A)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Control+a"}, KeyboardResult)
    print(f"Ctrl+A result: {keyboard.success}")
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Delete selected text
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Delete"}, KeyboardResult)
    print(f"Delete result: {keyboard.success}")
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Type new source code
    new_source = "REPORT ZTEST_MCP_EDIT.\nWRITE 'Hello from MCP edit test'."
    # We need to use browser_fill or browser_keyboard to type text
    # Try typing via keyboard
    for line in new_source.split("\n"):
        keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": line}, KeyboardResult)
        keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Enter"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "se38_edit_after_replace", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print("=" * 80)
    print("SE38 After Text Replacement")
    print(f"Status: {status.message}")
    print(f"Snapshot preview:\n{snapshot.encode('ascii', 'replace').decode()[:2000]}")
    print("=" * 80)


# =============================================================================
# Integration Test - Round-trip edit via sap_se38_edit tool
# =============================================================================


@pytest.mark.anyio
async def test_se38_edit_round_trip(sap_mcp_client: ClientSession) -> None:
    """
    Integration test: edit ZTEST_MCP_EDIT, check, activate, then restore original.

    1. Login to SAP
    2. Call sap_se38_edit with modified source (add a comment)
    3. Verify success and activation
    4. Restore original source via sap_se38_edit
    5. Verify restoration succeeded
    """
    from sapguimcp.models.se38_edit_models import SE38EditResult

    # Login
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # First edit: add a comment line
    modified_source = "REPORT ZTEST_MCP_EDIT.\n" "WRITE 'HELLO WORLD'.\n" "* MCP edit integration test."

    edit_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se38_edit",
        {"program_name": "ZTEST_MCP_EDIT", "new_source": modified_source},
        SE38EditResult,
    )

    print(f"Edit result: success={edit_result.success}, activated={edit_result.activated}")
    print(f"Check messages: {edit_result.check_messages}")
    if edit_result.error:
        print(f"Error: {edit_result.error}")

    assert edit_result.success, f"Edit failed: {edit_result.error}"
    assert edit_result.activated, "Report was not activated"
    assert edit_result.backup_source, "No backup source returned"

    # Restore original source
    original_source = edit_result.backup_source
    restore_result = await call_tool_typed(
        sap_mcp_client,
        "sap_se38_edit",
        {"program_name": "ZTEST_MCP_EDIT", "new_source": original_source},
        SE38EditResult,
    )

    print(f"Restore result: success={restore_result.success}, activated={restore_result.activated}")
    assert restore_result.success, f"Restore failed: {restore_result.error}"
    assert restore_result.activated, "Restore was not activated"
