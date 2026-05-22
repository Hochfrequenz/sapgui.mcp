"""
Integration tests for SM30 (Table Maintenance View) lookup tool.

These tests run against a real SAP system to verify the sap_sm30_lookup tool
works correctly end-to-end.
"""

import os

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import ClickResult
from sapguimcp.models import (
    DiscoveredButtons,
    FillFormResult,
    LoginResult,
    ScreenInfo,
    StatusBarInfo,
    TransactionResult,
)
from sapguimcp.models.sm30_models import SM30ViewResult

from .conftest import call_tool_typed
from .integration_helpers import capture_html_snapshot

# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.anyio
async def test_sm30_lookup_v_t005_countries(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_sm30_lookup with V_T005 (Countries) - a well-known flat table view.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm30_lookup",
        {"view_name": "V_T005"},
        SM30ViewResult,
    )

    assert result.success, f"SM30 lookup failed: {result.error}"
    assert result.view_name == "V_T005"
    assert result.view_type == "flat"
    assert len(result.columns) > 0
    assert result.row_count > 0
    assert len(result.rows) > 0

    # V_T005 should have country-related columns
    first_row = result.rows[0]
    assert len(first_row.values) == len(result.columns)


@pytest.mark.anyio
async def test_sm30_lookup_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_sm30_lookup with a non-existent view.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm30_lookup",
        {"view_name": "ZZZNOTEXIST99"},
        SM30ViewResult,
    )

    assert not result.success, "Expected failure for non-existent view"
    assert result.view_type == "unsupported"


# --- Merged from test_sap_integration.py ---


