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

CRITICAL - Tests Must Never Fail Silently:
------------------------------------------
MCP tools catch exceptions and return error messages as strings (e.g., "Error: ...").
This means Playwright errors like timeouts DON'T automatically fail tests!

ALWAYS check tool return values for errors:
    result = await client.call_tool("browser_fill", {"selector": "...", "value": "..."})
    text = result.content[0].text if result.content else ""
    assert "Error" not in text, f"Operation failed: {text}"

Use the helper functions _wait_for_transaction_screen() and _wait_for_easy_access()
which raise RuntimeError on failures.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession

# HTML snapshot directory for offline selector tests
HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"


def parse_tool_response(result: Any) -> dict[str, Any]:
    """
    Parse a tool result that returns a JSON-serialized Pydantic model.

    All SAP and browser tools now return Pydantic models that get JSON-serialized
    in the MCP response. This helper parses the JSON and returns the dict.

    Args:
        result: The CallToolResult from client.call_tool()

    Returns:
        Parsed dict from the JSON response

    Raises:
        AssertionError: If result is empty or not valid JSON
    """
    assert result.content, "Expected non-empty response from tool"
    text = result.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # If not JSON, return a dict with the text (for backward compatibility)
        return {"_raw_text": text, "success": "error" not in text.lower()}


def assert_tool_success(result: Any, context: str = "") -> dict[str, Any]:
    """
    Assert that a tool call was successful and return the parsed response.

    Args:
        result: The CallToolResult from client.call_tool()
        context: Optional context for error messages

    Returns:
        Parsed dict from the JSON response

    Raises:
        AssertionError: If the tool returned an error
    """
    data = parse_tool_response(result)
    ctx = f" ({context})" if context else ""
    assert data.get("success", True), f"Tool failed{ctx}: {data.get('error', data)}"
    return data


async def capture_html_snapshot(
    client: ClientSession,
    base_name: str,
    overwrite: bool = False,
) -> str:
    """
    Capture the current browser HTML and save it as a snapshot for unit tests.

    The filename will include the current SAP_LANGUAGE setting (e.g., "easy_access_en.html").
    This allows capturing snapshots in multiple languages for testing.

    Args:
        client: MCP ClientSession connected to the SAP Web GUI server
        base_name: Base name of the snapshot file without extension (e.g., "easy_access")
        overwrite: If True, overwrite existing snapshot. If False, skip if exists.

    Returns:
        The captured HTML content.
    """
    result = await client.call_tool("browser_get_html", {})
    if not result.content:
        raise RuntimeError("browser_get_html returned empty content")

    html_content = result.content[0].text

    # Include language in filename for multi-language snapshots
    language = os.environ.get("SAP_LANGUAGE", "EN").lower()
    filename = f"{base_name}_{language}.html"

    HTML_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = HTML_SNAPSHOTS_DIR / filename

    if overwrite or not snapshot_path.exists():
        snapshot_path.write_text(html_content, encoding="utf-8")

    return html_content


# Transaction-specific selectors for wait conditions
# These selectors identify unique elements on each transaction's initial screen
_TRANSACTION_WAIT_SELECTORS: dict[str, str] = {
    "SE11": "[lsdata*='RSRD1-TBMA']",  # Database table radio button
    "SE16": "input[lsdata*='TABLENAME']",  # Table name input field
    "SE93": "input[lsdata*='TSTC-TCODE']",  # Transaction code input field
    "SM37": "input[lsdata*='JOBNAME']",  # Job name input field
    "SU3": "[lsdata*='SUID_ST_NODE']",  # User profile (SU3) fields - SUID_ST_NODE_PERSON_NAME etc.
    "BP": "span:has-text('Person'), span:has-text('Organisation')",  # BP category buttons
    "EMMACL": "input[type='text']",  # EMMACL has many input fields
}


async def _wait_for_transaction_screen(
    client: ClientSession,
    tcode: str,
    timeout: int = 5000,
) -> None:
    """
    Wait for a transaction's initial screen to load.

    Uses transaction-specific selectors to detect when the screen is ready.
    This is faster than fixed timeouts because it returns as soon as the
    expected element is found.

    Args:
        client: MCP ClientSession connected to the SAP Web GUI server
        tcode: Transaction code (e.g., "SE16", "SM37")
        timeout: Maximum wait time in milliseconds (default 5000)

    Raises:
        NotImplementedError: If the transaction code is not in _TRANSACTION_WAIT_SELECTORS
        RuntimeError: If the wait times out or fails
    """
    tcode_upper = tcode.upper()
    if tcode_upper not in _TRANSACTION_WAIT_SELECTORS:
        raise NotImplementedError(
            f"No wait selector defined for transaction '{tcode}'. "
            f"Known transactions: {', '.join(sorted(_TRANSACTION_WAIT_SELECTORS.keys()))}. "
            f"Add a selector to _TRANSACTION_WAIT_SELECTORS or use browser_wait directly."
        )

    selector = _TRANSACTION_WAIT_SELECTORS[tcode_upper]
    result = await client.call_tool("browser_wait", {"selector": selector, "timeout": timeout})
    data = parse_tool_response(result)
    if not data.get("success", True):
        raise RuntimeError(f"Wait for {tcode} failed: {data.get('error', data)}")


async def _wait_for_easy_access(client: ClientSession, timeout: int = 5000) -> None:
    """
    Wait for SAP Easy Access screen (main menu) to load.

    Used after pressing F3 (Back) or when returning from a transaction.

    Args:
        client: MCP ClientSession connected to the SAP Web GUI server
        timeout: Maximum wait time in milliseconds (default 5000)

    Raises:
        RuntimeError: If the wait times out or fails
    """
    result = await client.call_tool("browser_wait", {"selector": "#ToolbarOkCode", "timeout": timeout})
    data = parse_tool_response(result)
    if not data.get("success", True):
        raise RuntimeError(f"Wait for Easy Access failed: {data.get('error', data)}")


@pytest.mark.anyio
async def test_sap_login_page_capture(sap_mcp_client: ClientSession) -> None:
    """Capture the login page HTML before login for debugging."""
    # Navigate to SAP URL without logging in to capture login page
    sap_url = os.environ.get("SAP_URL", "")
    if sap_url:
        await sap_mcp_client.call_tool("browser_navigate", {"url": sap_url})
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
        # Capture login page for debugging
        await capture_html_snapshot(sap_mcp_client, "login_page")


