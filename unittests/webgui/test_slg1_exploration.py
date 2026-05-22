"""
Exploratory tests for SLG1 (Application Log) tool.

These tests explore the SLG1 screens against a real SAP system to capture:
1. SLG1 selection screen (initial screen with filter fields)
2. SLG1 log list (ALV Tree Control with log headers)
3. SLG1 expanded log (tree node expanded to show messages)
4. SLG1 no results screen

Prerequisites:
- SAP system must have application logs
- Run with SAP_LANGUAGE=DE first, then SAP_LANGUAGE=EN to capture both locales
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import FillFormResult, KeyboardResult, LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "slg1_exploration"


async def capture_yaml_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for SLG1 development."""
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
async def test_slg1_01_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SLG1 selection screen (initial screen with filter fields)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_initial", overwrite=True)
    assert snapshot, "Snapshot should not be empty"
    assert len(snapshot) > 100, "Snapshot should have substantial content"


@pytest.mark.anyio
async def test_slg1_02_capture_log_list(sap_mcp_client: ClientSession) -> None:
    """
    Capture SLG1 log list result.

    Uses wildcard (*) object to find any logs in the system.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill object field with wildcard to find any logs
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekt": "*"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object": "*"}},
            FillFormResult,
        )

    # Execute (F8)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F8 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_log_list", overwrite=True)
    assert snapshot, "Snapshot should not be empty"
    assert len(snapshot) > 100, "Snapshot should have substantial content"


@pytest.mark.anyio
async def test_slg1_03_capture_expanded_log(sap_mcp_client: ClientSession) -> None:
    """
    Capture SLG1 tree with first log node expanded to show messages.

    This is the critical snapshot for understanding the ALV Tree Control structure.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Fill object field with wildcard
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekt": "*"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object": "*"}},
            FillFormResult,
        )

    # Execute (F8)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F8 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Try to expand the first tree node by clicking its expand icon
    # Try multiple selectors since ALV tree rendering varies
    try:
        await sap_mcp_client.call_tool(
            "browser_click",
            {"selector": "[role='treeitem'] img[title*='Expand']"},
        )
    except Exception:
        try:
            await sap_mcp_client.call_tool(
                "browser_click",
                {"selector": "[role='treeitem'] img[title*='Einblenden']"},
            )
        except Exception:
            # Try clicking the first treeitem directly
            try:
                await sap_mcp_client.call_tool(
                    "browser_click",
                    {"selector": "[role='treeitem']:first-child"},
                )
            except Exception:
                pass  # Will capture whatever state we're in

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_expanded_log", overwrite=True)
    assert snapshot, "Snapshot should not be empty"


@pytest.mark.anyio
async def test_slg1_04_capture_no_results(sap_mcp_client: ClientSession) -> None:
    """Capture SLG1 screen when no logs are found."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SLG1"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Use a non-existent log object
    fill = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Objekt": "ZZZNOTEXIST99"}},
        FillFormResult,
    )
    if not fill.success:
        fill = await call_tool_typed(
            sap_mcp_client,
            "sap_fill_form",
            {"fields": {"Object": "ZZZNOTEXIST99"}},
            FillFormResult,
        )

    # Execute (F8)
    keyboard = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    assert keyboard.success, f"Keyboard F8 failed: {keyboard.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "slg1_no_results", overwrite=True)
    status = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    assert snapshot, "Snapshot should not be empty"
    # The status bar should indicate no results or an error
    assert status.message, "Status bar should have a message"