@pytest.mark.anyio
async def test_sm30_discover_buttons(sap_mcp_client: ClientSession) -> None:
    """
    Test button discovery in SM30 transaction.

    SM30 is the Table/View Maintenance transaction. After entering a table name,
    it shows buttons like "Pflegen" (Maintain) and "Anzeigen" (Display).

    This test:
    1. Opens SM30 transaction
    2. Enters a table name (EIPO - a simple customizing table)
    3. Discovers all buttons on the screen using JavaScript
    4. Verifies we can find the "Pflegen" or "Maintain" button
    5. Captures HTML snapshot for offline analysis

    This test is foundational for issue #99 (sap_discover_fields doesn't return buttons)
    and issue #101 (browser_click doesn't work for SAP buttons).
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open SM30 transaction
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM30"}, TransactionResult)
    assert tx_result.success, f"sap_transaction SM30 failed: {tx_result.error}"

    # Wait for SM30 to load - look for a more generic selector first
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture initial SM30 screen
    await capture_html_snapshot(sap_mcp_client, "sm30_initial")

    # Find and fill the table name field
    # SM30 has a field for "Table/View" (Tabelle/Sicht)
    fill_data = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Tabelle/Sicht": "EIPO", "Table/View": "EIPO"}},
        FillFormResult,
    )
    print(f"\nFill result for table name: {fill_data}")

    # Wait briefly for SAP to process
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Capture SM30 screen with table name entered
    await capture_html_snapshot(sap_mcp_client, "sm30_with_table")

    # Discover buttons using the sap_discover_buttons tool
    # This tests the new tool (addresses issue #99)
    buttons_data = await call_tool_typed(sap_mcp_client, "sap_discover_buttons", {}, DiscoveredButtons)
    assert buttons_data.success, f"sap_discover_buttons failed: {buttons_data.error}"

    buttons = buttons_data.buttons
    print(f"\nDiscovered {len(buttons)} buttons on SM30 screen:")
    for btn in buttons[:20]:  # Show first 20 buttons
        print(f"  - {btn.label or 'no-label'}: id={btn.id}, selector={btn.selector}")

    # Look for the "Pflegen" or "Maintain" button
    maintain_button = None
    for btn in buttons:
        label = (btn.label or "").lower()
        if "pflegen" in label or "maintain" in label:
            maintain_button = btn
            break

    # Also look for "Anzeigen" / "Display" button as alternative
    display_button = None
    for btn in buttons:
        label = (btn.label or "").lower()
        if "anzeigen" in label or "display" in label:
            display_button = btn
            break

    print(f"\nMaintain button found: {maintain_button}")
    print(f"Display button found: {display_button}")

    # Verify we found at least one of these buttons
    # This is the critical assertion for issues #99, #101
    assert maintain_button is not None or display_button is not None, (
        f"Expected to find 'Pflegen'/'Maintain' or 'Anzeigen'/'Display' button in SM30. "
        f"Found buttons: {[b.label for b in buttons[:20]]}"
    )

    # Verify button has required properties for clicking
    target_btn = maintain_button or display_button
    assert target_btn.id, f"Button should have an ID: {target_btn}"
    assert target_btn.selector, f"Button should have a selector: {target_btn}"


@pytest.mark.anyio
async def test_sm30_click_pflegen_button(sap_mcp_client: ClientSession) -> None:
    """
    Test clicking the Pflegen (Maintain) button in SM30 transaction.

    This test verifies that:
    1. We can discover SAP buttons using sap_discover_buttons tool
    2. We can click buttons using browser_click with the discovered selector
    3. Clicking "Pflegen" navigates to the table maintenance screen

    This test addresses issues:
    - #99 (sap_discover_fields doesn't return buttons -> use sap_discover_buttons)
    - #101 (browser_click doesn't work for SAP buttons with text selectors)
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open SM30 transaction
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM30"}, TransactionResult)
    assert tx_result.success, f"sap_transaction SM30 failed: {tx_result.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Fill the table name field
    fill_data = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Tabelle/Sicht": "EIPO", "Table/View": "EIPO"}},
        FillFormResult,
    )
    assert fill_data.success, f"Fill failed: {fill_data.error}"
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Discover buttons using the sap_discover_buttons tool
    buttons_data = await call_tool_typed(sap_mcp_client, "sap_discover_buttons", {}, DiscoveredButtons)
    assert buttons_data.success, f"sap_discover_buttons failed: {buttons_data.error}"
    buttons = buttons_data.buttons

    # Find the Pflegen (DE) / Edit (EN) button - the one for table maintenance
    # Note: In EN there may be two "Edit" buttons (menu and toolbar), we want the toolbar one
    # which appears after "Display" in the list
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    pflegen_button = None
    found_display = False

    for btn in buttons:
        label = (btn.label or "").lower()
        # In DE, look for "pflegen"
        if "pflegen" in label:
            pflegen_button = btn
            break
        # In EN, look for "Edit" that comes after "Display" (toolbar button, not menu)
        if "display" in label:
            found_display = True
        elif found_display and label == "edit":
            pflegen_button = btn
            break

    # Fallback: if we didn't find it with the smart logic, just take the first Edit after position 8
    # (skipping menu items like Table, Edit, Goto, System, Help which come first)
    if pflegen_button is None and sap_language == "EN":
        for i, btn in enumerate(buttons):
            label = (btn.label or "").lower()
            if i >= 8 and label == "edit":
                pflegen_button = btn
                break

    assert pflegen_button is not None, f"Pflegen/Edit button not found. Buttons: {[b.label for b in buttons]}"
    assert pflegen_button.id, f"Pflegen button should have ID: {pflegen_button}"
    assert pflegen_button.selector, f"Pflegen button should have selector: {pflegen_button}"

    print(f"\nFound Pflegen button: {pflegen_button}")

    # Get screen info before clicking
    info_before = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert info_before.success, f"sap_get_screen_info failed: {info_before.error}"
    title_before = info_before.title
    print(f"Screen title before click: {title_before}")

    # Click the Pflegen button using its selector (from sap_discover_buttons)
    btn_selector = pflegen_button.selector
    click_data = await call_tool_typed(sap_mcp_client, "browser_click", {"selector": btn_selector}, ClickResult)

    print(f"Click result: {click_data}")
    assert click_data.success, f"Click failed: {click_data.error}"

    # Wait for SAP to process the click
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture the result
    await capture_html_snapshot(sap_mcp_client, "sm30_after_click_pflegen")

    # Read the status bar - SAP shows a message about the table after clicking Pflegen
    status_data = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    assert status_data.success, f"sap_read_status_bar failed: {status_data.error}"

    status_type = status_data.type or "none"
    status_message = (status_data.message or "").lower()

    print(f"Status bar after click: type={status_type}, message={status_message}")

    # The status bar should contain EIPO - this proves the click worked
    # (SAP shows an error/info message about the table we tried to maintain)
    assert "eipo" in status_message, (
        f"Expected status bar to mention EIPO after clicking Pflegen. "
        f"Status: type={status_type}, message={status_message}"
    )