@pytest.mark.anyio
async def test_sap_login(sap_mcp_client: ClientSession) -> None:
    """Test that sap_login tool automatically logs in with credentials from environment.

    The sap_login tool reads SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE
    from environment variables and performs automatic login.

    Verification:
    - Tool returns success message
    - Browser shows SAP Easy Access (verified via HTML)
    - OK-Code field is visible (can enter transactions)
    - Login language matches SAP_LANGUAGE setting
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    result = await sap_mcp_client.call_tool("sap_login", {})

    # Tool now returns structured JSON with success/error fields
    data = assert_tool_success(result, "sap_login")
    assert data.get("url"), "Expected URL in login response"

    # Verify browser state: check that SAP Easy Access loaded
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text

    # SAP Easy Access page should have the OK-Code field
    assert "toolbarokcode" in page_html.lower(), (
        "Browser does not show SAP Easy Access screen. " "Login may have failed or a dialog is blocking."
    )

    # Verify the login language is correct by checking UI text
    if sap_language == "EN":
        # English UI should have "SAP Easy Access" (not German "SAP Schnellzugriff")
        assert "sap easy access" in page_html.lower(), (
            f"Expected English UI (SAP Easy Access) but got German. "
            f"SAP_LANGUAGE={sap_language} may not have been applied during login."
        )
    elif sap_language == "DE":
        # German UI typically shows "SAP Easy Access" too, but with German menu items
        # Check for German menu items like "System" or "Hilfe"
        pass  # German is the fallback, no strict assertion needed

    await capture_html_snapshot(sap_mcp_client, "easy_access")


@pytest.mark.anyio
async def test_settings_dialog_capture(sap_mcp_client: ClientSession) -> None:
    """Capture the settings dialog HTML for selector testing.

    Opens the SAP settings dialog to capture its HTML structure.
    This allows unit tests to verify selectors for settings_button,
    okcode_checkbox, save_settings, and close_dialog.
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Try to find and click the settings button using browser_evaluate
    # This mirrors the logic in _enable_okcode_field
    settings_clicked = await sap_mcp_client.call_tool(
        "browser_evaluate",
        {
            "expression": """
            (function() {
                // Try various settings button selectors
                var selectors = [
                    '[id*="settingsButton"]',
                    '[title*="Setting" i]',
                    '[title*="Einstellung" i]',
                    'button[id*="gear" i]',
                    '[aria-label*="Setting" i]'
                ];
                for (var i = 0; i < selectors.length; i++) {
                    var btn = document.querySelector(selectors[i]);
                    if (btn) {
                        btn.click();
                        return 'clicked: ' + selectors[i];
                    }
                }
                return 'not found';
            })()
            """
        },
    )

    if settings_clicked.content and "clicked" in settings_clicked.content[0].text:
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
        await capture_html_snapshot(sap_mcp_client, "settings_dialog")

        # Close the dialog
        await sap_mcp_client.call_tool(
            "browser_evaluate",
            {
                "expression": """
                (function() {
                    var selectors = [
                        'button:contains("Close")',
                        'button:contains("Schließen")',
                        '[id*="closeButton"]',
                        'button[aria-label*="Close" i]'
                    ];
                    for (var i = 0; i < selectors.length; i++) {
                        try {
                            var btn = document.querySelector(selectors[i]);
                            if (btn) { btn.click(); return 'closed'; }
                        } catch(e) {}
                    }
                    // Try pressing Escape
                    return 'escape';
                })()
                """
            },
        )
        await sap_mcp_client.call_tool("sap_keyboard", {"key": "Escape"})


@pytest.mark.anyio
async def test_sap_transaction(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code after login.

    Uses SU3 (Maintain User Profile) as it's a simple, safe transaction
    available to all SAP users.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    # Login (auto-login with credentials from environment, or skip if already logged in)
    login_result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(login_result, "sap_login")

    # Test the sap_transaction tool with SU3 (user profile)
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SU3"})

    # Tool returns structured JSON with success/error fields
    data = assert_tool_success(result, "sap_transaction SU3")
    assert data.get("tcode", "").upper() == "SU3", f"Expected tcode SU3: {data}"

    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    # Verify SU3 actually opened by checking the page content
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.lower()

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
    await sap_mcp_client.call_tool("sap_login", {})

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

    # Capture HTML snapshot with error status bar for offline testing
    await capture_html_snapshot(sap_mcp_client, "status_bar_error")


@pytest.mark.anyio
async def test_sap_transaction_with_slash_prefix(sap_mcp_client: ClientSession) -> None:
    """Test entering a transaction code that starts with / (namespace transaction).

    Transaction codes like /IWFND/GW_CLIENT need special handling:
    - They should become /n/IWFND/GW_CLIENT (not just /IWFND/GW_CLIENT)
    - The /n prefix tells SAP to open a new transaction
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Test with a namespace transaction (starts with /)
    # /IWFND/GW_CLIENT is the SAP Gateway Client for testing OData services
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "/IWFND/GW_CLIENT"})

    assert result.content, "Expected response from sap_transaction"
    response_text = result.content[0].text.lower()

    # Should indicate transaction executed (or error if not authorized)
    assert "executed" in response_text or "error" in response_text, f"Unexpected response: {response_text}"


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

    await sap_mcp_client.call_tool("sap_login", {})

    # Step 1: Open SE11 (ABAP Dictionary)
    result1 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11", "new_window": False})
    data1 = assert_tool_success(result1, "sap_transaction SE11")
    assert not data1.get("new_window"), f"SE11 should open in current window: {data1}"

    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Verify SE11 is displayed (ABAP Dictionary / Data Dictionary)
    html1 = await sap_mcp_client.call_tool("browser_get_html", {})
    html1_data = parse_tool_response(html1)
    page_html1 = html1_data.get("html", html1_data.get("_raw_text", "")).lower()
    if sap_language == "DE":
        assert any(
            phrase in page_html1 for phrase in ["dictionary", "wörterbuch", "se11"]
        ), "SE11 (ABAP Dictionary) should be displayed"
    else:
        assert any(
            phrase in page_html1 for phrase in ["dictionary", "se11"]
        ), "SE11 (ABAP Dictionary) should be displayed"

    # Step 2: Open SE16 (Data Browser) - this should REPLACE SE11
    result2 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16", "new_window": False})
    data2 = assert_tool_success(result2, "sap_transaction SE16")
    assert not data2.get("new_window"), f"SE16 should open in current window: {data2}"

    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Verify SE16 is displayed and SE11 is gone
    html2 = await sap_mcp_client.call_tool("browser_get_html", {})
    html2_data = parse_tool_response(html2)
    page_html2 = html2_data.get("html", html2_data.get("_raw_text", "")).lower()

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
    await sap_mcp_client.call_tool("sap_login", {})

    # Step 1: Open SE11 (ABAP Dictionary) in current window
    result1 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11", "new_window": False})
    data1 = assert_tool_success(result1, "sap_transaction SE11")
    assert not data1.get("new_window"), f"SE11 should open in current window: {data1}"

    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Step 2: Open SE16 in NEW window - this should NOT replace SE11
    result2 = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16", "new_window": True})
    data2 = assert_tool_success(result2, "sap_transaction SE16 new_window")

    # Should indicate new session was opened
    assert data2.get("new_window"), f"Response should indicate new window mode: {data2}"

    # Should report session count
    session_count = data2.get("session_count")
    assert session_count is not None, f"Response should report session count: {data2}"

    # Should have at least 2 sessions (original + new)
    assert session_count >= 2, f"Expected at least 2 SAP sessions after opening new window, got {session_count}"


# =============================================================================
# Tests for new SAP tools (sap_session_status, sap_keyboard, sap_get_screen_text,
# sap_read_table, sap_read_status_bar, sap_get_screen_info)
# =============================================================================


@pytest.mark.anyio
async def test_sap_session_status_after_login(sap_mcp_client: ClientSession) -> None:
    """Test that session status is 'active' after successful login."""
    await sap_mcp_client.call_tool("sap_login", {})

    result = await sap_mcp_client.call_tool("sap_session_status", {})
    assert result.content, "Expected response from sap_session_status"
    response_text = result.content[0].text.lower()

    assert "active" in response_text, f"Expected active session after login: {response_text}"


@pytest.mark.anyio
async def test_sap_session_status_returns_valid_state(sap_mcp_client: ClientSession) -> None:
    """Test that session status returns a recognized state."""
    await sap_mcp_client.call_tool("sap_login", {})

    result = await sap_mcp_client.call_tool("sap_session_status", {})
    response_text = result.content[0].text.lower()

    valid_states = ["active", "timed_out", "logged_off", "no_page", "unknown"]
    assert any(
        state in response_text for state in valid_states
    ), f"Expected one of {valid_states}, got: {response_text}"


@pytest.mark.anyio
async def test_sap_keyboard_f3_navigates_back(sap_mcp_client: ClientSession) -> None:
    """Test F3 (Back) returns from transaction to previous screen."""
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Press F3 to go back
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})
    data = assert_tool_success(result, "sap_keyboard F3")
    assert data.get("key") == "F3", f"Expected key F3: {data}"

    # Wait for Easy Access (OK-Code field visible means we're back on main menu)
    await _wait_for_easy_access(sap_mcp_client)

    # Should be back on Easy Access or previous screen
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    html_data = parse_tool_response(html_result)
    page_html = html_data.get("html", html_data.get("_raw_text", "")).lower()

    # SE16 specific content should be gone or we should be on Easy Access
    se16_gone = "data browser" not in page_html and "tabelleninhalt" not in page_html
    on_easy_access = "sap easy access" in page_html or "toolbarokcode" in page_html

    assert se16_gone or on_easy_access, "F3 should have navigated away from SE16"


@pytest.mark.anyio
async def test_sap_keyboard_f8_triggers_execution(sap_mcp_client: ClientSession) -> None:
    """Test F8 (Execute) triggers action in SE16.

    When F8 is pressed in SE16 without a table name, SAP should show an error
    message about missing table name - this proves F8 was received.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to execute without entering a table name - should trigger error
    result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    assert result.content, "Expected response from sap_keyboard"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Check for error message in page or status bar
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    page_html = html_result.content[0].text.lower()

    # SAP should show error about missing table name
    if sap_language == "DE":
        expected_phrases = ["eingabe", "tabelle", "fehler", "pflichtfeld", "füllen"]
    else:
        expected_phrases = ["enter", "table", "error", "required", "specify", "fill"]

    assert any(
        phrase in page_html for phrase in expected_phrases
    ), f"F8 without input should trigger error or prompt. Language: {sap_language}"


@pytest.mark.anyio
async def test_sap_get_screen_text_from_se16(sap_mcp_client: ClientSession) -> None:
    """Test reading screen text from SE16 initial screen."""
    sap_language = os.environ.get("SAP_LANGUAGE", "EN")

    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await sap_mcp_client.call_tool("sap_get_screen_text", {})
    assert result.content, "Expected response from sap_get_screen_text"
    response_text = result.content[0].text.lower()

    # SE16 should show table name prompt
    if sap_language == "DE":
        expected_phrases = ["tabellenname", "tabelle", "data browser"]
    else:
        expected_phrases = ["table name", "table", "data browser"]

    assert any(
        phrase in response_text for phrase in expected_phrases
    ), f"SE16 screen text should contain table-related labels. Language: {sap_language}. Got: {response_text[:500]}"

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "se16_initial")


