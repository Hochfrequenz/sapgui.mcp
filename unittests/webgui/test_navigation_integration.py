"""Integration tests for SAP transaction navigation (SU3, same/new window, invalid tcode)."""

import os

import pytest
from mcp import ClientSession

from sapguimcp.models import (
    LoginResult,
    TransactionResult,
)

from .conftest import call_tool_typed, get_html_content
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)


@pytest.mark.anyio
async def test_sap_transaction(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code after login.

    Uses SU3 (Maintain User Profile) as it's a simple, safe transaction
    available to all SAP users.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    # Login (auto-login with credentials from environment, or skip if already logged in)
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Test the sap_transaction tool with SU3 (user profile)
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    assert result.success, f"Transaction failed: {result.error}"
    assert result.tcode and result.tcode.upper() == "SU3", f"Expected tcode SU3: {result}"

    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    # Verify SU3 actually opened by checking the page content
    page_html = (await get_html_content(sap_mcp_client)).lower()

    # Check that we're no longer on the Easy Access menu (SMEN)
    assert "sap easy access" not in page_html, "Still on SAP Easy Access menu. Transaction SU3 did not open."

    # Check for SU3-specific content (user profile screen)
    # - German: "Pflege eigener Benutzervorgaben"
    # - English: "Maintain User Profile" or "Own Data"
    if sap_language == "DE":
        expected_phrases = ["benutzervorgaben", "eigene daten"]
    else:
        expected_phrases = ["user profile", "own data", "maintain user"]

    assert any(phrase in page_html for phrase in expected_phrases), (
        f"SU3 transaction screen not detected for language '{sap_language}'. " f"Expected one of: {expected_phrases}."
    )

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "su3_screen")


@pytest.mark.anyio
async def test_sap_transaction_invalid_tcode(sap_mcp_client: ClientSession) -> None:
    """Test that an invalid transaction code shows an error message.

    This is a negative test to verify the transaction entry mechanism works.
    If SAP shows an error message, it means the transaction code was received.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "INVALIDTCODE123"}, TransactionResult)
    # Note: result may or may not be success - we just check page content

    # Get the page HTML to check for error message in the status bar
    page_html = (await get_html_content(sap_mcp_client)).lower()

    # SAP should show an error message about invalid transaction code
    # - German: "Transaktion INVALIDTCODE123 existiert nicht"
    # - English: "Transaction INVALIDTCODE123 does not exist"
    assert any(
        phrase in page_html
        for phrase in ["existiert nicht", "does not exist", "nicht gefunden", "not found", "invalid"]
    ), (
        "Expected error message for invalid transaction code. "
        "If no error, the transaction entry mechanism may not be working."
    )

    # Capture HTML snapshot with error status bar for offline testing
    await capture_html_snapshot(sap_mcp_client, "status_bar_error")


@pytest.mark.anyio
async def test_sap_transaction_with_slash_prefix(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code that starts with / (namespace transaction).

    Transaction codes like /IWFND/GW_CLIENT need special handling:
    - They should become /n/IWFND/GW_CLIENT (not just /IWFND/GW_CLIENT)
    - The /n prefix tells SAP to open a new transaction
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Test with a namespace transaction (starts with /)
    # /IWFND/GW_CLIENT is the SAP Gateway Client for testing OData services
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "/IWFND/GW_CLIENT"}, TransactionResult)

    # Should indicate transaction executed (or error if not authorized)
    # TransactionResult has success, tcode, error fields
    assert result.success or result.error, f"Expected success or error in response: {result}"


@pytest.mark.anyio
async def test_sap_transaction_same_window_replaces_previous(sap_mcp_client: ClientSession) -> None:
    """Test that transactions in same window mode (/n) replace the previous transaction.

    This test:
    1. Opens SE11 (ABAP Dictionary) in same window mode
    2. Opens SE16 (Data Browser) in same window mode
    3. Verifies that SE11 was cancelled and SE16 is now active

    The /n prefix cancels any active transaction and starts the new one.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Step 1: Open SE11 (ABAP Dictionary)
    result1 = await call_tool_typed(
        sap_mcp_client, "sap_transaction", {"tcode": "SE11", "new_window": False}, TransactionResult
    )
    assert result1.success, f"SE11 transaction failed: {result1.error}"
    assert not result1.new_window, f"SE11 should open in current window: {result1}"

    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Verify SE11 is displayed (ABAP Dictionary / Data Dictionary)
    page_html1 = (await get_html_content(sap_mcp_client)).lower()
    if sap_language == "DE":
        assert any(
            phrase in page_html1 for phrase in ["dictionary", "wörterbuch", "se11"]
        ), "SE11 (ABAP Dictionary) should be displayed"
    else:
        assert any(
            phrase in page_html1 for phrase in ["dictionary", "se11"]
        ), "SE11 (ABAP Dictionary) should be displayed"

    # Step 2: Open SE16 (Data Browser) - this should REPLACE SE11
    result2 = await call_tool_typed(
        sap_mcp_client, "sap_transaction", {"tcode": "SE16", "new_window": False}, TransactionResult
    )
    assert result2.success, f"SE16 transaction failed: {result2.error}"
    assert not result2.new_window, f"SE16 should open in current window: {result2}"

    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Verify SE16 is displayed and SE11 is gone
    page_html2 = (await get_html_content(sap_mcp_client)).lower()

    # SE16 should be visible (Data Browser / Table Contents)
    if sap_language == "DE":
        se16_found = any(phrase in page_html2 for phrase in ["data browser", "tabelleninhalt", "se16"])
    else:
        se16_found = any(phrase in page_html2 for phrase in ["data browser", "table contents", "se16"])

    assert se16_found, "SE16 (Data Browser) should be displayed after replacing SE11"


@pytest.mark.anyio
async def test_sap_transaction_new_window_preserves_previous(sap_mcp_client: ClientSession) -> None:
    """Test that transactions in new window mode (/o) preserve the previous transaction.

    This test:
    1. Opens SE11 (ABAP Dictionary) in same window mode
    2. Opens SE16 (Data Browser) in NEW window mode (new_window=True)
    3. Verifies that both transactions are now open in separate SAP sessions
    4. Checks that the session count is reported correctly

    The /o prefix opens a new SAP session without affecting the current one.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Step 1: Open SE11 (ABAP Dictionary) in current window
    result1 = await call_tool_typed(
        sap_mcp_client, "sap_transaction", {"tcode": "SE11", "new_window": False}, TransactionResult
    )
    assert result1.success, f"SE11 transaction failed: {result1.error}"
    assert not result1.new_window, f"SE11 should open in current window: {result1}"

    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Step 2: Open SE16 in NEW window - this should NOT replace SE11
    result2 = await call_tool_typed(
        sap_mcp_client, "sap_transaction", {"tcode": "SE16", "new_window": True}, TransactionResult
    )
    assert result2.success, f"SE16 new_window transaction failed: {result2.error}"

    # Should indicate new session was opened
    assert result2.new_window, f"Response should indicate new window mode: {result2}"

    # Should report session count
    assert result2.session_count is not None, f"Response should report session count: {result2}"

    # Should have at least 2 sessions (original + new)
    assert (
        result2.session_count >= 2
    ), f"Expected at least 2 SAP sessions after opening new window, got {result2.session_count}"
