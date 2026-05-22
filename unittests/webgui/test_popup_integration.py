"""Integration tests for popup detection, dismiss, close, and SE38 error popup."""

import os

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import ClickResult
from sapguimcp.models import (
    ClosePopupResult,
    FillFormResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    TransactionResult,
)

from .conftest import call_tool_typed
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)


@pytest.mark.anyio
async def test_bp_popup_detection_and_dismiss(sap_mcp_client: ClientSession) -> None:
    """
    Test popup detection and dismissal in BP transaction.

    This test verifies the popup handling feature:
    1. Open BP transaction and press F5 (triggers "Switch to Person" popup)
    2. Dismiss the first popup to enter person creation mode
    3. Press F3 (Back) WITHOUT filling required fields
    4. This triggers a validation popup: "Die Daten des Geschäftspartners sind fehlerhaft"
    5. Verify that sap_press_key returns with popup info
    6. Capture HTML snapshot of the popup for offline testing
    7. Dismiss the popup using sap_close_popup with "Ja"
    8. Verify the popup was dismissed and we're back to BP initial screen

    Fixes:
    - #54: Popup dialogs blocking operations cause 30s timeouts
    - #44: "Daten geändert" (Data changed) popup blocks navigation
    - #57: Dialog closed unexpectedly - reliable popup interaction
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert tx_result.success, f"sap_transaction BP failed: {tx_result.error}"
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Press F5 to create a new person - this triggers a confirmation popup
    # "Wechsel in das Anlegen einer Person" (Switch to creating a person)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    kb_data = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F5"}, KeyboardResult)

    # Capture the F5 confirmation popup for debugging
    await capture_html_snapshot(sap_mcp_client, "bp_switch_to_person_popup", overwrite=True)

    # F5 should trigger the "Switch to Person" confirmation popup
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    yes_button = "Ja" if sap_language == "DE" else "Yes"

    if kb_data.popup:
        popup = kb_data.popup
        assert popup.message, f"F5 popup should have a message. Got: {popup}"
        # Message should mention "Person" or "Wechsel" (DE) / "Switch" (EN)
        assert (
            "Person" in popup.message or "Wechsel" in popup.message or "Switch" in popup.message
        ), f"F5 popup should mention 'Person', 'Wechsel' or 'Switch'. Got: {popup.message}"

        # Dismiss with "Ja"/"Yes" to proceed to person creation
        dismiss_data = await call_tool_typed(
            sap_mcp_client, "sap_close_popup", {"button": yes_button}, ClosePopupResult
        )
        assert dismiss_data.success, f"Dismiss should succeed. Result: {dismiss_data}"
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Wait for person form to load (name fields appear)
    await sap_mcp_client.call_tool(
        "browser_wait", {"selector": "label:has-text('Vorname'), label:has-text('First Name')", "timeout": 15000}
    )
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Press F3 (Back) WITHOUT filling any data - this triggers validation popup
    # Message: "Die Daten des Geschäftspartners sind fehlerhaft..."
    # Buttons: "Ja", "Nein"
    back_data = await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F3"}, KeyboardResult)

    # Always capture HTML to debug popup detection
    await capture_html_snapshot(sap_mcp_client, "bp_validation_popup", overwrite=True)

    # The popup should be detected
    assert back_data.popup, (
        f"Expected popup after F3 from empty BP form. Got: {back_data}. "
        "The popup should show a validation error. "
        "Check bp_validation_popup_*.html for the actual page state."
    )

    popup = back_data.popup

    # Verify popup has message (could be header title like "Beenden" or body text)
    assert popup.message, f"Popup should have a message. Got: {popup}"
    # Message should be at least a few characters (not empty)
    # Some popups just have a short title like "Beenden" (Exit) without body text
    assert len(popup.message) >= 3, f"Popup message should not be empty. Got: {popup.message}"

    # Should have "Ja"/"Yes" and "Nein"/"No" buttons
    buttons = popup.buttons or []
    button_labels = [b.label for b in buttons]
    assert len(buttons) >= 2, f"Popup should have at least 2 buttons. Got: {button_labels}"
    assert any(
        "Ja" in label or "Yes" in label for label in button_labels
    ), f"Should have 'Ja' or 'Yes' button. Got: {button_labels}"
    assert any(
        "Nein" in label or "No" in label for label in button_labels
    ), f"Should have 'Nein' or 'No' button. Got: {button_labels}"

    # Dismiss with "Ja"/"Yes" to go back without saving
    dismiss_data = await call_tool_typed(sap_mcp_client, "sap_close_popup", {"button": yes_button}, ClosePopupResult)

    # Check dismiss result
    assert dismiss_data.success, f"Dismiss should succeed. Result: {dismiss_data}"
    assert dismiss_data.popup_closed, f"Popup should be dismissed. Result: {dismiss_data}"
    assert dismiss_data.button_clicked in ("Ja", "Yes"), f"Should have clicked 'Ja' or 'Yes'. Result: {dismiss_data}"

    # Verify we're back to BP initial screen or SAP Easy Access
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Check the page title - should be BP or Easy Access
    screen_data = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert screen_data.success, f"sap_get_screen_info failed: {screen_data.error}"
    title = screen_data.title
    assert (
        "SAP" in title
        or "Geschäftspartner" in title
        or "Business Partner" in title
        or "Easy Access" in title
        or "Einstieg" in title
    ), f"Should be back to BP or SAP landing page. Got title: {title}"


@pytest.mark.anyio
async def test_se38_error_popup_with_body_message(sap_mcp_client: ClientSession, lang_strings: dict[str, str]) -> None:
    """
    Test popup detection with a detailed body message in SE38.

    Clicks "Create" with a non-existent program name to trigger a popup.
    Depending on SAP system configuration, this may be:
    - An error popup ("Fehler in der Objektbearbeitung" / "Error in Object Processing")
    - A package assignment popup ("Objekt kann nur in SAP-Paket angelegt werden")

    This verifies that:
    1. A popup is detected after the action
    2. Popup has a descriptive message
    3. Popup has at least one button
    4. Popup can be dismissed (via close button or first available button)
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open SE38 (ABAP Editor)
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE38"}, TransactionResult)
    assert tx_result.success, f"sap_transaction SE38 failed: {tx_result.error}"
    await _wait_for_transaction_screen(sap_mcp_client, "SE38")

    # Capture initial SE38 screen
    await capture_html_snapshot(sap_mcp_client, "se38_initial", overwrite=True)

    # Enter a non-existent program name (use bilingual label: Programm/Program)
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {"fields": {"Programm": "AAAAAAAAAAAAAAAAAAAA", "Program": "AAAAAAAAAAAAAAAAAAAA"}},
        FillFormResult,
    )
    assert fill_result.success, f"Fill program name failed: {fill_result.error}"

    # Click "Anlegen/Create" button - this triggers a popup
    create_label = lang_strings["create"]
    click_data = await call_tool_typed(
        sap_mcp_client,
        "browser_click",
        {"selector": f"span:has-text('{create_label}'), button:has-text('{create_label}')"},
        ClickResult,
    )

    # Capture the popup HTML for debugging
    await capture_html_snapshot(sap_mcp_client, "se38_error_popup", overwrite=True)

    # Check if popup was detected via the click result or needs manual check
    popup = click_data.popup
    if not popup:
        # Popup might not be in click result, check via sap_get_screen_info
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
        # Try to detect popup by checking screen info
        screen_data = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
        popup = screen_data.popup

    assert popup, (
        f"Expected popup after clicking {create_label} with non-existent program name. "
        f"Check se38_error_popup_*.html. Click result: {click_data}"
    )

    # Verify popup has a message (title + body)
    message = popup.message
    assert message, f"Popup should have a message. Got: {popup}"
    # The message should contain either the title or body text
    assert len(message) > 10, f"Popup message should be descriptive. Got: {message}"

    # Should have at least one button
    buttons = popup.buttons or []
    button_labels = [b.label for b in buttons]
    assert len(buttons) >= 1, f"Popup should have at least one button. Got: {button_labels}"

    # Dismiss popup: prefer close button (X), fall back to first available button
    close_button_id = popup.close_button_id
    if close_button_id:
        dismiss_data = await call_tool_typed(sap_mcp_client, "sap_close_popup", {"close": True}, ClosePopupResult)
        assert dismiss_data.success, f"Close should succeed. Result: {dismiss_data}"
    else:
        # Dismiss using the first available button
        first_button = button_labels[0]
        dismiss_data = await call_tool_typed(
            sap_mcp_client, "sap_close_popup", {"button": first_button}, ClosePopupResult
        )
        assert dismiss_data.success, f"Dismiss should succeed. Result: {dismiss_data}"

    # Verify popup was dismissed and we're not stuck
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})
    screen_data = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert screen_data.success, f"sap_get_screen_info failed: {screen_data.error}"
    assert screen_data.popup is None, f"Popup should be dismissed. Got: {screen_data.popup}"


@pytest.mark.anyio
async def test_popup_detection_without_popup(sap_mcp_client: ClientSession) -> None:
    """
    Test that tools work normally when no popup is present.

    Verifies that the popup detection doesn't interfere with normal operation.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Navigate to SE16 - should work without any popup
    data = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    assert data.success, f"sap_transaction SE16 failed: {data.error}"

    # Should NOT have popup
    assert data.popup is None, f"No popup expected on clean navigation. Got: {data}"


@pytest.mark.anyio
async def test_sap_close_popup_no_popup_present(sap_mcp_client: ClientSession) -> None:
    """
    Test that sap_close_popup handles the case when no popup is present.

    Should return an error message, not crash.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to dismiss when no popup is present
    data = await call_tool_typed(sap_mcp_client, "sap_close_popup", {"button": "Ja"}, ClosePopupResult)

    # Should fail gracefully
    assert not data.success, f"Should fail when no popup present: {data}"
    assert "no popup" in (data.error or "").lower(), f"Error should mention no popup: {data}"