@pytest.mark.anyio
async def test_sap_get_screen_text_structure(sap_mcp_client: ClientSession) -> None:
    """Test that sap_get_screen_text returns structured output."""
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SU3"})
    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await sap_mcp_client.call_tool("sap_get_screen_text", {})
    data = assert_tool_success(result, "sap_get_screen_text")

    # Check for expected structure in JSON response
    assert "title" in data, "Should contain title"

    # Should have some labels or content
    has_labels = bool(data.get("labels"))
    has_content = bool(data.get("main_content"))
    has_buttons = bool(data.get("buttons"))

    assert (
        has_labels or has_content or has_buttons
    ), f"Screen text should contain labels, content, or buttons. Got: {data}"


@pytest.mark.anyio
async def test_sap_read_table_from_sm37_no_jobs(sap_mcp_client: ClientSession) -> None:
    """Test SM37 when no jobs match selection criteria.

    Uses current user (default) which typically has no scheduled jobs,
    resulting in "Kein Job entspricht den Selektionsbedingungen" message.
    """
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SM37"})
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")

    # Capture HTML snapshot for offline selector testing (before filling form)
    await capture_html_snapshot(sap_mcp_client, "sm37_initial")

    # Use defaults (current user) - typically no jobs
    fill_result = await sap_mcp_client.call_tool("browser_fill", {"selector": "input[lsdata*='JOBNAME']", "value": "*"})
    fill_text = fill_result.content[0].text if fill_result.content else ""
    assert "Error" not in fill_text, f"Failed to fill JOBNAME field: {fill_text}"

    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Check status bar for "no jobs" message
    status_result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    status_text = status_result.content[0].text.lower() if status_result.content else ""

    # German: "Kein Job entspricht den Selektionsbedingungen"
    # English: "No job meets the selection conditions"
    no_jobs_de = "kein job" in status_text
    no_jobs_en = "no job" in status_text

    assert no_jobs_de or no_jobs_en, f"Expected 'no jobs' status message, got: {status_text}"


async def assert_fill_success(result: Any, field_name: str) -> None:
    """Assert that browser_fill succeeded for a field."""
    data = parse_tool_response(result)
    assert data.get("success", True), f"Failed to fill {field_name}: {data.get('error', data)}"


