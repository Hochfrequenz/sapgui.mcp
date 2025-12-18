"""
Integration tests for SAP Web GUI MCP Server against a real SAP system.

Test Philosophy:
----------------
These tests verify that the MCP server tools work correctly WITH a real SAP system.
They assume SAP is functioning correctly - if SAP is down or misbehaving, these
tests will fail, which is the desired behavior: you need to know if SAP is broken.

What these tests verify:
- MCP server starts and accepts tool calls via stdio protocol
- sap_login tool navigates to SAP and logs in automatically
- sap_transaction tool enters transaction codes correctly
- Browser state changes are observable via browser_get_html

What these tests assume (and don't test):
- SAP Web GUI is available and responding
- SAP credentials are valid
- SAP transactions (SU3, etc.) exist and are accessible to the test user

If tests fail, check:
1. Is SAP accessible? (network, VPN, firewall)
2. Are credentials correct and not expired?
3. Is the user locked or does it have required authorizations?
4. Is there a "user already logged in" dialog blocking the flow?

Tool Return Values:
-------------------
MCP tools return a CallToolResult with content containing text messages.

Example return values:
- sap_login: "Successfully logged into SAP as kleink. Ready to run transactions."
- sap_login: "Already logged in to SAP at https://... Ready to run transactions."
- sap_transaction: "Transaction SU3 executed. Current page: Pflege eigener..."
- browser_get_html: The full HTML of the current page
- browser_fill: "Filled #sap-client with: 100"
- browser_click: "Clicked element: #LOGON_BUTTON"

Testing Boundary:
-----------------
The test structure is:

    1. TOOL CALL (what the tool does internally)
       ├── Navigate to URL
       ├── Fill form fields
       ├── Click buttons
       └── Wait for elements

    2. TOOL RETURN (what we can assert on)
       └── Text message describing success/failure

    3. BROWSER STATE (what we can verify independently)
       └── HTML content via browser_get_html tool

We assert on BOTH:
- The tool return value (did it claim success?)
- The browser state (did the browser actually change?)

This two-step verification ensures the tool didn't just return "success" while
the browser is stuck on an error page.

Test Environment:
-----------------
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
   - Solution: Set value via JavaScript, then press Enter via Playwright keyboard
   - The text may not visually appear, but the transaction executes correctly
   - Transaction prefixes:
     - /n = Open in current window (cancels current transaction)
     - /o = Open in new window (creates new SAP session, preserves current)
   - Examples: "SU3" → "/nSU3", "SE16" with new_window=True → "/oSE16"

4. SSL certificates:
   - SAP systems often use self-signed certificates
   - Browser context must be created with ignore_https_errors=True

5. "User already logged in" dialogs:
   - May appear if user has other active sessions
   - Can be dismissed by clicking "Continue"/"Weiter" button
"""

import os
import re

import pytest
from mcp import ClientSession


@pytest.mark.asyncio
async def test_sap_login(sap_mcp_client: ClientSession) -> None:
    """Test that sap_login tool automatically logs in with credentials from environment.

    The sap_login tool reads SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE
    from environment variables and performs automatic login.

    Verification:
    - Tool returns success message
    - Browser shows SAP Easy Access (verified via HTML)
    - OK-Code field is visible (can enter transactions)
    """
    result = await sap_mcp_client.call_tool("sap_login", {})

    assert result.content, "Expected non-empty response from sap_login"
    response_text = result.content[0].text.lower()

    # Should indicate successful login or already logged in
    assert any(
        phrase in response_text
        for phrase in ["successfully logged", "already logged", "ready to run"]
    ), f"Login failed or unexpected response: {response_text}"

    # Verify browser state: check that SAP Easy Access loaded
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.lower()

    # SAP Easy Access page should have:
    # - The page title "SAP Easy Access"
    # - The OK-Code field (ToolbarOkCode)
    assert "sap easy access" in page_html or "toolbarokcode" in page_html, (
        "Browser does not show SAP Easy Access screen. "
        "Login may have failed or a dialog is blocking."
    )


@pytest.mark.asyncio
async def test_sap_transaction(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code after login.

    Uses SU3 (Maintain User Profile) as it's a simple, safe transaction
    available to all SAP users.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    # Login (auto-login with credentials from environment, or skip if already logged in)
    login_result = await sap_mcp_client.call_tool("sap_login", {})
    login_text = login_result.content[0].text.lower()
    assert "ready" in login_text or "already logged" in login_text, (
        f"Login failed: {login_result.content[0].text}"
    )

    # Test the sap_transaction tool with SU3 (user profile)
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SU3"})

    assert result.content, "Expected response from sap_transaction"
    response_text = result.content[0].text.lower()

    # Should indicate transaction executed
    assert "executed" in response_text, f"Transaction not executed: {response_text}"

    # Wait for SAP to load the SU3 transaction screen
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Verify SU3 actually opened by checking the page content
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.lower()

    # Check that we're no longer on the Easy Access menu (SMEN)
    assert "sap easy access" not in page_html, (
        "Still on SAP Easy Access menu. Transaction SU3 did not open."
    )

    # Check for SU3-specific content (user profile screen)
    # - German: "Pflege eigener Benutzervorgaben"
    # - English: "Maintain User Profile" or "Own Data"
    if sap_language == "DE":
        expected_phrases = ["benutzervorgaben", "eigene daten"]
    else:
        expected_phrases = ["user profile", "own data", "maintain user"]

    assert any(phrase in page_html for phrase in expected_phrases), (
        f"SU3 transaction screen not detected for language '{sap_language}'. "
        f"Expected one of: {expected_phrases}."
    )


@pytest.mark.asyncio
async def test_sap_transaction_invalid_tcode(sap_mcp_client: ClientSession) -> None:
    """Test that an invalid transaction code shows an error message.

    This is a negative test to verify the transaction entry mechanism works.
    If SAP shows an error message, it means the transaction code was received.
    """
    # Login
    await sap_mcp_client.call_tool("sap_login", {})

    # Try an obviously invalid transaction code
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "INVALIDTCODE123"})
    assert result.content, "Expected response from sap_transaction"

    # Get the page HTML to check for error message in the status bar
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.lower()

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


