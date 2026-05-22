"""
Exploratory tests for ST22 (Short Dump Analysis) tool.

These tests explore the ST22 interface against a real SAP system to understand:
1. The initial screen layout and date selection buttons
2. The dump list ALV grid structure (columns, rows)
3. The dump detail page (scrollable text sections)
4. DE and EN locale differences

Prerequisites: SAP system reachable. Dumps may or may not exist.
Run with SAP_LANGUAGE=DE and SAP_LANGUAGE=EN to capture both locale snapshots.
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "st22_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for ST22 development."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{base_name}_{language}.yaml"
    filepath = YAML_SNAPSHOTS_DIR / filename

    if not filepath.exists() or overwrite:
        YAML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")

    return yaml_content


async def _login_and_navigate_to_st22(client: ClientSession) -> None:
    """Login and navigate to ST22."""
    login = await call_tool_typed(client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(client, "sap_transaction", {"tcode": "ST22"}, TransactionResult)
    assert tx.success
    await client.call_tool("browser_wait", {"timeout": 2000})


# =============================================================================
# Exploration Tests
# =============================================================================


@pytest.mark.anyio
async def test_st22_01_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Step 1: Navigate to ST22, capture the initial screen (today's dumps)."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_initial")
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    # Assert we captured something meaningful
    assert len(snapshot) > 100
    assert status is not None


@pytest.mark.anyio
async def test_st22_02_yesterday_dumps(sap_mcp_client: ClientSession) -> None:
    """Step 2: Click 'Yesterday' button and capture dump list."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Click Yesterday button (DE: "Gestern", EN: "Yesterday")
    try:
        await sap_mcp_client.call_tool("browser_click", {"selector": "button", "text": "Gestern"})
    except Exception:
        await sap_mcp_client.call_tool("browser_click", {"selector": "button", "text": "Yesterday"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_yesterday_list")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_03_execute_today(sap_mcp_client: ClientSession) -> None:
    """Step 3: Press F8 (Execute) on initial screen to show today's dump list."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # ST22 might show today's dumps already, or we might need F8
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_today_executed")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_04_dump_detail(sap_mcp_client: ClientSession) -> None:
    """Step 4: Try to open first dump detail by double-clicking first data row."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # First capture the list to understand structure
    await capture_yaml_snapshot(sap_mcp_client, "st22_before_detail_click")

    # Try double-clicking the first row (index 1 = first data row after header)
    try:
        await sap_mcp_client.call_tool(
            "browser_click",
            {"selector": "row", "index": 1, "double_click": True},
        )
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})
    except Exception:
        # If row click fails, try clicking a cell in the grid
        try:
            await sap_mcp_client.call_tool(
                "browser_click",
                {"selector": "gridcell", "index": 0, "double_click": True},
            )
            await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})
        except Exception:
            pass

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_dump_detail")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_05_dump_detail_scrolled(sap_mcp_client: ClientSession) -> None:
    """Step 5: Scroll down in dump detail to capture more sections."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Try to open first dump detail
    try:
        await sap_mcp_client.call_tool(
            "browser_click",
            {"selector": "row", "index": 1, "double_click": True},
        )
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})
    except Exception:
        pass

    # Scroll down multiple times
    for _i in range(5):
        await sap_mcp_client.call_tool("sap_press_key", {"key": "PageDown"})
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_dump_detail_scrolled")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_06_click_today_count_button(sap_mcp_client: ClientSession) -> None:
    """Step 6: Click the dump count button next to 'Heute' (e.g. '1 Laufzeitfehler')."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # The "Heute" button is followed by a count button like "1 Laufzeitfehler"
    # Try clicking the count button (index 0 = first match for 'Laufzeitfehler')
    try:
        await sap_mcp_client.call_tool("browser_click", {"selector": "button", "text": "Laufzeitfehler", "index": 0})
    except Exception:
        # EN: "Runtime Errors"
        try:
            await sap_mcp_client.call_tool(
                "browser_click", {"selector": "button", "text": "Runtime Errors", "index": 0}
            )
        except Exception:
            pass
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_today_count_click")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_07_clear_user_and_execute(sap_mcp_client: ClientSession) -> None:
    """Step 7: Clear user field and execute to see all dumps."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Clear the Benutzer/User field to search for all users
    await sap_mcp_client.call_tool("sap_fill_form", {"fields": {"Benutzer": ""}})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Press F8 to execute
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_all_users_today")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_08_clear_user_via_keyboard(sap_mcp_client: ClientSession) -> None:
    """Step 8: Clear user field by clicking into it and clearing, then execute."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Click into the Benutzer field using set_field approach
    await sap_mcp_client.call_tool("sap_set_field", {"field_label": "Benutzer", "value": ""})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Press F8 to execute
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_cleared_user_f8")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_09_find_heute_dom(sap_mcp_client: ClientSession) -> None:
    """Step 9: Inspect DOM to find the Heute/Today button element details."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Inspect all elements containing "Heute" to understand the DOM structure
    js_code = """
    const results = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) {
        const el = walker.currentNode;
        const text = el.textContent || '';
        if ((text.includes('Heute') || text.includes('Today')) && text.length < 50) {
            results.push({
                tag: el.tagName,
                id: el.id,
                class: el.className,
                role: el.getAttribute('role'),
                ct: el.getAttribute('ct'),
                onclick: el.getAttribute('onclick'),
                text: text.trim().substring(0, 40),
                parentTag: el.parentElement?.tagName,
                parentId: el.parentElement?.id,
            });
        }
    }
    JSON.stringify(results.slice(0, 10), null, 2);
    """
    result = await sap_mcp_client.call_tool("browser_evaluate", {"expression": js_code})
    # Print result for inspection
    for content in result.content:
        if hasattr(content, "text"):
            # Don't print the full content to avoid encoding issues
            assert content.text is not None


@pytest.mark.anyio
async def test_st22_10_click_heute_sapui(sap_mcp_client: ClientSession) -> None:
    """Step 10: Click Heute button using SAP UI5 event dispatch."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # In SAP WebGUI, buttons are typically SPAN elements with ct="Button"
    # They respond to sapbi events, not standard click events
    # Try finding by text and using mousedown/mouseup events
    js_code = """
    const allElements = document.querySelectorAll('[ct="Button"], [role="button"], button');
    let found = null;
    for (const el of allElements) {
        if (el.textContent && el.textContent.trim() === 'Heute') {
            found = el;
            break;
        }
    }
    if (!found) {
        // Also check for "1 Laufzeitfehler" next to Heute
        for (const el of allElements) {
            if (el.textContent && el.textContent.trim().includes('Laufzeitfehler')) {
                found = el;
                break;
            }
        }
    }
    if (found) {
        // Simulate full mouse event sequence
        found.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
        found.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
        found.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        'dispatched events to: ' + found.textContent.trim();
    } else {
        'not found';
    }
    """
    result = await sap_mcp_client.call_tool("browser_evaluate", {"expression": js_code})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_heute_sapui_click")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_11_clear_user_fill_star(sap_mcp_client: ClientSession) -> None:
    """Step 11: Set user field to wildcard * and execute."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Try filling user field with * (wildcard) using sap_fill_form
    await sap_mcp_client.call_tool("sap_fill_form", {"fields": {"Benutzer": "*"}})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Press F8 to execute
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_wildcard_user")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_12_reset_then_execute(sap_mcp_client: ClientSession) -> None:
    """Step 12a: Click Zurucksetzen (reset) button then F8."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Use browser_evaluate to find and click Zurucksetzen/Reset button
    js_code = """
    const inputs = document.querySelectorAll('input');
    for (const inp of inputs) {
        if (inp.value === 'KLEINK') {
            // Focus the input, select all, delete
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(inp, '');
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
            // Also try the SAP-specific approach
            if (inp.id) {
                const sapEvent = new Event('sapenter', { bubbles: true });
                inp.dispatchEvent(sapEvent);
            }
            return 'cleared: ' + inp.id;
        }
    }
    return 'not found';
    """
    await sap_mcp_client.call_tool("browser_evaluate", {"expression": js_code})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Enter to submit the form changes
    await sap_mcp_client.call_tool("sap_press_key", {"key": "Enter"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # F8 to execute
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_reset_execute")
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_st22_13_clear_user_triple_click_delete(sap_mcp_client: ClientSession) -> None:
    """Step 12: Clear user field by triple-clicking and deleting, then F8."""
    await _login_and_navigate_to_st22(sap_mcp_client)

    # Find the user field input element and clear it using CSS selector + fill
    # The Benutzer textbox should have value KLEINK
    # Use browser_fill with the CSS selector for the input
    js_code = """
    const inputs = document.querySelectorAll('input');
    let result = [];
    for (const inp of inputs) {
        if (inp.value === 'KLEINK') {
            result.push({id: inp.id, name: inp.name, title: inp.title, type: inp.type, value: inp.value});
        }
    }
    JSON.stringify(result);
    """
    result = await sap_mcp_client.call_tool("browser_evaluate", {"expression": js_code})
    # The result should contain the ID of the user input field
    for content in result.content:
        if hasattr(content, "text"):
            assert content.text is not None

    # Try clearing with browser_fill using the input's CSS selector
    # First, find the ID
    js_find = """
    const inputs = document.querySelectorAll('input');
    for (const inp of inputs) {
        if (inp.value === 'KLEINK') {
            return inp.id;
        }
    }
    return '';
    """
    # Use a direct approach: clear via focus + selectAll + delete
    js_clear = """
    const inputs = document.querySelectorAll('input');
    for (const inp of inputs) {
        if (inp.value === 'KLEINK') {
            inp.focus();
            inp.select();
            document.execCommand('delete');
            return 'cleared: ' + inp.id;
        }
    }
    return 'not found';
    """
    result = await sap_mcp_client.call_tool("browser_evaluate", {"expression": js_clear})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Press F8 to execute
    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "st22_cleared_f8")
    assert len(snapshot) > 100