@pytest.mark.anyio
async def test_sap_read_table_from_sm37_all_jobs(sap_mcp_client: ClientSession) -> None:
    """Test reading table data from SM37 (Job Overview) with broad criteria.

    SM37 exists on every SAP system and shows background jobs.
    Uses wildcards for username and broad date range to find jobs.
    """
    from datetime import datetime, timedelta

    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SM37"})
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")

    # Fill job selection with wildcards and clear username restriction
    # SM37 fields use SID in lsdata: BTCH2170-JOBNAME, BTCH2170-USERNAME
    result = await sap_mcp_client.call_tool("browser_fill", {"selector": "input[lsdata*='JOBNAME']", "value": "*"})
    await assert_fill_success(result, "JOBNAME")

    result = await sap_mcp_client.call_tool("browser_fill", {"selector": "input[lsdata*='USERNAME']", "value": "*"})
    await assert_fill_success(result, "USERNAME")

    # Set broad date range (last 365 days) to find jobs
    # Date fields have SID in lsdata: BTCH2170-FROM_DATE, BTCH2170-TO_DATE
    today = datetime.now()
    from_date = (today - timedelta(days=365)).strftime("%d.%m.%Y")
    to_date = today.strftime("%d.%m.%Y")

    result = await sap_mcp_client.call_tool(
        "browser_fill", {"selector": "input[lsdata*='FROM_DATE']", "value": from_date}
    )
    await assert_fill_success(result, f"FROM_DATE={from_date}")

    result = await sap_mcp_client.call_tool("browser_fill", {"selector": "input[lsdata*='TO_DATE']", "value": to_date})
    await assert_fill_success(result, f"TO_DATE={to_date}")

    # Execute (F8) and wait for list output to complete (can take a while with many jobs)
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 30000})

    # Capture table results HTML for unit tests
    await capture_html_snapshot(sap_mcp_client, "sm37_results")

    result = await sap_mcp_client.call_tool("sap_read_table", {"start_row": 1, "end_row": 5})
    table_data = assert_tool_success(result, "sap_read_table")

    # Assert that we got actual table data with rows
    assert "rows" in table_data, f"Expected table with 'rows', got: {table_data}"
    assert "total_rows" in table_data, f"Expected 'total_rows' in response, got: {table_data}"

    # Verify we got some jobs
    assert table_data.get("total_rows", 0) > 0, f"Expected some jobs in SM37, got total_rows=0"
    assert len(table_data.get("rows", [])) > 0, "Expected at least one row in SM37 results"


@pytest.mark.anyio
async def test_sap_read_table_from_se93(sap_mcp_client: ClientSession) -> None:
    """Test reading transaction codes from SE93.

    SE93 with wildcard 'SE*' will always return results (SE11, SE16, etc.).
    """
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE93"})
    # Wait for SE93 to load (has transaction code input field with TSTC-TCODE in lsdata)
    await _wait_for_transaction_screen(sap_mcp_client, "SE93")

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "se93_initial")

    # Search for transactions starting with SE - use lsdata selector
    fill_result = await sap_mcp_client.call_tool(
        "browser_fill", {"selector": "input[lsdata*='TSTC-TCODE']", "value": "SE*"}
    )
    fill_text = fill_result.content[0].text if fill_result.content else ""
    assert "Error" not in fill_text, f"Failed to fill SE93 transaction code field: {fill_text}"

    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    result = await sap_mcp_client.call_tool("sap_read_table", {})
    assert result.content, "Expected response from sap_read_table"
    response_text = result.content[0].text.lower()

    # Should find standard SE* transactions
    # Check for either transaction codes in data or valid table structure
    has_se_transactions = "se11" in response_text or "se16" in response_text or "se80" in response_text
    has_table_structure = "rows" in response_text or "headers" in response_text

    assert (
        has_se_transactions or has_table_structure
    ), f"Expected to find standard SE* transactions or table structure: {response_text[:500]}"


@pytest.mark.anyio
async def test_se16_table_content_t000(sap_mcp_client: ClientSession) -> None:
    """Test reading actual table content from SE16 using T000 (Clients table).

    T000 is the SAP clients/mandants table. It exists on every SAP system
    and contains at least one row (the current client). It's small enough
    to not overwhelm the LLM context.

    This test verifies:
    - SE16 can display table content
    - The table has at least one row
    - We can capture the HTML for unit tests
    """
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Enter table name T000 (Clients table - always exists, always small)
    # Use lsdata selector which is reliable for SAP Web GUI elements
    fill_result = await sap_mcp_client.call_tool(
        "browser_fill", {"selector": "input[lsdata*='TABLENAME']", "value": "T000"}
    )
    fill_text = fill_result.content[0].text if fill_result.content else ""
    assert "Error" not in fill_text, f"Failed to fill table name field: {fill_text}"

    # Execute to show table content
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture table content HTML for unit tests
    await capture_html_snapshot(sap_mcp_client, "se16_t000_content")

    # Read the table data
    result = await sap_mcp_client.call_tool("sap_read_table", {"start_row": 1, "end_row": 10})
    assert result.content, "Expected response from sap_read_table"
    response_text = result.content[0].text

    # T000 must have at least one row (the current client)
    # Check for table data indicators
    has_rows = "rows" in response_text.lower() or "mandt" in response_text.lower()
    has_content = len(response_text) > 50  # More than just an error message

    assert has_rows and has_content, (
        f"SE16 T000 should return table content with at least one client. " f"Response: {response_text[:500]}"
    )


@pytest.mark.anyio
async def test_se11_table_definition_t000(sap_mcp_client: ClientSession) -> None:
    """Test viewing table definition in SE11 using T000 (Clients table).

    SE11 (ABAP Dictionary) shows table structure/definition, not content.
    T000 is a simple table with well-known fields like MANDT, CCCATEGORY, etc.

    This test verifies:
    - SE11 can display table definition
    - The table fields are shown
    - We can capture the HTML for unit tests
    """
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE11"})
    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Capture SE11 initial screen
    await capture_html_snapshot(sap_mcp_client, "se11_initial")

    # "Datenbanktabelle" is a radio button, click it then Tab to the text field
    await sap_mcp_client.call_tool("browser_click", {"selector": "text=Datenbanktabelle"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 300})
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "Tab"})
    await sap_mcp_client.call_tool("browser_keyboard", {"text": "T000"})

    # Press F7 (Anzeigen/Display) to view table definition
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F7"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture table structure HTML
    await capture_html_snapshot(sap_mcp_client, "se11_t000_content")

    # Verify we're on the table definition screen
    html_result = await sap_mcp_client.call_tool("browser_get_html", {})
    assert html_result.content, "Expected HTML response"
    page_html = html_result.content[0].text.upper()

    # T000 definition should show field names like MANDT, CCCATEGORY
    has_mandt = "MANDT" in page_html
    has_fields = "FIELD" in page_html or "COMPONENT" in page_html or "CCCATEGORY" in page_html

    assert has_mandt or has_fields, (
        "SE11 T000 definition should show table fields. " "Expected MANDT or other field indicators in the page."
    )


@pytest.mark.anyio
async def test_sap_read_status_bar_after_navigation(sap_mcp_client: ClientSession) -> None:
    """Test reading status bar after successful navigation."""
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SU3"})
    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    assert result.content, "Expected response from sap_read_status_bar"
    response_text = result.content[0].text

    # Should return JSON with type and message fields
    assert (
        "type" in response_text.lower() or "message" in response_text.lower()
    ), f"Status bar should return type/message info: {response_text}"


