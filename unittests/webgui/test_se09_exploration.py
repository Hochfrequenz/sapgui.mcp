"""
Exploratory tests for SE09 (Transport Organizer) tool.

These tests explore the SE09 screens against a real SAP system to capture
YAML accessibility snapshots for parser development.

Run with SAP_LANGUAGE=DE or SAP_LANGUAGE=EN to capture both locales:
  SAP_LANGUAGE=DE pytest unittests/test_se09_exploration.py -v -s
  SAP_LANGUAGE=EN pytest unittests/test_se09_exploration.py -v -s

IMPORTANT: SE09's tree control renders as flat text inside a region "Liste"
in the ARIA snapshot. F8 may not trigger display - use the "Anzeigen" button.
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import EvaluateResult, SnapshotResult
from sapguimcp.models import FillFormResult, LoginResult, TransactionResult
from sapguimcp.models.se09_models import TransportListResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "se09_exploration"


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

    return yaml_content


@pytest.mark.anyio
async def test_se09_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SE09 initial/selection screen."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se09_initial", overwrite=True)

    assert len(yaml_content) > 100
    assert "Transport Organizer" in yaml_content


@pytest.mark.anyio
async def test_se09_capture_transport_list(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 transport list after clicking Anzeigen button.

    Note: F8 does not reliably trigger display in SE09 WebGUI.
    The "Anzeigen" button must be clicked directly.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Click Anzeigen button directly (F8 is unreliable in SE09 WebGUI)
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": 'role=button[name="Anzeigen"]'},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se09_modifiable_only", overwrite=True)

    assert len(yaml_content) > 100


@pytest.mark.anyio
async def test_se09_capture_no_transports(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 with no matching transports (filter by non-existent user).
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill username with non-existent user
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Benutzer": "ZZZNOUSER99"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"User": "ZZZNOUSER99"}},
            FillFormResult,
        )

    # Click Anzeigen
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": 'role=button[name="Anzeigen"]'},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se09_no_transports", overwrite=True)

    assert len(yaml_content) > 50


@pytest.mark.anyio
async def test_se09_capture_expanded_tree(sap_mcp_client: ClientSession) -> None:
    """
    Capture SE09 transport list with tree fully expanded to show objects.

    After displaying transports, uses Ctrl+* (numpad) to expand all tree nodes,
    then captures the snapshot. This reveals tasks and objects (PROG, CLAS, TABL, etc.)
    underneath each transport request.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill username with KLEINK
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Benutzer": "KLEINK", "User": "KLEINK"}},
        FillFormResult,
    )

    # Click Anzeigen button
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": 'role=button[name="Anzeigen"]'},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # First capture: collapsed (normal) view
    await capture_yaml_snapshot(sap_mcp_client, "se09_kleink_collapsed", overwrite=True)

    # Expand all tree nodes by clicking the expand buttons (folder+ icons)
    # In the ARIA snapshot, these are unnamed "button" elements before each transport number.
    # Use JavaScript to find and click all tree node expand buttons.
    # The SE09 tree is an ABAP LIST output. Each line has:
    # - A button (expand icon) followed by a text node
    # We need to identify which buttons are for transport numbers (not section headers)
    # and click only those to expand them.
    #
    # Strategy: Find all [role="button"] + sibling text pairs in the region,
    # click only the button whose next text sibling matches a transport number pattern.
    # Inspect button HTML to understand expand/collapse icon rendering
    js_inspect_buttons = """(() => {
        const region = document.querySelector('[role="region"]');
        if (!region) return {error: 'no region found'};
        const children = [...region.children];
        const buttons = [];
        for (let i = 0; i < children.length; i++) {
            const el = children[i];
            if (el.getAttribute('role') !== 'button') continue;
            let nearbyText = '';
            for (let j = 1; j <= 3 && i + j < children.length; j++) {
                const t = children[i + j].textContent?.trim() || '';
                if (t) { nearbyText = t; break; }
            }
            // Check innerHTML, className, and child elements
            const innerImg = el.querySelector('img');
            const imgSrc = innerImg ? innerImg.src : null;
            buttons.push({
                index: i,
                id: el.id,
                className: el.className,
                innerHTML: el.innerHTML.substring(0, 200),
                nearbyText,
                imgSrc: imgSrc ? imgSrc.substring(imgSrc.lastIndexOf('/')) : null,
                title: el.title || el.getAttribute('aria-label') || ''
            });
        }
        return {buttonCount: buttons.length, buttons};
    })()"""

    import json

    structure_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_inspect_buttons},
        EvaluateResult,
    )
    print(f"Button inspection:\n{json.dumps(structure_result.result, indent=2, default=str)}")

    # Click expand buttons one at a time, tracking already-expanded numbers
    # to avoid re-clicking (which would collapse). Re-query DOM after each click
    # since SAP re-renders the list. This handles both transport requests AND tasks.
    expanded_numbers: set[str] = set()
    total_expanded = 0
    for _ in range(30):  # safety limit
        # Pass already-expanded numbers to JS to skip them
        skip_list = json.dumps(list(expanded_numbers))
        js_click_next = f"""(() => {{
            const region = document.querySelector('[role="region"]');
            if (!region) return {{error: 'no region found'}};
            const children = [...region.children];
            const skip = new Set({skip_list});
            const transportPattern = /^[A-Z0-9]{{3}}K\\d{{6}}$/;
            for (let i = 0; i < children.length; i++) {{
                const el = children[i];
                if (el.getAttribute('role') !== 'button') continue;
                for (let j = 1; j <= 3 && i + j < children.length; j++) {{
                    const sibText = children[i + j].textContent?.trim() || '';
                    if (transportPattern.test(sibText) && !skip.has(sibText)) {{
                        el.click();
                        return {{clicked: sibText, remaining: true}};
                    }}
                }}
            }}
            return {{clicked: null, remaining: false}};
        }})()"""

        result = await call_tool_typed(
            sap_mcp_client,
            "browser_evaluate",
            {"script": js_click_next},
            EvaluateResult,
        )
        result_data = result.result
        if isinstance(result_data, str):
            result_data = json.loads(result_data)
        print(f"Expand step: {result_data}")
        if not result_data or not result_data.get("remaining"):
            break
        expanded_numbers.add(result_data["clicked"])
        total_expanded += 1
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    print(f"Total transport/task expanded: {total_expanded}, numbers: {expanded_numbers}")

    # Second pass: expand object category buttons (e.g., "Programm", "Tabellentyp")
    # These are buttons next to non-transport-number text, deeper in the tree.
    # We skip section headers by checking the button's column position in its ID.
    # Second pass: expand object category buttons using button IDs as skip key
    expanded_button_ids: set[str] = set()
    cat_expanded = 0
    for _ in range(50):  # safety limit
        skip_ids = json.dumps(list(expanded_button_ids))
        js_click_category = f"""(() => {{
            const region = document.querySelector('[role="region"]');
            if (!region) return {{clicked: null, remaining: false}};
            const children = [...region.children];
            const transportPattern = /^[A-Z0-9]{{3}}K\\d{{6}}$/;
            const skipIds = new Set({skip_ids});
            for (let i = 0; i < children.length; i++) {{
                const el = children[i];
                if (el.getAttribute('role') !== 'button') continue;
                if (skipIds.has(el.id)) continue;
                // Skip section headers by column number in ID
                const idMatch = el.id.match(/:(\\d+)$/);
                if (!idMatch) continue;
                const colNum = parseInt(idMatch[1]);
                if (colNum < 20) continue;
                // Find nearby text - skip if it's a transport number
                for (let j = 1; j <= 3 && i + j < children.length; j++) {{
                    const sibText = children[i + j].textContent?.trim() || '';
                    if (sibText && !transportPattern.test(sibText)) {{
                        el.click();
                        return {{clicked: sibText, buttonId: el.id, remaining: true}};
                    }}
                    if (sibText) break;
                }}
            }}
            return {{clicked: null, remaining: false}};
        }})()"""

        result = await call_tool_typed(
            sap_mcp_client,
            "browser_evaluate",
            {"script": js_click_category},
            EvaluateResult,
        )
        result_data = result.result
        if isinstance(result_data, str):
            result_data = json.loads(result_data)
        print(f"Category expand: {result_data}")
        if not result_data or not result_data.get("remaining"):
            break
        expanded_button_ids.add(result_data["buttonId"])
        cat_expanded += 1
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    print(f"Total categories expanded: {cat_expanded}")

    # Use JS to extract ALL text content from the region (not just visible portion)
    js_extract_all = """(() => {
        const region = document.querySelector('[role="region"]');
        if (!region) return {error: 'no region found'};
        const children = [...region.children];
        const items = [];
        for (const el of children) {
            const role = el.getAttribute('role');
            const text = el.textContent?.trim() || '';
            if (text || role === 'button' || role === 'img') {
                items.push({role: role || 'div', text, id: el.id});
            }
        }
        return {totalChildren: children.length, items};
    })()"""

    extract_result = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": js_extract_all},
        EvaluateResult,
    )
    result_data = extract_result.result
    if isinstance(result_data, str):
        result_data = json.loads(result_data)
    print(f"Total children: {result_data.get('totalChildren')}")
    print(f"Items with content: {len(result_data.get('items', []))}")
    for item in result_data.get("items", []):
        if item["text"]:
            print(f"  [{item['role']}] {item['text'][:80]}")

    # Also capture YAML snapshot (even though only visible portion)
    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se09_kleink_expanded", overwrite=True)
    assert len(yaml_content) > 100
    print(f"Expanded snapshot size: {len(yaml_content)} chars")


@pytest.mark.anyio
async def test_se09_find_customizing_transports(sap_mcp_client: ClientSession) -> None:
    """Find users with customizing transports for integration test setup.

    This exploration test queries SE09 for customizing-only transports
    without a user filter to discover which users have them.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE09"}, TransactionResult)
    assert tx.success

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill username with * (wildcard)
    await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Benutzer": "*", "User": "*"}},
        FillFormResult,
    )

    # Uncheck Workbench, keep only Customizing
    try:
        await sap_mcp_client.call_tool("sap_set_checkbox", {"label": "Workbench", "checked": False})
    except Exception:
        pass

    # Check both modifiable and released
    try:
        await sap_mcp_client.call_tool("sap_set_checkbox", {"label": "Freigegeben", "checked": True})
    except Exception:
        try:
            await sap_mcp_client.call_tool("sap_set_checkbox", {"label": "Released", "checked": True})
        except Exception:
            pass

    # Click Anzeigen
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": 'role=button[name="Anzeigen"]'},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    yaml_content = await capture_yaml_snapshot(sap_mcp_client, "se09_customizing_wildcard", overwrite=True)
    print(f"Customizing wildcard snapshot ({len(yaml_content)} chars):")
    print(yaml_content[:2000])
