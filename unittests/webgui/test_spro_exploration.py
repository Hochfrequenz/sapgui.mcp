"""
Exploratory tests for SPRO (Customizing - Implementation Guide) search tool.

These tests run against a real SAP system to capture YAML snapshots for
parser development. Run with SAP_LANGUAGE=DE and SAP_LANGUAGE=EN to get both.

Exploration targets:
1. SPRO initial screen (before entering IMG)
2. IMG tree after clicking "SAP Referenz-IMG" / "SAP Reference IMG"
3. Search dialog (F5 / Ctrl+F / toolbar button - mechanism TBD)
4. Search results for a known keyword
5. Empty search results

Usage:
    SAP_LANGUAGE=DE pytest unittests/test_spro_exploration.py -v -s
    SAP_LANGUAGE=EN pytest unittests/test_spro_exploration.py -v -s
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import KeyboardResult, LoginResult, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "spro_exploration"


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


async def _login_and_navigate_to_spro(client: ClientSession) -> None:
    """Login and navigate to SPRO."""
    login = await call_tool_typed(client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(client, "sap_transaction", {"tcode": "SPRO"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await client.call_tool("browser_wait", {"timeout": 2000})


# =============================================================================
# Exploration Tests
# =============================================================================


@pytest.mark.anyio
async def test_spro_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SPRO initial screen before entering IMG tree."""
    await _login_and_navigate_to_spro(sap_mcp_client)
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_initial", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")


@pytest.mark.anyio
async def test_spro_capture_img_tree(sap_mcp_client: ClientSession) -> None:
    """Capture IMG tree after clicking 'SAP Referenz-IMG' / 'SAP Reference IMG'.

    First captures the initial screen to see button labels,
    then tries F5 (which is often the SAP Reference IMG shortcut in SPRO).
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Try F5 to enter SAP Reference IMG
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_img_tree", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")


@pytest.mark.anyio
async def test_spro_capture_search_via_ctrl_f(sap_mcp_client: ClientSession) -> None:
    """Try to open IMG search via Ctrl+F after entering the IMG tree.

    The search mechanism is unknown — this test tries Ctrl+F which is
    common for search dialogs in SAP WebGUI.
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Enter IMG tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Try Ctrl+F for search
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Ctrl+F"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_search_ctrlf", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")