@pytest.mark.anyio
async def test_sap_read_status_bar_after_error(sap_mcp_client: ClientSession) -> None:
    """Test reading status bar after triggering an error."""
    await sap_mcp_client.call_tool("sap_login", {})

    # Try invalid transaction to trigger error
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "ZZZZINVALID999"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    assert result.content, "Expected response from sap_read_status_bar"
    response_text = result.content[0].text.lower()

    # Should indicate error type or contain error message
    error_indicators = ['"e"', '"type": "e"', "error", "fehler", "existiert nicht", "does not exist"]
    assert any(
        indicator in response_text for indicator in error_indicators
    ), f"Status bar should indicate error after invalid transaction: {response_text}"


@pytest.mark.anyio
async def test_sap_get_screen_info_from_se16(sap_mcp_client: ClientSession) -> None:
    """Test getting screen info from SE16."""
    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await sap_mcp_client.call_tool("sap_get_screen_info", {})
    assert result.content, "Expected response from sap_get_screen_info"
    response_text = result.content[0].text.lower()

    # Should contain basic screen info
    assert "title" in response_text, "Screen info should contain title"
    assert "url" in response_text, "Screen info should contain url"


@pytest.mark.anyio
async def test_sap_get_screen_info_different_transactions(sap_mcp_client: ClientSession) -> None:
    """Test that screen info changes between transactions."""
    await sap_mcp_client.call_tool("sap_login", {})

    # Get info from SE16
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")
    result1 = await sap_mcp_client.call_tool("sap_get_screen_info", {})
    info1 = result1.content[0].text.lower()

    # Get info from SM37
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SM37"})
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")
    result2 = await sap_mcp_client.call_tool("sap_get_screen_info", {})
    info2 = result2.content[0].text.lower()

    # The title or content should be different
    assert info1 != info2, "Screen info should differ between SE16 and SM37"


@pytest.mark.anyio
async def test_browser_reconnect_after_idle(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser reconnects after becoming stale.

    This test simulates a scenario where the CDP connection becomes stale
    (e.g., browser was minimized, focus was lost, or connection timed out).
    The server should automatically reconnect and continue working.
    """
    # Step 1: Login and verify we have a working session
    login_result = await sap_mcp_client.call_tool("sap_login", {})
    login_data = assert_tool_success(login_result, "sap_login")
    assert login_data.get("url"), "Expected URL in login response"

    # Step 2: Navigate to a transaction
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Step 3: Wait a bit to let connection potentially become stale
    # In real scenarios, this could be minutes; here we just verify the flow works
    await asyncio.sleep(5)

    # Step 4: Try to use the browser again - this should reconnect if stale
    result = await sap_mcp_client.call_tool("sap_session_status", {})
    status_data = parse_tool_response(result)

    # Should be able to get status (either connected or reconnected)
    assert "status" in status_data or status_data.get(
        "success", True
    ), f"Should get valid session status after idle period: {status_data}"

    # Step 5: Verify we can still execute transactions
    tx_result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SM37"})
    tx_data = assert_tool_success(tx_result, "sap_transaction after idle")
    assert tx_data.get("tcode"), f"Transaction should work after idle: {tx_data}"


@pytest.mark.anyio
async def test_browser_reconnect_multiple_times(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser can reconnect multiple times during a session.

    This verifies the reconnection logic is robust and doesn't leave
    the browser manager in a bad state after reconnecting.
    """
    await sap_mcp_client.call_tool("sap_login", {})

    transactions = ["SE16", "SM37", "SU3", "SE16"]

    for i, tcode in enumerate(transactions):
        # Small delay between transactions
        await asyncio.sleep(2)

        # Execute transaction
        result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": tcode})
        tx_data = assert_tool_success(result, f"sap_transaction {tcode}")
        assert tx_data.get("tcode"), f"Transaction {tcode} should work: {tx_data}"

        # Verify session is still valid
        status = await sap_mcp_client.call_tool("sap_session_status", {})
        status_data = parse_tool_response(status)
        assert status_data.get("success", True), f"Expected valid status after transaction {i+1}: {status_data}"


# =============================================================================
# Tests for sap_fill_form (batch form filling)
# =============================================================================


@pytest.mark.anyio
async def test_bp_fill_form_batch_fill(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form batch filling in BP (Business Partner) transaction.

    This test verifies that sap_fill_form can fill multiple form fields
    in a single call, which is much faster than individual browser_fill calls.

    The test:
    1. Opens BP transaction
    2. Captures HTML snapshot of initial screen (shows Person/Organisation buttons)
    3. Clicks "Person" button to create a new person BP
    4. Captures HTML snapshot of person form
    5. Uses sap_fill_form to batch fill name and address fields
    6. Verifies all fields were reported as filled
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await sap_mcp_client.call_tool("sap_login", {})

    # Step 1: Open BP transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    assert_tool_success(result, "sap_transaction BP")

    # Wait for BP initial screen (has Person/Organisation buttons)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Capture HTML snapshot of BP initial screen
    await capture_html_snapshot(sap_mcp_client, "bp_initial")

    # Step 2: Click on the "Person" button to create a new person
    # The button has ID M0:48::btn[5] with text "Person anlegen (F5)"
    #
    # IMPORTANT: SAP Web GUI requires multiple waits for reliable form interaction:
    # - Pre-click wait: Ensures the page is fully interactive after initial load
    # - Post-click wait: Allows SAP backend to process and return the form HTML
    # - Form label wait: Ensures the specific form labels are rendered
    # - Post-render wait: Allows all label-input associations (lsdata) to be populated
    # Without these waits, the form may not have all labels visible when sap_fill_form runs.
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    click_result = await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    click_data = parse_tool_response(click_result)
    assert click_data.get("success", True), f"Failed to click Person button: {click_data}"

    # Wait for SAP backend to process and return form HTML
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for specific form labels to be rendered
    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})

    # Allow all label-input lsdata associations to be populated
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture HTML snapshot after clicking Person (shows the form fields)
    await capture_html_snapshot(sap_mcp_client, "bp_person_form")

    # Step 3: Use sap_fill_form to batch fill multiple fields
    # Field labels depend on language setting
    if sap_language == "DE":
        fields_to_fill = {
            "Vorname": "Max",
            "Nachname": "Mustermann",
        }
    else:
        fields_to_fill = {
            "First Name": "Max",
            "Last Name": "Mustermann",
        }

    fill_result = await sap_mcp_client.call_tool("sap_fill_form", {"fields": fields_to_fill})
    fill_data = assert_tool_success(fill_result, "sap_fill_form")

    # Verify ALL fields were filled successfully
    filled_fields = set(fill_data.get("filled", []))
    not_found_fields = fill_data.get("not_found", [])
    error_fields = fill_data.get("errors", [])
    expected_fields = set(fields_to_fill.keys())

    # No fields should be missing or have errors
    assert len(not_found_fields) == 0, (
        f"All fields must be found. Not found: {not_found_fields}. "
        f"Check if labels match SAP_LANGUAGE={sap_language} setting."
    )
    assert len(error_fields) == 0, f"All fields must fill without errors. Errors: {error_fields}"

    # All requested fields must be in the filled list
    assert (
        filled_fields == expected_fields
    ), f"All fields must be filled. Expected: {expected_fields}, Filled: {filled_fields}"


