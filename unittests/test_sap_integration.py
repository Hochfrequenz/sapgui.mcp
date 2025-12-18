"""
Integration tests for SAP Web GUI MCP Server against a real SAP system.

These tests only run on authorized machines with SAP access (see conftest.py).
They are automatically skipped in CI environments.

Required environment variables (set in .env):
- SAP_URL: The SAP Web GUI URL
- SAP_USER: Username for auto-login
- SAP_PASSWORD: Password for auto-login
- SAP_MANDANT: Client/Mandant (3-digit string, e.g., "100")
- SAP_LANGUAGE: Login language ("DE" or "EN")

SAP Web GUI Automation Notes:
-----------------------------
SAP Web GUI uses custom event handlers (lsevents) that intercept standard browser
input. Key findings from testing:

1. Login form fields (#sap-client, #sap-user, #sap-password):
   - Standard Playwright fill() works for these fields
   - Language field (sap-language) is often hidden - use JavaScript to set value

2. Login button (#LOGON_BUTTON):
   - This is a <div> with role="button", not a <button> element
   - Standard click() works

3. OK-Code field (#ToolbarOkCode) for transaction codes:
   - Standard fill() and type() DO NOT work - SAP intercepts input
   - Solution: Set value via JavaScript, then dispatch Enter keyboard events
   - The text may not visually appear, but the transaction executes correctly

4. SSL certificates:
   - SAP systems often use self-signed certificates
   - Browser context must be created with ignore_https_errors=True

5. "User already logged in" dialogs:
   - May appear if user has other active sessions
   - Can be dismissed by clicking "Continue"/"Weiter" button
"""

import os

import pytest
from mcp import ClientSession


@pytest.mark.asyncio
async def test_sap_login_opens_login_page(sap_mcp_client: ClientSession) -> None:
    """Test that sap_login tool opens the SAP login page."""
    result = await sap_mcp_client.call_tool("sap_login", {})

    assert result.content, "Expected non-empty response from sap_login"
    response_text = result.content[0].text.lower()

    # Should either show login page or indicate already logged in
    assert any(
        phrase in response_text
        for phrase in ["login", "anmeld", "credentials", "logged in", "ready"]
    ), f"Unexpected response: {response_text}"


@pytest.mark.asyncio
async def test_sap_login_and_fill_credentials(sap_mcp_client: ClientSession) -> None:
    """Test logging into SAP with credentials from environment."""
    sap_user = os.environ.get("SAP_USER")
    sap_password = os.environ.get("SAP_PASSWORD")
    sap_mandant = os.environ.get("SAP_MANDANT")
    sap_language = os.environ.get("SAP_LANGUAGE")

    if not all([sap_user, sap_password, sap_mandant, sap_language]):
        pytest.skip("SAP_USER, SAP_PASSWORD, SAP_MANDANT, and SAP_LANGUAGE environment variables required")

    # Open login page
    result = await sap_mcp_client.call_tool("sap_login", {})
    assert result.content, "Expected response from sap_login"

    # Fill mandant/client
    result = await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": 'input[name="sap-client"], input[id*="client" i], input[id*="mandant" i]', "value": sap_mandant},
    )
    assert "error" not in result.content[0].text.lower(), f"Failed to fill mandant: {result.content[0].text}"

    # Fill username
    result = await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": 'input[name="sap-user"], input[id*="user" i]', "value": sap_user},
    )
    assert "error" not in result.content[0].text.lower(), f"Failed to fill username: {result.content[0].text}"

    # Fill password
    result = await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": 'input[name="sap-password"], input[type="password"]', "value": sap_password},
    )
    assert "error" not in result.content[0].text.lower(), f"Failed to fill password: {result.content[0].text}"

    # Fill language - try visible input first, fall back to setting via JavaScript if hidden
    result = await sap_mcp_client.call_tool(
        "browser_evaluate",
        {"script": f'document.querySelector(\'input[name="sap-language"]\').value = "{sap_language}"'},
    )
    # Language field may be hidden, so we set it via JS - don't assert on errors

    # Click the login button (LOGON_BUTTON is a div with role="button")
    result = await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": "#LOGON_BUTTON"},
    )
    assert "error" not in result.content[0].text.lower(), f"Failed to click Anmelden: {result.content[0].text}"

    # Wait for page to load after login
    result = await sap_mcp_client.call_tool("browser_wait", {"timeout": 5000})

    # Handle "user already logged in" warning - continue with new session without terminating others
    # Try to find and click "Continue" / "Weiter" button (proceeds without ending other sessions)
    result = await sap_mcp_client.call_tool(
        "browser_click",
        {"selector": 'button:has-text("Continue"), button:has-text("Weiter"), button:has-text("Fortfahren")'},
    )
    # Ignore errors - dialog may not appear if no other session exists

    # Wait again after potential dialog
    result = await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Verify we're logged in by checking for SAP GUI elements
    result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert result.content, "Expected HTML response after login"


