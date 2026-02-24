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

from sapwebguimcp.models import FillFormResult, LoginResult, SnapshotResult, TransactionResult

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