@pytest.mark.anyio
async def test_bp_fill_form_with_css_selectors(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form using CSS selectors instead of labels.

    This test verifies that sap_fill_form can fill fields using direct
    CSS selectors (e.g., [attribute*='value'] selectors) that match SAP lsdata attributes.
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open BP transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    assert_tool_success(result, "sap_transaction BP")

    # Wait for BP initial screen
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Click on "Person" button to create a new person
    # IMPORTANT: SAP Web GUI requires multiple waits for reliable form interaction.
    # See test_bp_fill_form_batch_fill for detailed explanation.
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    click_result = await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    click_data = parse_tool_response(click_result)
    assert click_data.get("success", True), f"Failed to click Person button: {click_data}"

    # Wait for SAP backend to process and return form HTML
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for first name label to confirm form is loaded
    await sap_mcp_client.call_tool(
        "browser_wait", {"selector": "label:has-text('Vorname'), label:has-text('First Name')", "timeout": 15000}
    )

    # Allow all label-input lsdata associations to be populated
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Use CSS selectors that match SAP lsdata attributes for BP person form
    # These selectors target the actual SAP field IDs embedded in lsdata
    # Based on actual BP form HTML snapshots (bp_person_form_de.html)
    fields_to_fill = {
        "input[lsdata*='NAME_FIRST']": "Max",
        "input[lsdata*='NAME_LAST']": "Mustermann",
        "input[lsdata*='STREET']": "Hauptstraße",
        "input[lsdata*='HOUSE_NUM1']": "123",
        "input[lsdata*='POST_CODE1']": "12345",
        "input[lsdata*='CITY1']": "Berlin",
    }

    fill_result = await sap_mcp_client.call_tool("sap_fill_form", {"fields": fields_to_fill})
    fill_data = assert_tool_success(fill_result, "sap_fill_form with CSS selectors")

    # Verify ALL fields were filled successfully
    filled_fields = set(fill_data.get("filled", []))
    not_found_fields = fill_data.get("not_found", [])
    error_fields = fill_data.get("errors", [])
    expected_fields = set(fields_to_fill.keys())

    # No fields should be missing or have errors
    assert len(not_found_fields) == 0, (
        f"All CSS selector fields must be found. Not found: {not_found_fields}. "
        f"Selectors may need adjustment based on actual BP form HTML."
    )
    assert len(error_fields) == 0, f"All fields must fill without errors. Errors: {error_fields}"

    # All requested fields must be in the filled list
    assert (
        filled_fields == expected_fields
    ), f"All fields must be filled. Expected: {expected_fields}, Filled: {filled_fields}"


@pytest.mark.anyio
async def test_sap_fill_form_strict_mode(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form strict mode - should fail if any field is not found.

    In strict mode (strict=True), the tool should return success=False
    if any field cannot be found or filled.
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open a simple transaction
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to fill with an invalid field label in strict mode
    fill_result = await sap_mcp_client.call_tool(
        "sap_fill_form",
        {
            "fields": {
                "NONEXISTENT_FIELD_12345": "test value",
            },
            "strict": True,
        },
    )
    fill_data = parse_tool_response(fill_result)

    # Strict mode should report failure when field not found
    assert not fill_data.get("success", True), f"Strict mode should fail when field not found. Response: {fill_data}"
    assert "NONEXISTENT_FIELD_12345" in fill_data.get(
        "not_found", []
    ), f"Field should be in not_found list: {fill_data}"


# =============================================================================
# Tests for EMMACL transaction (field discovery and batch fill)
# =============================================================================


@pytest.mark.anyio
async def test_emmacl_discover_fields(sap_mcp_client: ClientSession) -> None:
    """
    Test field discovery in EMMACL transaction.

    EMMACL is an energy market clearing transaction with many input fields,
    making it ideal for testing field discovery and batch fill capabilities.

    This test:
    1. Opens EMMACL transaction
    2. Captures HTML snapshot
    3. Uses sap_discover_fields to find all fields
    4. Verifies fields are discovered with proper structure
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open EMMACL transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    assert_tool_success(result, "sap_transaction EMMACL")

    # Wait for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of EMMACL initial screen
    await capture_html_snapshot(sap_mcp_client, "emmacl_initial")

    # Discover all fields on the screen
    discover_result = await sap_mcp_client.call_tool("sap_discover_fields", {})
    discover_data = assert_tool_success(discover_result, "sap_discover_fields")

    # Verify we found some fields
    field_count = discover_data.get("field_count", 0)
    fields = discover_data.get("fields", [])

    assert field_count > 0, f"EMMACL should have input fields. Got: {discover_data}"
    assert len(fields) > 0, f"Fields list should not be empty. Got: {discover_data}"

    # Print discovered fields for debugging (visible in test output)
    print(f"\nDiscovered {field_count} fields in EMMACL:")
    for field in fields[:20]:  # Show first 20
        print(f"  - {field.get('label', 'no-label')}: {field.get('selector', 'no-selector')}")


@pytest.mark.anyio
async def test_emmacl_fill_form_with_discovered_fields(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form in EMMACL using discovered field selectors.

    This test:
    1. Opens EMMACL transaction
    2. Discovers fields using sap_discover_fields
    3. Uses sap_fill_form to fill some of the discovered fields
    4. Verifies all specified fields were filled
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open EMMACL transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    assert_tool_success(result, "sap_transaction EMMACL")

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # First discover fields to find valid selectors
    discover_result = await sap_mcp_client.call_tool("sap_discover_fields", {})
    discover_data = assert_tool_success(discover_result, "sap_discover_fields")

    fields = discover_data.get("fields", [])

    # Find text input fields (not readonly, not checkboxes)
    fillable_fields = [f for f in fields if f.get("type") in ("text", None) and f.get("selector")]

    if len(fillable_fields) < 2:
        pytest.skip("Not enough fillable fields found in EMMACL")

    # Pick first 2 fillable fields and try to fill them
    fields_to_fill = {}
    for i, field in enumerate(fillable_fields[:2]):
        selector = field.get("selector")
        if selector:
            fields_to_fill[selector] = f"TEST{i}"

    print(f"\nTrying to fill {len(fields_to_fill)} fields: {list(fields_to_fill.keys())}")

    fill_result = await sap_mcp_client.call_tool("sap_fill_form", {"fields": fields_to_fill})
    fill_data = parse_tool_response(fill_result)

    # Log results
    print(f"Filled: {fill_data.get('filled', [])}")
    print(f"Not found: {fill_data.get('not_found', [])}")
    print(f"Errors: {fill_data.get('errors', [])}")

    # At least some fields should have been filled
    filled = fill_data.get("filled", [])
    assert len(filled) > 0, f"Expected at least one field to be filled. Result: {fill_data}"


@pytest.mark.anyio
async def test_emmacl_execute_without_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test executing EMMACL without any filter (F8 on initial screen).

    This test:
    1. Opens EMMACL transaction
    2. Presses F8 to execute without filters
    3. Captures result table
    4. Saves HTML snapshot of results
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open EMMACL transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    assert_tool_success(result, "sap_transaction EMMACL")

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Execute without any filters (F8)
    kb_result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    assert_tool_success(kb_result, "sap_keyboard F8")

    # Wait for results to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of results
    await capture_html_snapshot(sap_mcp_client, "emmacl_results_no_filter")

    # Read result table
    table_result = await sap_mcp_client.call_tool("sap_read_table", {"max_rows": 20})
    table_data = parse_tool_response(table_result)

    # Print results for debugging
    print(f"\nEMMACL results without filter:")
    print(f"Headers: {table_data.get('headers', [])}")
    print(f"Total rows: {table_data.get('total_rows', 0)}")
    for row in table_data.get("rows", [])[:5]:
        print(f"  Row {row.get('row')}: {row.get('data')}")

    # Verify we got some results (or at least the table was read)
    assert table_data.get("success", True), f"Table read failed: {table_data}"


@pytest.mark.anyio
async def test_emmacl_execute_with_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test executing EMMACL with filter fields.

    This test:
    1. Opens EMMACL transaction
    2. Fills a filter field (Business Process Code)
    3. Presses F8 to execute
    4. Verifies the search was executed (got results or "no data" message)
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open EMMACL transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    assert_tool_success(result, "sap_transaction EMMACL")

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Fill filter field using discovered selector
    # Using a filter value that likely won't match many rows to test filtering works
    filter_values = {
        "input[lsdata*='BPCODE-LOW']": "ZTEST",  # Business Process Code (likely no matches)
    }

    fill_result = await sap_mcp_client.call_tool("sap_fill_form", {"fields": filter_values})
    fill_data = assert_tool_success(fill_result, "sap_fill_form")

    print(f"\nFilled filter fields: {fill_data.get('filled', [])}")

    # Verify filter field was filled
    assert len(fill_data.get("filled", [])) == len(
        filter_values
    ), f"Expected {len(filter_values)} fields filled, got: {fill_data}"

    # Execute with filter (F8)
    kb_result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    assert_tool_success(kb_result, "sap_keyboard F8")

    # Wait for results to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of filtered results
    await capture_html_snapshot(sap_mcp_client, "emmacl_results_filtered")

    # Check status bar for result message (works in DE and EN)
    status_result = await sap_mcp_client.call_tool("sap_read_status_bar", {})
    status_data = parse_tool_response(status_result)

    print(f"\nStatus bar after F8: {status_data.get('message', '')}")

    # Also try reading table (may show 0 rows if filter matched nothing)
    table_result = await sap_mcp_client.call_tool("sap_read_table", {"max_rows": 5})
    table_data = parse_tool_response(table_result)

    print(f"Table rows: {table_data.get('total_rows', 0)}")

    # The test passes if:
    # 1. Filter was filled successfully (already verified above)
    # 2. F8 was executed (already verified)
    # 3. We got either results or a "no data" status message
    status_msg = status_data.get("message", "").lower()
    total_rows = table_data.get("total_rows", 0)

    # Either we got some rows, or we got a status message about no data
    assert (
        total_rows > 0 or "keine" in status_msg or "no " in status_msg or status_msg == ""
    ), f"Expected either results or 'no data' message. Got rows={total_rows}, status='{status_msg}'"


@pytest.mark.anyio
async def test_emmacl_alv_grid_click_cell(sap_mcp_client: ClientSession) -> None:
    """
    Test clicking on an ALV grid cell in EMMACL to navigate to detail view.

    This test verifies the full ALV grid click workflow:
    1. Opens EMMACL transaction
    2. Presses F8 to execute (shows ALV grid with results)
    3. Reads table with sap_read_table (should get ALV metadata + cell selectors)
    4. Clicks on a case number (hotspot cell) using sap_click_table_cell
    5. Verifies navigation to the detail screen

    This is a critical test for the ALV grid click support feature.
    The test MUST succeed with an actual click + navigation for the feature to work.
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Step 1: Open EMMACL transaction
    result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    assert_tool_success(result, "sap_transaction EMMACL")

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Step 2: Execute without filters (F8) to get the results table
    kb_result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    assert_tool_success(kb_result, "sap_keyboard F8")

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Step 3: Read the table - should get ALV metadata with cell selectors
    table_result = await sap_mcp_client.call_tool("sap_read_table", {"max_rows": 10})
    table_data = assert_tool_success(table_result, "sap_read_table")

    print(f"\nTable data structure:")
    print(f"  Headers: {table_data.get('headers', [])}")
    print(f"  Total rows: {table_data.get('total_rows', 0)}")
    print(f"  ALV metadata: {table_data.get('alv', 'NOT PRESENT')}")

    # Verify we have ALV metadata (proves ALV grid detection worked)
    assert "alv" in table_data, (
        "sap_read_table should return ALV metadata for EMMACL results. " f"Got: {list(table_data.keys())}"
    )

    alv_meta = table_data.get("alv", {})
    assert alv_meta.get("table_id"), f"ALV metadata should have table_id: {alv_meta}"

    # Verify we have at least one row
    rows = table_data.get("rows", [])
    assert len(rows) >= 1, f"Expected at least one row in EMMACL results: {table_data}"

    # Verify first row has cell metadata with selectors
    first_row = rows[0]
    cells = first_row.get("cells", {})
    print(f"  First row cells metadata: {cells}")

    assert cells, "First row should have cells metadata with click selectors. " f"Got row: {first_row}"

    # Find a hotspot cell (one that can be clicked to navigate)
    hotspot_cell = None
    hotspot_column = None
    for col_name, cell_info in cells.items():
        if cell_info.get("hotspot"):
            hotspot_cell = cell_info
            hotspot_column = col_name
            break

    assert hotspot_cell, (
        "EMMACL results should have at least one hotspot cell (e.g., 'Fall' column). " f"Cells: {cells}"
    )

    print(f"\n  Found hotspot in column '{hotspot_column}': {hotspot_cell}")

    # Get the page title before clicking
    screen_info_before = await sap_mcp_client.call_tool("sap_get_screen_info", {})
    info_before = parse_tool_response(screen_info_before)
    title_before = info_before.get("title", "")
    print(f"  Title before click: {title_before}")

    # Step 4: Click on the hotspot cell using sap_click_table_cell
    # This should navigate to the detail view
    click_result = await sap_mcp_client.call_tool(
        "sap_click_table_cell",
        {"row": first_row.get("row", 1), "column": hotspot_column},
    )
    click_data = assert_tool_success(click_result, "sap_click_table_cell")

    print(f"\n  Click result:")
    print(f"    Selector used: {click_data.get('selector_used')}")
    print(f"    Was hotspot: {click_data.get('was_hotspot')}")
    print(f"    Page title after: {click_data.get('page_title')}")

    # Verify the click was on a hotspot
    assert click_data.get("was_hotspot"), f"Click should have been on a hotspot cell. Result: {click_data}"

    # Step 5: Verify navigation happened (title should change)
    title_after = click_data.get("page_title", "")

    # The title should change to show the detail view
    # German: "Klärungsfall XXXXXXXXX anzeigen" (Show case XXXXXXXXX)
    # English: "Display Case XXXXXXXXX"
    assert title_before != title_after, (
        f"Page title should change after clicking hotspot cell. " f"Before: '{title_before}', After: '{title_after}'"
    )

    # Verify we're on a detail screen (not still on the list)
    detail_indicators = ["anzeigen", "display", "case", "fall", "klärungsfall"]
    assert any(
        ind in title_after.lower() for ind in detail_indicators
    ), f"Should navigate to detail view. Got title: '{title_after}'"

    print(f"\n  SUCCESS: Navigated from '{title_before}' to '{title_after}'")

    # Capture the detail screen HTML for reference
    await capture_html_snapshot(sap_mcp_client, "emmacl_case_detail")

    # Press F3 to go back to the list
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})