@pytest.mark.anyio
async def test_spro_capture_search_via_f5_in_tree(sap_mcp_client: ClientSession) -> None:
    """Try to open IMG search via F5 once inside the IMG tree.

    In some SAP tree views, F5 triggers the Find function.
    We first enter the IMG tree, then try F5 again for search.
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Enter IMG tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Try F5 again for search within the tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_search_f5_in_tree", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")


@pytest.mark.anyio
async def test_spro_capture_search_via_button_click(sap_mcp_client: ClientSession) -> None:
    """Click the 'Suchen (Strg+F)' button directly to open the search dialog.

    Ctrl+F is intercepted by the browser, so we need to click the SAP toolbar
    button directly via JavaScript.
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Enter IMG tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Click "Suchen (Strg+F)" / "Find (Ctrl+F)" button via JS
    # SAP WebGUI buttons may use various HTML elements with title/aria-label
    from sapguimcp.backend.webgui.models.browser_results import EvaluateResult

    # First, discover what elements contain "Suchen" or "Find"
    discovery = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": """(() => {
            const results = [];
            const all = document.querySelectorAll('*');
            for (const el of all) {
                const text = el.textContent || '';
                const title = el.getAttribute('title') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const role = el.getAttribute('role') || '';
                const tag = el.tagName;
                if ((title.includes('Such') || title.includes('Find') ||
                     ariaLabel.includes('Such') || ariaLabel.includes('Find')) &&
                    !text.includes('Weiter such')) {
                    results.push({
                        tag: tag,
                        role: role,
                        title: title.substring(0, 80),
                        ariaLabel: ariaLabel.substring(0, 80),
                        id: el.id || '',
                        className: (el.className || '').substring(0, 80),
                        ct: el.getAttribute('ct') || ''
                    });
                }
            }
            return JSON.stringify(results.slice(0, 10));
        })()"""},
        EvaluateResult,
    )
    print(f"Search button discovery: {discovery.result}")

    # Try clicking via title attribute
    js_click = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": """(() => {
            // Try title attribute first (SAP WebGUI toolbar buttons often use title)
            let btn = document.querySelector('[title*="Such"][title*="Strg"]') ||
                      document.querySelector('[title*="Find"][title*="Ctrl"]') ||
                      document.querySelector('[aria-label*="Such"]') ||
                      document.querySelector('[aria-label*="Find"]');
            if (btn) {
                btn.click();
                return 'clicked via attr: ' + (btn.title || btn.getAttribute('aria-label'));
            }
            // Fallback: try all elements with matching role=button
            const buttons = document.querySelectorAll('[role="button"]');
            for (const b of buttons) {
                const label = b.getAttribute('aria-label') || b.textContent || '';
                if (label.includes('Such') || label.includes('Find')) {
                    b.click();
                    return 'clicked via role: ' + label.substring(0, 50);
                }
            }
            return 'not_found';
        })()"""},
        EvaluateResult,
    )
    print(f"Button click result: {js_click.result}")
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_search_dialog", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")


@pytest.mark.anyio
async def test_spro_capture_search_results(sap_mcp_client: ClientSession) -> None:
    """Execute a search for 'Land' and capture results.

    After clicking Search button, fills 'Suchbegriff' field with 'Land',
    clicks 'Weiter' to execute, and captures the result.
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Enter IMG tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Click search button
    from sapguimcp.backend.webgui.models.browser_results import EvaluateResult
    from sapguimcp.models import FillFormResult

    await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": """(() => {
            let btn = document.querySelector('[title*="Such"][title*="Strg"]') ||
                      document.querySelector('[title*="Find"][title*="Ctrl"]');
            if (btn) { btn.click(); return 'ok'; }
            return 'not_found';
        })()"""},
        EvaluateResult,
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Use browser_click to focus the search input, browser_keyboard to type,
    # then Enter to submit. This is the most SAP-friendly input approach.
    from sapguimcp.backend.webgui.models.browser_results import BrowserKeyboardResult, ClickResult

    # Click the input field to focus it
    click_input = await call_tool_typed(
        sap_mcp_client,
        "browser_click",
        {"selector": "[role='dialog'] input[role='textbox']"},
        ClickResult,
    )
    print(f"Click input: success={click_input.success}")
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Type search term character by character
    type_result = await call_tool_typed(
        sap_mcp_client,
        "browser_keyboard",
        {"text": "Land"},
        BrowserKeyboardResult,
    )
    print(f"Type result: success={type_result.success}")
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Capture snapshot to see if text was entered
    pre_snapshot = await call_tool_typed(sap_mcp_client, "browser_snapshot", {}, SnapshotResult)
    # Check if the textbox now has a value
    for line in pre_snapshot.snapshot.split("\n"):
        if "Suchbegriff" in line or "textbox" in line.lower() or "InputField" in line:
            print(f"  PRE-ENTER: {line.strip()}")

    # Press Enter to submit search
    enter_result = await call_tool_typed(
        sap_mcp_client,
        "browser_keyboard",
        {"key": "Enter"},
        BrowserKeyboardResult,
    )
    print(f"Enter result: success={enter_result.success}")
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 5000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_search_results_land", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")

    # Print interesting lines
    for line in snapshot.split("\n"):
        stripped = line.strip()
        if any(kw in stripped.lower() for kw in ["land", "country", "treffer", "found", "result"]):
            print(f"  MATCH: {stripped}")


@pytest.mark.anyio
async def test_spro_capture_search_results_country(sap_mcp_client: ClientSession) -> None:
    """Execute a search for 'country' and capture results.

    Uses 'country' which works better in EN (vs 'Land' which is DE-specific).
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Enter IMG tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Click search button
    from sapguimcp.backend.webgui.models.browser_results import BrowserKeyboardResult, ClickResult, EvaluateResult

    await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": """(() => {
            let btn = document.querySelector('[title*="Such"][title*="Strg"]') ||
                      document.querySelector('[title*="Find"][title*="Ctrl"]');
            if (btn) { btn.click(); return 'ok'; }
            return 'not_found';
        })()"""},
        EvaluateResult,
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Click input and type search term
    await call_tool_typed(
        sap_mcp_client,
        "browser_click",
        {"selector": "[role='dialog'] input[role='textbox']"},
        ClickResult,
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    await call_tool_typed(
        sap_mcp_client,
        "browser_keyboard",
        {"text": "country"},
        BrowserKeyboardResult,
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Press Enter to submit — SPRO search can be very slow on first run
    # (text index may need to be built if no one searched in EN before)
    await call_tool_typed(sap_mcp_client, "browser_keyboard", {"key": "Enter"}, BrowserKeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 120000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_search_results_country", overwrite=True)
    assert len(snapshot) > 100
    print(f"Snapshot length: {len(snapshot)} chars")

    # Print interesting lines
    for line in snapshot.split("\n"):
        stripped = line.strip()
        if any(kw in stripped.lower() for kw in ["country", "hit", "found", "result", "column"]):
            print(f"  MATCH: {stripped}")


@pytest.mark.anyio
async def test_spro_capture_toolbar_buttons(sap_mcp_client: ClientSession) -> None:
    """Capture IMG tree with focus on toolbar to identify available buttons.

    This helps discover the correct search mechanism and other navigation
    options available in the IMG tree toolbar.
    """
    await _login_and_navigate_to_spro(sap_mcp_client)

    # Enter IMG tree
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture the tree view — toolbar buttons should be visible in ARIA snapshot
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "spro_img_tree_buttons", overwrite=True)

    # Print buttons found in snapshot for analysis
    for line in snapshot.split("\n"):
        if "button" in line.lower():
            print(f"  BUTTON: {line.strip()}")

    assert len(snapshot) > 100
