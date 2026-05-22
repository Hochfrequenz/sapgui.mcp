"""
Exploratory tests for SM30 (Table Maintenance View) lookup tool.

These tests run against a real SAP system to capture YAML snapshots for
parser development. Run with SAP_LANGUAGE=DE and SAP_LANGUAGE=EN to get both.

Test views:
- V_T005 (Countries) - flat table, well-known, always has data
- V_T002 (Languages) - flat table, small
- ZZZNOTEXIST99 - non-existent view (error case)
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import FillFormResult, KeyboardResult, LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "sm30_exploration"


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


async def _login_and_navigate_to_sm30(client: ClientSession) -> None:
    """Login and navigate to SM30."""
    login = await call_tool_typed(client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(client, "sap_transaction", {"tcode": "SM30"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await client.call_tool("browser_wait", {"timeout": 1000})


async def _fill_view_name_and_display(client: ClientSession, view_name: str) -> None:
    """Fill the view name and click Display button."""
    # Try German label first, then English
    fill = await call_tool_typed(
        client,
        "sap_fill_form",
        {"fields": {"Tabelle/Sicht": view_name}},
        FillFormResult,
    )
    if not fill.filled:
        fill = await call_tool_typed(
            client,
            "sap_fill_form",
            {"fields": {"Table/View": view_name}},
            FillFormResult,
        )
    assert fill.filled, f"Fill form failed for view '{view_name}': not_found={fill.not_found}"

    # SM30: Click "Anzeigen"/"Display" button using JavaScript evaluation
    # SAP WebGUI buttons can be clicked by finding the button element with matching text
    from sapguimcp.backend.webgui.models.browser_results import EvaluateResult

    js_click = await call_tool_typed(
        client,
        "browser_evaluate",
        {"script": """(() => {
            const buttons = document.querySelectorAll('button, [role="button"], span[ct="BUTTON"]');
            for (const btn of buttons) {
                const text = btn.textContent || btn.getAttribute('title') || '';
                if (text.trim() === 'Anzeigen' || text.trim() === 'Display') {
                    btn.click();
                    return 'clicked';
                }
            }
            return 'not_found';
            })()"""},
        EvaluateResult,
    )
    assert js_click.success, f"JS click failed: {js_click.error}"

    await client.call_tool("browser_wait", {"timeout": 2000})


# =============================================================================
# Exploration Tests
# =============================================================================


@pytest.mark.anyio
async def test_sm30_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SM30 initial screen snapshot."""
    await _login_and_navigate_to_sm30(sap_mcp_client)
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm30_initial", overwrite=True)
    assert "Tabelle" in snapshot or "Table" in snapshot


@pytest.mark.anyio
async def test_sm30_capture_v_t005_countries(sap_mcp_client: ClientSession) -> None:
    """Capture SM30 display of V_T005 (Countries) - flat table view."""
    await _login_and_navigate_to_sm30(sap_mcp_client)
    await _fill_view_name_and_display(sap_mcp_client, "V_T005")
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm30_v_t005_display", overwrite=True)
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_sm30_capture_v_t002_languages(sap_mcp_client: ClientSession) -> None:
    """Capture SM30 display of V_T002 (Languages) - flat table view."""
    await _login_and_navigate_to_sm30(sap_mcp_client)
    await _fill_view_name_and_display(sap_mcp_client, "V_T002")
    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm30_v_t002_display", overwrite=True)
    assert len(snapshot) > 100


@pytest.mark.anyio
async def test_sm30_capture_not_found(sap_mcp_client: ClientSession) -> None:
    """Capture SM30 behavior for non-existent view."""
    await _login_and_navigate_to_sm30(sap_mcp_client)
    await _fill_view_name_and_display(sap_mcp_client, "ZZZNOTEXIST99")

    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    assert status.message is not None

    await capture_yaml_snapshot(sap_mcp_client, "sm30_not_found", overwrite=True)