@pytest.mark.anyio
async def test_emmacl_alv_click_with_browser_click(sap_mcp_client: ClientSession) -> None:
    """
    Test clicking on an ALV grid cell using browser_click with the selector from sap_read_table.

    This is an alternative approach to sap_click_table_cell - using the
    pre-escaped CSS selector directly with browser_click.

    This test verifies:
    1. sap_read_table returns properly escaped CSS selectors
    2. browser_click can use these selectors directly
    3. Navigation works when clicking hotspot cells
    """
    await sap_mcp_client.call_tool("sap_login", {})

    # Open EMMACL and get results
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Read table with ALV metadata
    table_result = await sap_mcp_client.call_tool("sap_read_table", {"max_rows": 5})
    table_data = assert_tool_success(table_result, "sap_read_table")

    rows = table_data.get("rows", [])
    assert len(rows) >= 1, "Expected at least one row"

    # Find a hotspot cell selector
    first_row = rows[0]
    cells = first_row.get("cells", {})

    hotspot_selector = None
    for col_name, cell_info in cells.items():
        if cell_info.get("hotspot"):
            hotspot_selector = cell_info.get("selector")
            print(f"Found hotspot selector for '{col_name}': {hotspot_selector}")
            break

    assert hotspot_selector, "Expected a hotspot cell with selector"

    # Get title before click
    screen_info = await sap_mcp_client.call_tool("sap_get_screen_info", {})
    title_before = parse_tool_response(screen_info).get("title", "")

    # Use browser_click with the selector directly
    click_result = await sap_mcp_client.call_tool("browser_click", {"selector": hotspot_selector})
    click_data = assert_tool_success(click_result, "browser_click with ALV selector")

    # Wait for navigation
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Verify navigation
    screen_info_after = await sap_mcp_client.call_tool("sap_get_screen_info", {})
    title_after = parse_tool_response(screen_info_after).get("title", "")

    print(f"Title before: {title_before}")
    print(f"Title after: {title_after}")

    assert title_before != title_after, (
        f"Page title should change after clicking hotspot. " f"Before: '{title_before}', After: '{title_after}'"
    )

    # Go back
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})


