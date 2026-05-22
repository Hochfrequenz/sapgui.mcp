"""
Exploratory tests for SM37 (Job Overview) tool.

These tests capture YAML accessibility snapshots from real SAP SM37 screens for:
1. Initial selection screen (with status checkboxes)
2. Job list results after executing
3. Job log detail (after selecting a job and clicking Jobprotokoll)
4. Empty results (no matching jobs)

Prerequisites: SAP system with some background jobs.
Run with: pytest unittests/test_sm37_exploration.py -v -s
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import SnapshotResult
from sapguimcp.models import LoginResult, StatusBarInfo, TransactionResult

from .conftest import call_tool_typed

YAML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "sm37_exploration"


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
async def test_sm37_capture_initial_screen(sap_mcp_client: ClientSession) -> None:
    """Capture SM37 initial selection screen snapshot."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm37_initial", overwrite=True)
    assert snapshot, "Snapshot should not be empty"
    assert "Jobname" in snapshot or "Job name" in snapshot, "Should be on SM37 screen"


@pytest.mark.anyio
async def test_sm37_capture_job_list(sap_mcp_client: ClientSession) -> None:
    """Capture SM37 job list results."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Jobname": "*", "Benutzername": "*"}},
    )

    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm37_job_list", overwrite=True)
    assert snapshot, "Snapshot should not be empty"


@pytest.mark.anyio
async def test_sm37_capture_job_log(sap_mcp_client: ClientSession) -> None:
    """Capture SM37 job log detail."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Jobname": "*", "Benutzername": "*"}},
    )

    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Select first row
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "[role='row']", "text": "", "index": 1},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Click Jobprotokoll button
    await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "button", "text": "Jobprotokoll"},
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm37_job_log", overwrite=True)
    assert snapshot, "Snapshot should not be empty"


@pytest.mark.anyio
async def test_sm37_capture_no_jobs_found(sap_mcp_client: ClientSession) -> None:
    """Capture SM37 behavior when no jobs match the filter."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    tx = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    assert tx.success, f"Transaction failed: {tx.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    await sap_mcp_client.call_tool(
        "sap_fill_form",
        {"fields": {"Jobname": "ZZZNOTEXIST_JOB_99", "Benutzername": "*"}},
    )

    await sap_mcp_client.call_tool("sap_press_key", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    snapshot = await capture_yaml_snapshot(sap_mcp_client, "sm37_no_jobs_found", overwrite=True)
    assert snapshot, "Snapshot should not be empty"