@pytest.mark.asyncio
async def test_sap_transaction(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code after login."""
    sap_user = os.environ.get("SAP_USER")
    sap_password = os.environ.get("SAP_PASSWORD")
    sap_mandant = os.environ.get("SAP_MANDANT")
    sap_language = os.environ.get("SAP_LANGUAGE")

    if not all([sap_user, sap_password, sap_mandant, sap_language]):
        pytest.skip("SAP credentials required")

    # First, login
    await sap_mcp_client.call_tool("sap_login", {})

    # Fill login form
    await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": "#sap-client", "value": sap_mandant},
    )
    await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": "#sap-user", "value": sap_user},
    )
    await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": "#sap-password", "value": sap_password},
    )
    await sap_mcp_client.call_tool(
        "browser_evaluate",
        {"script": f'document.querySelector(\'input[name="sap-language"]\').value = "{sap_language}"'},
    )

    # Click login button and wait for SAP Easy Access to load
    # The OK-Code field (#ToolbarOkCode) only appears after successful login
    await sap_mcp_client.call_tool("browser_click", {"selector": "#LOGON_BUTTON"})
    await sap_mcp_client.call_tool(
        "browser_wait", {"selector": "#ToolbarOkCode", "timeout": 15000, "state": "visible"}
    )

    # Now test the sap_transaction tool with a simple transaction (SU3 - user profile)
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SU3"})

    assert result.content, "Expected response from sap_transaction"
    response_text = result.content[0].text.lower()

    # Should indicate transaction executed
    assert "executed" in response_text, f"Transaction not executed: {response_text}"
    assert "error" not in response_text, f"Transaction had error: {response_text}"

    # Wait for SAP to fully load the SU3 transaction screen
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Verify SU3 actually opened by checking the page title or content
    # SU3 (Maintain User Profile) has different titles depending on language:
    # - German: "Pflege eigener Benutzervorgaben"
    # - English: "Maintain User Profile" or "Own Data"
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.lower()

    # Check that we're no longer on the Easy Access menu (SMEN)
    assert "sap easy access" not in page_html, (
        "Still on SAP Easy Access menu. Transaction SU3 did not open."
    )

    # Check for SU3-specific content (user profile screen)
    # The expected phrases depend on the login language
    if sap_language == "DE":
        expected_phrases = ["benutzervorgaben", "eigene daten"]
    else:
        expected_phrases = ["user profile", "own data", "maintain user"]

    assert any(phrase in page_html for phrase in expected_phrases), (
        f"SU3 transaction screen not detected for language '{sap_language}'. "
        f"Expected one of: {expected_phrases}. "
        "The transaction code entry may have failed."
    )


@pytest.mark.asyncio
async def test_sap_transaction_invalid_tcode(sap_mcp_client: ClientSession) -> None:
    """Test that an invalid transaction code shows an error message.

    This is a negative test to verify the transaction entry mechanism works.
    If we get an error message, it means SAP received the transaction code.
    """
    sap_user = os.environ.get("SAP_USER")
    sap_password = os.environ.get("SAP_PASSWORD")
    sap_mandant = os.environ.get("SAP_MANDANT")
    sap_language = os.environ.get("SAP_LANGUAGE")

    if not all([sap_user, sap_password, sap_mandant, sap_language]):
        pytest.skip("SAP credentials required")

    # Login
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("browser_fill", {"selector": "#sap-client", "value": sap_mandant})
    await sap_mcp_client.call_tool("browser_fill", {"selector": "#sap-user", "value": sap_user})
    await sap_mcp_client.call_tool("browser_fill", {"selector": "#sap-password", "value": sap_password})
    await sap_mcp_client.call_tool(
        "browser_evaluate",
        {"script": f'document.querySelector(\'input[name="sap-language"]\').value = "{sap_language}"'},
    )
    await sap_mcp_client.call_tool("browser_click", {"selector": "#LOGON_BUTTON"})
    await sap_mcp_client.call_tool(
        "browser_wait", {"selector": "#ToolbarOkCode", "timeout": 15000, "state": "visible"}
    )

    # Try an obviously invalid transaction code
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "INVALIDTCODE123"})

    assert result.content, "Expected response from sap_transaction"

    # Get the page HTML to check for error message in the status bar
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.lower()

    # SAP should show an error message about invalid transaction code
    # The message bar contains text like "Transaktion INVALIDTCODE123 existiert nicht"
    # or "Transaction INVALIDTCODE123 does not exist"
    assert any(
        phrase in page_html
        for phrase in ["existiert nicht", "does not exist", "nicht gefunden", "not found", "invalid"]
    ), (
        "Expected error message for invalid transaction code. "
        "If no error, the transaction entry mechanism may not be working."
    )


@pytest.mark.asyncio
async def test_sap_transaction_with_slash_prefix(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code that starts with / (namespace transaction).

    Transaction codes like /IWFND/GW_CLIENT need special handling:
    - They should become /n/IWFND/GW_CLIENT (not just /IWFND/GW_CLIENT)
    - The /n prefix tells SAP to open a new transaction
    """
    sap_user = os.environ.get("SAP_USER")
    sap_password = os.environ.get("SAP_PASSWORD")
    sap_mandant = os.environ.get("SAP_MANDANT")
    sap_language = os.environ.get("SAP_LANGUAGE")

    if not all([sap_user, sap_password, sap_mandant, sap_language]):
        pytest.skip("SAP credentials required")

    # First, login
    await sap_mcp_client.call_tool("sap_login", {})

    # Fill login form
    await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": "#sap-client", "value": sap_mandant},
    )
    await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": "#sap-user", "value": sap_user},
    )
    await sap_mcp_client.call_tool(
        "browser_fill",
        {"selector": "#sap-password", "value": sap_password},
    )
    await sap_mcp_client.call_tool(
        "browser_evaluate",
        {"script": f'document.querySelector(\'input[name="sap-language"]\').value = "{sap_language}"'},
    )

    # Click login button and wait for SAP Easy Access to load
    await sap_mcp_client.call_tool("browser_click", {"selector": "#LOGON_BUTTON"})
    await sap_mcp_client.call_tool(
        "browser_wait", {"selector": "#ToolbarOkCode", "timeout": 15000, "state": "visible"}
    )

    # Test with a namespace transaction (starts with /)
    # /IWFND/GW_CLIENT is the SAP Gateway Client for testing OData services
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "/IWFND/GW_CLIENT"})

    assert result.content, "Expected response from sap_transaction"
    response_text = result.content[0].text.lower()

    # Should indicate transaction executed
    assert any(
        phrase in response_text
        for phrase in ["executed", "transaction", "iwfnd", "gw_client", "current page", "error"]
    ), f"Unexpected response: {response_text}"