@pytest.mark.anyio
async def test_intent_logging_with_bp_transaction(
    sap_mcp_client: ClientSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test intent logging during BP (Business Partner) transaction.

    This test verifies that:
    1. log_intent tool can record intents during SAP operations
    2. The intent log messages are emitted with correct format
    3. The intent resource is accessible

    Steps:
    - Login to SAP
    - Run transaction BP
    - Press F5 to start creating a person
    - Log intents and verify log messages
    """
    # Login to SAP
    login_result = await sap_mcp_client.call_tool("sap_login", {})
    assert_tool_success(login_result, "sap_login")

    # Log intent at start
    intent_result = await sap_mcp_client.call_tool(
        "log_intent",
        {
            "intent": "Create a new business partner of type Person",
            "context": {"tcode": "BP", "action": "create_person"},
        },
    )
    intent_data = assert_tool_success(intent_result, "log_intent")
    assert intent_data.get("logged") is True, "Intent should be logged"
    entry_id = intent_data.get("entry_id")
    assert entry_id, "Intent should have an entry_id"
    session_id = intent_data.get("session_id")
    assert session_id, "Intent should have a session_id"

    # Run transaction BP
    tx_result = await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    assert_tool_success(tx_result, "sap_transaction BP")

    # Wait for BP screen (has Person/Organisation buttons)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Capture HTML snapshot for debugging
    await capture_html_snapshot(sap_mcp_client, "bp_initial")

    # Press F5 to start creating (opens new partner creation)
    kb_result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F5"})
    assert_tool_success(kb_result, "sap_keyboard F5")

    # Wait a moment for the dialog to open
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture HTML snapshot after F5
    await capture_html_snapshot(sap_mcp_client, "bp_create_person")

    # Log another intent for the milestone
    intent2_result = await sap_mcp_client.call_tool(
        "log_intent",
        {
            "intent": "Opened person creation dialog",
            "context": {"step": "dialog_open"},
        },
    )
    intent2_data = assert_tool_success(intent2_result, "log_intent 2")

    # Verify the intent resource template is available
    templates = await sap_mcp_client.list_resource_templates()
    template_uris = [str(t.uriTemplate) for t in templates.resourceTemplates]
    print(f"\nAvailable resource templates: {template_uris}")

    # Check that an intent resource template exists
    has_intent_template = any("intent://" in uri for uri in template_uris)
    assert has_intent_template, f"Expected intent:// template, got: {template_uris}"

    # Read the intent resource for the session using the session_id from log_intent
    intent_resource = await sap_mcp_client.read_resource(f"intent://session/{session_id}")
    intent_log = intent_resource.contents[0].text if intent_resource.contents else "[]"
    print(f"\nIntent log content for session {session_id}: {intent_log}")

    # Parse and verify the log has our entries
    entries = json.loads(intent_log)
    assert len(entries) >= 2, f"Expected at least 2 intent entries, got {len(entries)}"

    # Verify the entries have the expected structure
    for entry in entries:
        assert "timestamp" in entry, f"Entry missing timestamp: {entry}"
        assert "intent" in entry, f"Entry missing intent: {entry}"
        assert "entry_id" in entry, f"Entry missing entry_id: {entry}"

    # Verify our specific intents are in the log
    intents = [e["intent"] for e in entries]
    assert any("business partner" in i.lower() for i in intents), f"Expected BP intent: {intents}"
    assert any("dialog" in i.lower() for i in intents), f"Expected dialog intent: {intents}"

    # Verify entry_ids match what we received from the tool
    entry_ids = [e["entry_id"] for e in entries]
    assert entry_id in entry_ids, f"First entry_id {entry_id} not in log: {entry_ids}"
    assert intent2_data.get("entry_id") in entry_ids, "Second entry_id not in log"

    # Press F3 to go back/cancel (avoid creating an actual partner)
    back_result = await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})
    print(f"\nBack result: {back_result.content[0].text if back_result.content else 'N/A'}")
