"""
Exploratory tests for abapGit integration.

These tests help us understand the abapGit UI structure to build
automated pull/push tools.

Run with: pytest unittests/test_abapgit_exploration.py -v -s
"""

import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapwebguimcp.models import (
    DiscoveredButtons,
    FormFieldsResult,
    LoginResult,
    ScreenText,
    SnapshotResult,
    TableData,
    TransactionResult,
)

from .conftest import call_tool_typed

EXPLORATION_DIR = Path(__file__).parent / "testdata" / "abapgit_exploration"


async def capture_snapshot(
    client: ClientSession,
    name: str,
    overwrite: bool = False,
) -> str:
    """Capture YAML accessibility snapshot for analysis."""
    result = await call_tool_typed(client, "browser_snapshot", {}, SnapshotResult)
    yaml_content = result.snapshot

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{name}_{language}.yaml"
    filepath = EXPLORATION_DIR / filename

    if not filepath.exists() or overwrite:
        EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(yaml_content, encoding="utf-8")
        print(f"\nSaved snapshot: {filepath}")

    return yaml_content


async def capture_screen_text(
    client: ClientSession,
    name: str,
    overwrite: bool = False,
) -> str:
    """Capture screen text for analysis."""
    result = await call_tool_typed(client, "sap_get_screen_text", {}, ScreenText)
    text_content = result.text

    language = os.environ.get("SAP_LANGUAGE", "de").lower()
    filename = f"{name}_{language}.txt"
    filepath = EXPLORATION_DIR / filename

    if not filepath.exists() or overwrite:
        EXPLORATION_DIR.mkdir(parents=True, exist_ok=True)
        filepath.write_text(text_content, encoding="utf-8")
        print(f"\nSaved screen text: {filepath}")

    return text_content


# =============================================================================
# Exploration Tests - Run these manually to understand abapGit UI
# =============================================================================


@pytest.mark.anyio
async def test_abapgit_open_transaction(sap_mcp_client: ClientSession) -> None:
    """Open ZABAPGIT and capture initial screen."""
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"
    print(f"\nLogged in as {login_result.user}")

    # Open ZABAPGIT
    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success, f"Transaction failed: {tx_result.error}"
    print(f"\nOpened transaction: {tx_result.tcode}")

    # Capture snapshots
    await capture_snapshot(sap_mcp_client, "zabapgit_initial", overwrite=True)
    await capture_screen_text(sap_mcp_client, "zabapgit_initial", overwrite=True)

    print("\n=== Initial abapGit screen captured ===")


@pytest.mark.anyio
async def test_abapgit_explore_repo_list(sap_mcp_client: ClientSession) -> None:
    """Explore the repository list structure."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Try to read table data (repos might be in a table/grid)
    table_result = await call_tool_typed(
        sap_mcp_client,
        "sap_read_table",
        {"max_rows": 50},
        TableData,
    )

    if table_result.success and table_result.rows:
        print(f"\n=== Found table with {len(table_result.rows)} rows ===")
        print(f"Columns: {table_result.columns}")
        for i, row in enumerate(table_result.rows[:5]):
            print(f"Row {i}: {row}")
    else:
        print(f"\nNo table found or empty: {table_result.error}")

    # Capture for analysis
    await capture_snapshot(sap_mcp_client, "zabapgit_repo_list", overwrite=True)
    await capture_screen_text(sap_mcp_client, "zabapgit_repo_list", overwrite=True)


@pytest.mark.anyio
async def test_abapgit_explore_buttons(sap_mcp_client: ClientSession) -> None:
    """Explore available buttons/actions in abapGit."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Discover buttons
    buttons_result = await call_tool_typed(
        sap_mcp_client,
        "sap_discover_buttons",
        {},
        DiscoveredButtons,
    )

    print("\n=== Available buttons ===")
    for btn in buttons_result.buttons:
        print(f"  {btn.label}: selector={btn.selector}, shortcut={btn.shortcut}")


@pytest.mark.anyio
async def test_abapgit_explore_form_fields(sap_mcp_client: ClientSession) -> None:
    """Explore form fields in abapGit."""
    # Login and open ZABAPGIT
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success

    tx_result = await call_tool_typed(
        sap_mcp_client,
        "sap_transaction",
        {"tcode": "ZABAPGIT"},
        TransactionResult,
    )
    assert tx_result.success

    # Discover form fields
    fields_result = await call_tool_typed(
        sap_mcp_client,
        "sap_get_form_fields",
        {},
        FormFieldsResult,
    )

    print("\n=== Form fields ===")
    for field in fields_result.fields:
        print(f"  {field.label}: type={field.field_type}, value={field.value}")