@pytest.mark.asyncio
async def test_sap_transaction_with_slash_prefix(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code that starts with / (namespace transaction).

    Transaction codes like /IWFND/GW_CLIENT need special handling:
    - They should become /n/IWFND/GW_CLIENT (not just /IWFND/GW_CLIENT)
    - The /n prefix tells SAP to open a new transaction
    """
    # Login
    await sap_mcp_client.call_tool("sap_login", {})

    # Test with a namespace transaction (starts with /)
    # /IWFND/GW_CLIENT is the SAP Gateway Client for testing OData services
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "/IWFND/GW_CLIENT"})

    assert result.content, "Expected response from sap_transaction"
    response_text = result.content[0].text.lower()

    # Should indicate transaction executed (or error if not authorized)
    assert "executed" in response_text or "error" in response_text, (
        f"Unexpected response: {response_text}"
    )


@pytest.mark.asyncio
async def test_sap_transaction_same_window_replaces_previous(sap_mcp_client: ClientSession) -> None:
    """Test that transactions in same window mode (/n) replace the previous transaction.

    This test:
    1. Opens SE11 (ABAP Dictionary) in same window mode
    2. Opens SE16 (Data Browser) in same window mode
    3. Verifies that SE11 was cancelled and SE16 is now active

    The /n prefix cancels any active transaction and starts the new one.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    # Login
    await sap_mcp_client.call_tool("sap_login", {})

    # Step 1: Open SE11 (ABAP Dictionary)
    result1 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11", "new_window": False})
    assert result1.content, "Expected response from sap_transaction"
    response1 = result1.content[0].text.lower()
    assert "executed" in response1 and "current window" in response1, (
        f"SE11 should open in current window: {response1}"
    )

    # Wait for SE11 to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Verify SE11 is displayed (ABAP Dictionary / Data Dictionary)
    html1 = await sap_mcp_client.call_tool("browser_get_html", {})
    page_html1 = html1.content[0].text.lower()
    if sap_language == "DE":
        assert any(phrase in page_html1 for phrase in ["dictionary", "wörterbuch", "se11"]), (
            "SE11 (ABAP Dictionary) should be displayed"
        )
    else:
        assert any(phrase in page_html1 for phrase in ["dictionary", "se11"]), (
            "SE11 (ABAP Dictionary) should be displayed"
        )

    # Step 2: Open SE16 (Data Browser) - this should REPLACE SE11
    result2 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16", "new_window": False})
    assert result2.content, "Expected response from sap_transaction"
    response2 = result2.content[0].text.lower()
    assert "executed" in response2 and "current window" in response2, (
        f"SE16 should open in current window: {response2}"
    )
    assert "cancelled" in response2, (
        f"Response should mention previous transaction was cancelled: {response2}"
    )

    # Wait for SE16 to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Verify SE16 is displayed and SE11 is gone
    html2 = await sap_mcp_client.call_tool("browser_get_html", {})
    page_html2 = html2.content[0].text.lower()

    # SE16 should be visible (Data Browser / Table Contents)
    if sap_language == "DE":
        se16_found = any(phrase in page_html2 for phrase in ["data browser", "tabelleninhalt", "se16"])
    else:
        se16_found = any(phrase in page_html2 for phrase in ["data browser", "table contents", "se16"])

    assert se16_found, (
        "SE16 (Data Browser) should be displayed after replacing SE11"
    )


@pytest.mark.asyncio
async def test_sap_transaction_new_window_preserves_previous(sap_mcp_client: ClientSession) -> None:
    """Test that transactions in new window mode (/o) preserve the previous transaction.

    This test:
    1. Opens SE11 (ABAP Dictionary) in same window mode
    2. Opens SE16 (Data Browser) in NEW window mode (new_window=True)
    3. Verifies that both transactions are now open in separate SAP sessions
    4. Checks that the session count is reported correctly

    The /o prefix opens a new SAP session without affecting the current one.
    """
    # Login
    await sap_mcp_client.call_tool("sap_login", {})

    # Step 1: Open SE11 (ABAP Dictionary) in current window
    result1 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11", "new_window": False})
    assert result1.content, "Expected response from sap_transaction"
    response1 = result1.content[0].text.lower()
    assert "executed" in response1, f"SE11 should be executed: {response1}"

    # Wait for SE11 to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Step 2: Open SE16 in NEW window - this should NOT replace SE11
    result2 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16", "new_window": True})
    assert result2.content, "Expected response from sap_transaction"
    response2 = result2.content[0].text.lower()

    # Should indicate new session was opened
    assert "new session" in response2 or "new window" in response2, (
        f"Response should mention new session/window: {response2}"
    )

    # Should report session count
    assert "sessions open:" in response2, (
        f"Response should report session count: {response2}"
    )

    # Extract session count from response (e.g., "SAP sessions open: 2")
    session_match = re.search(r"sessions open:\s*(\d+)", response2)
    assert session_match, f"Could not find session count in response: {response2}"
    session_count = int(session_match.group(1))

    # Should have at least 2 sessions (original + new)
    assert session_count >= 2, (
        f"Expected at least 2 SAP sessions after opening new window, got {session_count}"
    )
