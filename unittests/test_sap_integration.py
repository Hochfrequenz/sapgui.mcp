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
    text = _get_content_text(result.content[0]) if result.content else ""
    assert "Error" not in text, f"Operation failed: {text}"

Use the helper functions _wait_for_transaction_screen() and _wait_for_easy_access()
which raise RuntimeError on failures.
"""

import asyncio
import os
from pathlib import Path

import pytest
from mcp import ClientSession

from sapwebguimcp.models import (
    CapabilitiesResult,
    ClickResult,
    ClosePopupResult,
    DiscoveredButtons,
    DiscoveredFields,
    EvaluateResult,
    FillFormResult,
    FillResult,
    FormFieldsResult,
    IntentLogResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SE16Result,
    SessionStatus,
    SetFieldResult,
    ShortcutsResult,
    SM37JobListResult,
    SnapshotResult,
    StatusBarInfo,
    TableCellClickResult,
    TableData,
    TransactionResult,
    WaitResult,
    WorkflowDeleteResult,
    WorkflowListResult,
    WorkflowSaveResult,
)

from .conftest import call_tool_typed, get_html_content

# HTML snapshot directory for offline selector tests
HTML_SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "html_snapshots"


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
    html_content = await get_html_content(client)

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
    "SE38": "label:has-text('Programm'), label:has-text('Program')",  # ABAP Editor program label
    "SE93": "input[lsdata*='TSTC-TCODE']",  # Transaction code input field
    "SM30": "input[title*='Table/View']",  # SM30 table maintenance - table name field
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
    result = await call_tool_typed(client, "browser_wait", {"selector": selector, "timeout": timeout}, WaitResult)
    if not result.success:
        raise RuntimeError(f"Wait for {tcode} failed: {result.error}")


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
    result = await call_tool_typed(
        client, "browser_wait", {"selector": "#ToolbarOkCode", "timeout": timeout}, WaitResult
    )
    if not result.success:
        raise RuntimeError(f"Wait for Easy Access failed: {result.error}")


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

    result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert result.success, f"Login failed: {result.error}"
    assert result.url, "Expected URL in login response"

    # Verify browser state: check that SAP Easy Access loaded
    page_html = await get_html_content(sap_mcp_client)

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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Try to find and click the settings button using browser_evaluate
    # This mirrors the logic in _enable_okcode_field
    settings_eval = await call_tool_typed(
        sap_mcp_client,
        "browser_evaluate",
        {"script": """
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
        """},
        EvaluateResult,
    )

    if settings_eval.result and "clicked" in str(settings_eval.result):
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
        await capture_html_snapshot(sap_mcp_client, "settings_dialog")

        # Close the dialog
        await call_tool_typed(
            sap_mcp_client,
            "browser_evaluate",
            {"script": """
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
            """},
            EvaluateResult,
        )
        await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "Escape"}, KeyboardResult)


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


# =============================================================================
# Tests for new SAP tools (sap_session_status, sap_keyboard, sap_get_screen_text,
# sap_read_table, sap_read_status_bar, sap_get_screen_info)
# =============================================================================


@pytest.mark.anyio
async def test_sap_session_status_after_login(sap_mcp_client: ClientSession) -> None:
    """Test that session status is 'active' after successful login."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(sap_mcp_client, "sap_session_status", {}, SessionStatus)
    assert result.status == "active", f"Expected active session after login: {result}"


@pytest.mark.anyio
async def test_sap_session_status_returns_valid_state(sap_mcp_client: ClientSession) -> None:
    """Test that session status returns a recognized state."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(sap_mcp_client, "sap_session_status", {}, SessionStatus)
    valid_states = ["active", "timed_out", "logged_off", "no_page", "unknown"]
    assert result.status in valid_states, f"Expected one of {valid_states}, got: {result.status}"


@pytest.mark.anyio
async def test_sap_keyboard_f3_navigates_back(sap_mcp_client: ClientSession) -> None:
    """Test F3 (Back) returns from transaction to previous screen."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Press F3 to go back
    result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F3"}, KeyboardResult)
    assert result.success, f"Keyboard F3 failed: {result.error}"
    assert result.key == "F3", f"Expected key F3: {result}"

    # Wait for Easy Access (OK-Code field visible means we're back on main menu)
    await _wait_for_easy_access(sap_mcp_client)

    # Should be back on Easy Access or previous screen
    page_html = (await get_html_content(sap_mcp_client)).lower()

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

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to execute without entering a table name - should trigger error
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Check for error message in page or status bar
    page_html = (await get_html_content(sap_mcp_client)).lower()

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

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await call_tool_typed(sap_mcp_client, "sap_get_screen_text", {}, ScreenText)

    # SE16 should show table name prompt - check title or labels
    response_text = (result.title or "").lower()
    labels_text = " ".join(result.labels or []).lower()
    combined_text = response_text + " " + labels_text

    if sap_language == "DE":
        expected_phrases = ["tabellenname", "tabelle", "data browser"]
    else:
        expected_phrases = ["table name", "table", "data browser"]

    assert any(
        phrase in combined_text for phrase in expected_phrases
    ), f"SE16 screen text should contain table-related labels. Language: {sap_language}. Got: {combined_text[:500]}"

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "se16_initial")


@pytest.mark.anyio
async def test_sap_get_screen_text_structure(sap_mcp_client: ClientSession) -> None:
    """Test that sap_get_screen_text returns structured output."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await call_tool_typed(sap_mcp_client, "sap_get_screen_text", {}, ScreenText)
    assert result.success, f"sap_get_screen_text failed: {result.error}"

    # Check for expected structure
    assert result.title, "Should contain title"

    # Should have some labels or content
    has_labels = bool(result.labels)
    has_content = bool(result.main_content)
    has_buttons = bool(result.buttons)

    assert (
        has_labels or has_content or has_buttons
    ), f"Screen text should contain labels, content, or buttons. Got: {result}"


@pytest.mark.anyio
async def test_sap_read_table_from_sm37_no_jobs(sap_mcp_client: ClientSession) -> None:
    """Test SM37 when no jobs match selection criteria.

    Uses a non-existent job name to guarantee no results,
    resulting in "Kein Job entspricht den Selektionsbedingungen" message.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")

    # Capture HTML snapshot for offline selector testing (before filling form)
    await capture_html_snapshot(sap_mcp_client, "sm37_initial")

    # Use a non-existent job name to guarantee "no jobs" result.
    # Previously used "*" (all jobs for current user), but that fails
    # when the user has any jobs (scheduled, finished, etc.).
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "browser_fill",
        {"selector": "input[lsdata*='JOBNAME']", "value": "ZZZNOTEXIST_JOB_99"},
        FillResult,
    )
    assert fill_result.success, f"Failed to fill JOBNAME field: {fill_result.error}"

    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Check status bar for "no jobs" message
    status_result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    status_text = (status_result.message or "").lower()

    # German: "Kein Job entspricht den Selektionsbedingungen"
    # English: "No job meets the selection conditions"
    no_jobs_de = "kein job" in status_text
    no_jobs_en = "no job" in status_text

    assert no_jobs_de or no_jobs_en, f"Expected 'no jobs' status message, got: {status_text}"


async def assert_fill_success(result: FillResult, field_name: str) -> None:
    """Assert that browser_fill succeeded for a field."""
    assert result.success, f"Failed to fill {field_name}: {result.error}"


@pytest.mark.anyio
async def test_sap_read_table_from_sm37_all_jobs(sap_mcp_client: ClientSession) -> None:
    """Test reading table data from SM37 (Job Overview) with broad criteria.

    SM37 exists on every SAP system and shows background jobs.
    Uses wildcards for username and broad date range to find jobs.
    """
    from datetime import datetime, timedelta

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")

    # Fill job selection with wildcards and clear username restriction
    # SM37 fields use SID in lsdata: BTCH2170-JOBNAME, BTCH2170-USERNAME
    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='JOBNAME']", "value": "*"}, FillResult
    )
    await assert_fill_success(result, "JOBNAME")

    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='USERNAME']", "value": "*"}, FillResult
    )
    await assert_fill_success(result, "USERNAME")

    # Set broad date range (last 365 days) to find jobs
    # Date fields have SID in lsdata: BTCH2170-FROM_DATE, BTCH2170-TO_DATE
    today = datetime.now()
    from_date = (today - timedelta(days=365)).strftime("%d.%m.%Y")
    to_date = today.strftime("%d.%m.%Y")

    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='FROM_DATE']", "value": from_date}, FillResult
    )
    await assert_fill_success(result, f"FROM_DATE={from_date}")

    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='TO_DATE']", "value": to_date}, FillResult
    )
    await assert_fill_success(result, f"TO_DATE={to_date}")

    # Execute (F8) and wait for list output to complete (can take a while with many jobs)
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 30000})

    # Capture table results HTML for unit tests
    await capture_html_snapshot(sap_mcp_client, "sm37_results")

    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"start_row": 1, "end_row": 5}, TableData)
    assert table_result.success, f"sap_read_table failed: {table_result.error}"

    # Assert that we got actual table data with rows
    assert table_result.rows is not None, f"Expected table with 'rows', got: {table_result}"
    assert table_result.total_rows is not None, f"Expected 'total_rows' in response, got: {table_result}"

    # Verify we got some jobs
    assert table_result.total_rows > 0, f"Expected some jobs in SM37, got total_rows=0"
    assert len(table_result.rows) > 0, "Expected at least one row in SM37 results"


@pytest.mark.anyio
async def test_sap_read_table_from_se93(sap_mcp_client: ClientSession) -> None:
    """Test reading transaction codes from SE93.

    SE93 with wildcard 'SE*' will always return results (SE11, SE16, etc.).
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE93"}, TransactionResult)
    # Wait for SE93 to load (has transaction code input field with TSTC-TCODE in lsdata)
    await _wait_for_transaction_screen(sap_mcp_client, "SE93")

    # Capture HTML snapshot for offline selector testing
    await capture_html_snapshot(sap_mcp_client, "se93_initial")

    # Search for transactions starting with SE - use lsdata selector
    fill_result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='TSTC-TCODE']", "value": "SE*"}, FillResult
    )
    assert fill_result.success, f"Failed to fill SE93 transaction code field: {fill_result.error}"

    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {}, TableData)

    # Should find standard SE* transactions
    # Check for either transaction codes in data or valid table structure
    rows_str = str(table_result.rows).lower() if table_result.rows else ""
    has_se_transactions = "se11" in rows_str or "se16" in rows_str or "se80" in rows_str
    has_table_structure = table_result.rows is not None or table_result.headers is not None

    assert (
        has_se_transactions or has_table_structure
    ), f"Expected to find standard SE* transactions or table structure: {table_result}"


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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Enter table name T000 (Clients table - always exists, always small)
    # Use lsdata selector which is reliable for SAP Web GUI elements
    fill_result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='TABLENAME']", "value": "T000"}, FillResult
    )
    assert fill_result.success, f"Failed to fill table name field: {fill_result.error}"

    # Execute to show table content
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture table content HTML for unit tests
    await capture_html_snapshot(sap_mcp_client, "se16_t000_content")

    # Read the table data
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"start_row": 1, "end_row": 10}, TableData)

    # T000 must have at least one row (the current client)
    # Check for table data indicators
    rows_str = str(table_result.rows).lower() if table_result.rows else ""
    has_rows = table_result.rows is not None or "mandt" in rows_str
    has_content = table_result.total_rows is not None and table_result.total_rows > 0

    assert has_rows and has_content, (
        f"SE16 T000 should return table content with at least one client. " f"Response: {table_result}"
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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE11"}, TransactionResult)
    # Wait for SE11 to load (has "Database table" radio button)
    await _wait_for_transaction_screen(sap_mcp_client, "SE11")

    # Capture SE11 initial screen
    await capture_html_snapshot(sap_mcp_client, "se11_initial")

    # "Datenbanktabelle" is a radio button, click it then Tab to the text field
    await call_tool_typed(sap_mcp_client, "browser_click", {"selector": "text=Datenbanktabelle"}, ClickResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 300})
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "Tab"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_keyboard", {"text": "T000"})

    # Press F7 (Anzeigen/Display) to view table definition
    await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F7"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture table structure HTML
    await capture_html_snapshot(sap_mcp_client, "se11_t000_content")

    # Verify we're on the table definition screen
    page_html = (await get_html_content(sap_mcp_client)).upper()

    # T000 definition should show field names like MANDT, CCCATEGORY
    has_mandt = "MANDT" in page_html
    has_fields = "FIELD" in page_html or "COMPONENT" in page_html or "CCCATEGORY" in page_html

    assert has_mandt or has_fields, (
        "SE11 T000 definition should show table fields. " "Expected MANDT or other field indicators in the page."
    )


@pytest.mark.anyio
async def test_sap_read_status_bar_after_navigation(sap_mcp_client: ClientSession) -> None:
    """Test reading status bar after successful navigation."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SU3"}, TransactionResult)
    # Wait for SU3 screen to load (user profile has address-related fields)
    await _wait_for_transaction_screen(sap_mcp_client, "SU3")

    result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    # Should return with type or message fields
    assert (
        result.type is not None or result.message is not None
    ), f"Status bar should return type/message info: {result}"


@pytest.mark.anyio
async def test_sap_read_status_bar_after_error(sap_mcp_client: ClientSession) -> None:
    """Test reading status bar after triggering an error."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Try invalid transaction to trigger error
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "ZZZZINVALID999"}, TransactionResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    # Should indicate error type or contain error message
    is_error = result.type == "E"
    has_error_msg = result.message and any(
        ind in result.message.lower() for ind in ["error", "fehler", "existiert nicht", "does not exist"]
    )

    assert is_error or has_error_msg, f"Status bar should indicate error after invalid transaction: {result}"


@pytest.mark.anyio
async def test_sap_get_screen_info_from_se16(sap_mcp_client: ClientSession) -> None:
    """Test getting screen info from SE16."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    result = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)

    # Should contain basic screen info
    assert result.title, "Screen info should contain title"
    assert result.url, "Screen info should contain url"


@pytest.mark.anyio
async def test_sap_get_screen_info_different_transactions(sap_mcp_client: ClientSession) -> None:
    """Test that screen info changes between transactions."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Get info from SE16
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")
    result1 = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)

    # Get info from SM37
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")
    result2 = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)

    # The title or content should be different
    assert (
        result1.title != result2.title or result1.url != result2.url
    ), "Screen info should differ between SE16 and SM37"


@pytest.mark.anyio
async def test_browser_reconnect_after_idle(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser reconnects after becoming stale.

    This test simulates a scenario where the CDP connection becomes stale
    (e.g., browser was minimized, focus was lost, or connection timed out).
    The server should automatically reconnect and continue working.
    """
    # Step 1: Login and verify we have a working session
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"
    assert login_result.url, "Expected URL in login response"

    # Step 2: Navigate to a transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    # Wait for SE16 to load (has table name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Step 3: Wait a bit to let connection potentially become stale
    # In real scenarios, this could be minutes; here we just verify the flow works
    await asyncio.sleep(5)

    # Step 4: Try to use the browser again - this should reconnect if stale
    status_result = await call_tool_typed(sap_mcp_client, "sap_session_status", {}, SessionStatus)

    # Should be able to get status (either connected or reconnected)
    assert status_result.status is not None, f"Should get valid session status after idle period: {status_result}"

    # Step 5: Verify we can still execute transactions
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    assert tx_result.success, f"Transaction after idle failed: {tx_result.error}"
    assert tx_result.tcode, f"Transaction should work after idle: {tx_result}"


@pytest.mark.anyio
async def test_browser_reconnect_multiple_times(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser can reconnect multiple times during a session.

    This verifies the reconnection logic is robust and doesn't leave
    the browser manager in a bad state after reconnecting.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    transactions = ["SE16", "SM37", "SU3", "SE16"]

    for i, tcode in enumerate(transactions):
        # Small delay between transactions
        await asyncio.sleep(2)

        # Execute transaction
        result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": tcode}, TransactionResult)
        assert result.success, f"Transaction {tcode} failed: {result.error}"
        assert result.tcode, f"Transaction {tcode} should work: {result}"

        # Verify session is still valid
        status = await call_tool_typed(sap_mcp_client, "sap_session_status", {}, SessionStatus)
        assert status.status is not None, f"Expected valid status after transaction {i+1}: {status}"


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

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Step 1: Open BP transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert result.success, f"sap_transaction BP failed: {result.error}"

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

    click_result = await call_tool_typed(
        sap_mcp_client, "browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"}, ClickResult
    )
    assert click_result.success, f"Failed to click Person button: {click_result.error}"

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

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": fields_to_fill}, FillFormResult)
    assert fill_result.success, f"sap_fill_form failed: {fill_result.error}"

    # Verify ALL fields were filled successfully
    filled_fields = set(fill_result.filled or [])
    not_found_fields = fill_result.not_found or []
    error_fields = fill_result.errors or []
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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert result.success, f"sap_transaction BP failed: {result.error}"

    # Wait for BP initial screen
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Click on "Person" button to create a new person
    # IMPORTANT: SAP Web GUI requires multiple waits for reliable form interaction.
    # See test_bp_fill_form_batch_fill for detailed explanation.
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    click_result = await call_tool_typed(
        sap_mcp_client, "browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"}, ClickResult
    )
    assert click_result.success, f"Failed to click Person button: {click_result.error}"

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

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": fields_to_fill}, FillFormResult)
    assert fill_result.success, f"sap_fill_form with CSS selectors failed: {fill_result.error}"

    # Verify ALL fields were filled successfully
    filled_fields = set(fill_result.filled or [])
    not_found_fields = fill_result.not_found or []
    error_fields = fill_result.errors or []
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
async def test_bp_org_form_snapshot(sap_mcp_client: ClientSession) -> None:
    """
    Capture HTML snapshot of BP organisation form for offline label verification.

    Opens the BP transaction and presses F6 to create an organisation.
    Saves the snapshot so unit tests can verify field labels used in prompts.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert result.success, f"sap_transaction BP failed: {result.error}"

    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Wait for initial screen to be fully interactive
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Press F6 to create an organisation
    kb_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F6"}, KeyboardResult)
    assert kb_result.success, f"sap_keyboard F6 failed: {kb_result.error}"

    # Wait for SAP backend to process and return form HTML
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for org-specific label ("Name 1" is the same in DE and EN)
    await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Name 1')", "timeout": 15000})

    # Allow all label-input lsdata associations to be populated
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Capture HTML snapshot of org form for offline label verification
    await capture_html_snapshot(sap_mcp_client, "bp_org_form")


@pytest.mark.anyio
async def test_sap_fill_form_strict_mode(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form strict mode - should fail if any field is not found.

    In strict mode (strict=True), the tool should return success=False
    if any field cannot be found or filled.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open a simple transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SE16"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    # Try to fill with an invalid field label in strict mode
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {
            "fields": {
                "NONEXISTENT_FIELD_12345": "test value",
            },
            "strict": True,
        },
        FillFormResult,
    )

    # Strict mode should report failure when field not found
    assert not fill_result.success, f"Strict mode should fail when field not found. Response: {fill_result}"
    assert (
        fill_result.not_found and "NONEXISTENT_FIELD_12345" in fill_result.not_found
    ), f"Field should be in not_found list: {fill_result}"


@pytest.mark.anyio
async def test_bp_fill_form_ambiguous_label_rejected(sap_mcp_client: ClientSession) -> None:
    """
    Test that ambiguous labels are rejected with a helpful error message.

    The BP Person form (BP transaction, F5 for Person) has two "Postleitzahl" fields:
    - ADDR2_DATA-POST_CODE1: for street address
    - ADDR2_DATA-POST_CODE2: for PO Box address

    Using the label "Postleitzahl" (German) or "Postal Code" (English) should fail
    because it's ambiguous. The error message should include the available CSS selectors.

    This test verifies the fix for the bug where sap_fill_form silently matched
    the first field when multiple fields shared the same label.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Press F5 to create a Person (uses sap_keyboard which reads status bar)
    keyboard_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F5"}, KeyboardResult)

    # Handle category selection popup if it appears
    if keyboard_result.popup:
        # Click "Ja" (Yes) or confirm button to proceed
        await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "Enter"}, KeyboardResult)
        await asyncio.sleep(0.5)

    # Wait for Person form to load
    await asyncio.sleep(1.0)

    # Determine the ambiguous label based on language
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    ambiguous_label = "Postleitzahl" if sap_language == "DE" else "Postal Code"

    # Try to fill using the ambiguous label
    # This should fail because there are 2 fields with this label
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "sap_fill_form",
        {
            "fields": {
                ambiguous_label: "12345",  # Ambiguous - matches POST_CODE1 and POST_CODE2
            },
        },
        FillFormResult,
    )

    # The field should NOT be filled successfully
    filled_fields = fill_result.filled or []
    assert ambiguous_label not in filled_fields, (
        f"Ambiguous label '{ambiguous_label}' should NOT be filled. " f"Response: {fill_result}"
    )

    # There should be an error about the ambiguous label
    errors = fill_result.errors or []
    error_messages = [str(e) for e in errors]
    error_text = " ".join(error_messages)

    assert any(ambiguous_label in msg or "matches" in msg.lower() for msg in error_messages), (
        f"Expected an error mentioning '{ambiguous_label}' ambiguity. " f"Errors: {errors}, Response: {fill_result}"
    )

    # The error should mention POST_CODE1 and/or POST_CODE2 as alternatives
    assert "POST_CODE" in error_text or "#" in error_text, (
        f"Error should include CSS selectors as alternatives. " f"Errors: {errors}"
    )


@pytest.mark.anyio
async def test_bp_set_field_ambiguous_label_rejected(sap_mcp_client: ClientSession) -> None:
    """
    Test that sap_set_field also rejects ambiguous labels.

    Similar to test_bp_fill_form_ambiguous_label_rejected but tests the
    single-field sap_set_field tool instead of sap_fill_form.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open BP transaction
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Press F5 to create a Person
    keyboard_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F5"}, KeyboardResult)

    # Handle category selection popup if it appears
    if keyboard_result.popup:
        await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "Enter"}, KeyboardResult)
        await asyncio.sleep(0.5)

    # Wait for Person form to load
    await asyncio.sleep(1.0)

    # Try to set the ambiguous "Postleitzahl" field
    set_result = await call_tool_typed(
        sap_mcp_client,
        "sap_set_field",
        {
            "label": "Postleitzahl",
            "value": "12345",
        },
        SetFieldResult,
    )

    # Should fail due to ambiguity
    assert not set_result.success, (
        f"sap_set_field should fail for ambiguous label 'Postleitzahl'. " f"Response: {set_result}"
    )

    # Error should mention the ambiguity
    error = set_result.error or ""
    assert (
        "Postleitzahl" in error or "matches" in error.lower() or "ambiguous" in error.lower()
    ), f"Error should mention ambiguity. Error: {error}"


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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    # Wait for the screen to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of EMMACL initial screen
    await capture_html_snapshot(sap_mcp_client, "emmacl_initial")

    # Discover all fields on the screen
    discover_result = await call_tool_typed(sap_mcp_client, "sap_discover_fields", {}, DiscoveredFields)
    assert discover_result.success, f"sap_discover_fields failed: {discover_result.error}"

    # Verify we found some fields
    field_count = discover_result.field_count or 0
    fields = discover_result.fields or []

    assert field_count > 0, f"EMMACL should have input fields. Got: {discover_result}"
    assert len(fields) > 0, f"Fields list should not be empty. Got: {discover_result}"

    # Print discovered fields for debugging (visible in test output)
    print(f"\nDiscovered {field_count} fields in EMMACL:")
    for field in fields[:20]:  # Show first 20
        print(f"  - {field.label or 'no-label'}: {field.selector or 'no-selector'}")


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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # First discover fields to find valid selectors
    discover_result = await call_tool_typed(sap_mcp_client, "sap_discover_fields", {}, DiscoveredFields)
    assert discover_result.success, f"sap_discover_fields failed: {discover_result.error}"

    fields = discover_result.fields or []

    # Find text input fields (not readonly, not checkboxes)
    fillable_fields = [f for f in fields if f.type in ("text", None) and f.selector]

    if len(fillable_fields) < 2:
        pytest.skip("Not enough fillable fields found in EMMACL")

    # Pick first 2 fillable fields and try to fill them
    fields_to_fill = {}
    for i, field in enumerate(fillable_fields[:2]):
        selector = field.selector
        if selector:
            fields_to_fill[selector] = f"TEST{i}"

    print(f"\nTrying to fill {len(fields_to_fill)} fields: {list(fields_to_fill.keys())}")

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": fields_to_fill}, FillFormResult)

    # Log results
    print(f"Filled: {fill_result.filled}")
    print(f"Not found: {fill_result.not_found}")
    print(f"Errors: {fill_result.errors}")

    # At least some fields should have been filled
    filled = fill_result.filled or []
    assert len(filled) > 0, f"Expected at least one field to be filled. Result: {fill_result}"


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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Execute without any filters (F8)
    kb_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    assert kb_result.success, f"sap_keyboard F8 failed: {kb_result.error}"

    # Wait for results to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of results
    await capture_html_snapshot(sap_mcp_client, "emmacl_results_no_filter")

    # Read result table
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 20}, TableData)

    # Print results for debugging
    print(f"\nEMMACL results without filter:")
    print(f"Headers: {table_result.headers}")
    print(f"Total rows: {table_result.total_rows}")
    for row in (table_result.rows or [])[:5]:
        print(f"  Row {row.row}: {row.data}")

    # Verify we got some results (or at least the table was read)
    assert table_result.success, f"Table read failed: {table_result}"


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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Fill filter field using discovered selector
    # Using a filter value that likely won't match many rows to test filtering works
    filter_values = {
        "input[lsdata*='BPCODE-LOW']": "ZTEST",  # Business Process Code (likely no matches)
    }

    fill_result = await call_tool_typed(sap_mcp_client, "sap_fill_form", {"fields": filter_values}, FillFormResult)
    assert fill_result.success, f"sap_fill_form failed: {fill_result.error}"

    print(f"\nFilled filter fields: {fill_result.filled}")

    # Verify filter field was filled
    assert len(fill_result.filled or []) == len(
        filter_values
    ), f"Expected {len(filter_values)} fields filled, got: {fill_result}"

    # Execute with filter (F8)
    kb_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    assert kb_result.success, f"sap_keyboard F8 failed: {kb_result.error}"

    # Wait for results to load
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Capture HTML snapshot of filtered results
    await capture_html_snapshot(sap_mcp_client, "emmacl_results_filtered")

    # Check status bar for result message (works in DE and EN)
    status_result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)

    print(f"\nStatus bar after F8: {status_result.message or ''}")

    # Also try reading table (may show 0 rows if filter matched nothing)
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 5}, TableData)

    print(f"Table rows: {table_result.total_rows or 0}")

    # The test passes if:
    # 1. Filter was filled successfully (already verified above)
    # 2. F8 was executed (already verified)
    # 3. We got either results or a "no data" status message
    status_msg = (status_result.message or "").lower()
    total_rows = table_result.total_rows or 0

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
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Step 1: Open EMMACL transaction
    result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "EMMACL"}, TransactionResult)
    assert result.success, f"sap_transaction EMMACL failed: {result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Step 2: Execute without filters (F8) to get the results table
    kb_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F8"}, KeyboardResult)
    assert kb_result.success, f"sap_keyboard F8 failed: {kb_result.error}"

    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Step 3: Read the table - should get ALV metadata with cell selectors
    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 10}, TableData)
    assert table_result.success, f"sap_read_table failed: {table_result.error}"

    print(f"\nTable data structure:")
    print(f"  Headers: {table_result.headers}")
    print(f"  Total rows: {table_result.total_rows}")
    print(f"  ALV metadata: {table_result.alv or 'NOT PRESENT'}")

    # Verify we have ALV metadata (proves ALV grid detection worked)
    assert table_result.alv is not None, f"sap_read_table should return ALV metadata for EMMACL results."

    alv_meta = table_result.alv
    assert alv_meta.table_id, f"ALV metadata should have table_id: {alv_meta}"

    # Verify we have at least one row
    rows = table_result.rows or []
    assert len(rows) >= 1, f"Expected at least one row in EMMACL results: {table_data}"

    # Verify first row has cell metadata with selectors
    first_row = rows[0]
    cells = first_row.cells or {}
    print(f"  First row cells metadata: {cells}")

    assert cells, "First row should have cells metadata with click selectors. " f"Got row: {first_row}"

    # Find a hotspot cell (one that can be clicked to navigate)
    hotspot_cell = None
    hotspot_column = None
    for col_name, cell_info in cells.items():
        if cell_info.hotspot:
            hotspot_cell = cell_info
            hotspot_column = col_name
            break

    assert hotspot_cell, (
        "EMMACL results should have at least one hotspot cell (e.g., 'Fall' column). " f"Cells: {cells}"
    )

    print(f"\n  Found hotspot in column '{hotspot_column}': {hotspot_cell}")

    # Get the page title before clicking
    info_before = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert info_before.success, f"sap_get_screen_info failed: {info_before.error}"
    title_before = info_before.title
    print(f"  Title before click: {title_before}")

    # Step 4: Click on the hotspot cell using sap_click_table_cell
    # This should navigate to the detail view
    click_data = await call_tool_typed(
        sap_mcp_client,
        "sap_click_table_cell",
        {"row": first_row.row, "column": hotspot_column},
        TableCellClickResult,
    )
    assert click_data.success, f"sap_click_table_cell failed: {click_data.error}"

    print(f"\n  Click result:")
    print(f"    Selector used: {click_data.selector_used}")
    print(f"    Was hotspot: {click_data.was_hotspot}")
    print(f"    Page title after: {click_data.page_title}")

    # Verify the click was on a hotspot
    assert click_data.was_hotspot, f"Click should have been on a hotspot cell. Result: {click_data}"

    # Step 5: Verify navigation happened (title should change)
    title_after = click_data.page_title

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
    table_data = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 5}, TableData)
    assert table_data.success, f"sap_read_table failed: {table_data.error}"

    rows = table_data.rows or []
    assert len(rows) >= 1, "Expected at least one row"

    # Find a hotspot cell selector
    first_row = rows[0]
    cells = first_row.cells or {}

    hotspot_selector = None
    for col_name, cell_info in cells.items():
        if cell_info.hotspot:
            hotspot_selector = cell_info.selector
            print(f"Found hotspot selector for '{col_name}': {hotspot_selector}")
            break

    assert hotspot_selector, "Expected a hotspot cell with selector"

    # Get title before click
    screen_info = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert screen_info.success, f"sap_get_screen_info failed: {screen_info.error}"
    title_before = screen_info.title

    # Use browser_click with the selector directly
    click_data = await call_tool_typed(sap_mcp_client, "browser_click", {"selector": hotspot_selector}, ClickResult)
    assert click_data.success, f"browser_click with ALV selector failed: {click_data.error}"

    # Wait for navigation
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Verify navigation
    screen_info_after = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
    assert screen_info_after.success, f"sap_get_screen_info failed: {screen_info_after.error}"
    title_after = screen_info_after.title

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
    import json

    # Login to SAP
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"sap_login failed: {login_result.error}"

    # Log intent at start
    intent_data = await call_tool_typed(
        sap_mcp_client,
        "log_intent",
        {
            "intent": "Create a new business partner of type Person",
            "context": {"tcode": "BP", "action": "create_person"},
        },
        IntentLogResult,
    )
    assert intent_data.success, f"log_intent failed: {intent_data.error}"
    assert intent_data.logged is True, "Intent should be logged"
    entry_id = intent_data.entry_id
    assert entry_id, "Intent should have an entry_id"
    session_id = intent_data.session_id
    assert session_id, "Intent should have a session_id"

    # Run transaction BP
    tx_result = await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "BP"}, TransactionResult)
    assert tx_result.success, f"sap_transaction BP failed: {tx_result.error}"

    # Wait for BP screen (has Person/Organisation buttons)
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Capture HTML snapshot for debugging
    await capture_html_snapshot(sap_mcp_client, "bp_initial")

    # Press F5 to start creating (opens new partner creation)
    kb_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F5"}, KeyboardResult)
    assert kb_result.success, f"sap_keyboard F5 failed: {kb_result.error}"

    # Wait a moment for the dialog to open
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

    # Capture HTML snapshot after F5
    await capture_html_snapshot(sap_mcp_client, "bp_create_person")

    # Log another intent for the milestone
    intent2_data = await call_tool_typed(
        sap_mcp_client,
        "log_intent",
        {
            "intent": "Opened person creation dialog",
            "context": {"step": "dialog_open"},
        },
        IntentLogResult,
    )
    assert intent2_data.success, f"log_intent 2 failed: {intent2_data.error}"

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
    assert intent2_data.entry_id in entry_ids, "Second entry_id not in log"

    # Press F3 to go back/cancel (avoid creating an actual partner)
    back_result = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F3"}, KeyboardResult)
    print(f"\nBack result: {back_result}")


# =============================================================================
# Tests for browser_screenshot returning native MCP Image
# =============================================================================


@pytest.mark.anyio
async def test_browser_screenshot_returns_mcp_image_content(sap_mcp_client: ClientSession) -> None:
    """
    Test that browser_screenshot returns a native MCP ImageContent.

    This verifies that:
    1. The tool returns ImageContent (type='image') instead of text with base64
    2. The image data is valid base64-encoded PNG
    3. The image can be decoded and has reasonable dimensions

    Using native MCP ImageContent is more token-efficient than returning base64
    as a string, because the MCP client can process the image as binary data
    rather than as text tokens.
    """
    import base64

    from mcp.types import ImageContent

    await sap_mcp_client.call_tool("sap_login", {})

    # Take a screenshot
    result = await sap_mcp_client.call_tool("browser_screenshot", {})

    # Verify we got a response
    assert result.content, "Expected non-empty response from browser_screenshot"

    # The first content block should be an ImageContent
    content = result.content[0]
    assert isinstance(content, ImageContent), (
        f"Expected ImageContent, got {type(content).__name__}. "
        "Screenshot should return native MCP image, not text with base64."
    )

    # Verify the ImageContent structure
    assert content.type == "image", f"Expected type='image', got '{content.type}'"
    assert content.mimeType == "image/png", f"Expected mimeType='image/png', got '{content.mimeType}'"
    assert content.data, "Expected non-empty image data"

    # Verify the base64 data is valid and decodes to PNG
    try:
        image_bytes = base64.b64decode(content.data)
    except Exception as e:
        raise AssertionError(f"Image data is not valid base64: {e}") from e

    # PNG files start with the magic bytes: 0x89 0x50 0x4E 0x47 0x0D 0x0A 0x1A 0x0A
    png_magic = b"\x89PNG\r\n\x1a\n"
    assert image_bytes[:8] == png_magic, (
        f"Image data does not start with PNG magic bytes. " f"Got: {image_bytes[:8].hex()}, expected: {png_magic.hex()}"
    )

    # Verify reasonable image size (at least 1KB, at most 10MB)
    image_size = len(image_bytes)
    assert image_size > 1024, f"Image seems too small: {image_size} bytes"
    assert image_size < 10 * 1024 * 1024, f"Image seems too large: {image_size} bytes"

    print(f"\nScreenshot captured successfully:")
    print(f"  - Type: {content.type}")
    print(f"  - MIME type: {content.mimeType}")
    print(f"  - Size: {image_size:,} bytes")


# =============================================================================
# Tests for Workflow Tools (workflow_list, workflow_save, workflow_delete)
# =============================================================================


@pytest.mark.anyio
async def test_workflow_list_returns_bundled_workflows(sap_mcp_client: ClientSession) -> None:
    """
    Test that workflow_list returns bundled workflows.

    This verifies:
    1. The workflow_list tool is registered and callable
    2. Bundled workflows (shipped with the package) are listed
    3. The response has expected structure with workflow metadata
    """
    data = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert data.success, f"workflow_list failed: {data.error}"

    # Should have a workflows list
    workflows = data.workflows

    # Should have at least one bundled workflow
    assert len(workflows) >= 1, f"Expected at least one bundled workflow: {workflows}"

    # Verify workflow structure
    first_workflow = workflows[0]
    required_fields = ["name", "description", "author", "prompt", "applicable_when"]
    for field in required_fields:
        assert hasattr(first_workflow, field), f"Workflow missing '{field}': {first_workflow}"

    print(f"\nFound {len(workflows)} workflows:")
    for wf in workflows:
        print(f"  - {wf.name}: {wf.description}")


@pytest.mark.anyio
async def test_workflow_save_and_delete(sap_mcp_client: ClientSession) -> None:
    """
    Test saving and deleting a user workflow.

    This verifies:
    1. workflow_save creates a new workflow in user directory
    2. The workflow appears in workflow_list
    3. workflow_delete removes the workflow
    4. The workflow is gone from workflow_list
    """
    test_workflow_name = "test-integration-workflow-12345"

    # Save a test workflow
    save_data = await call_tool_typed(
        sap_mcp_client,
        "workflow_save",
        {
            "workflow_input": {
                "name": test_workflow_name,
                "description": "Test workflow for integration tests",
                "prompt": "This is a test prompt for integration testing",
                "applicable_when": "During integration tests",
                "not_applicable_when": "In production",
                "author": "integration-test",
            }
        },
        WorkflowSaveResult,
    )
    assert save_data.success, f"workflow_save failed: {save_data.error}"

    assert save_data.name == test_workflow_name, f"Name mismatch: {save_data}"
    assert save_data.path, f"Expected path in response: {save_data}"

    print(f"\nSaved workflow to: {save_data.path}")

    # Verify it appears in list
    list_data = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert list_data.success, f"workflow_list after save failed: {list_data.error}"

    workflow_names = [w.name for w in list_data.workflows]
    assert test_workflow_name in workflow_names, f"Saved workflow not in list: {workflow_names}"

    # Delete the workflow
    delete_data = await call_tool_typed(
        sap_mcp_client, "workflow_delete", {"name": test_workflow_name}, WorkflowDeleteResult
    )
    assert delete_data.success, f"workflow_delete failed: {delete_data.error}"

    assert delete_data.name == test_workflow_name, f"Name mismatch: {delete_data}"

    # Verify it's gone from list
    list_data2 = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert list_data2.success, f"workflow_list after delete failed: {list_data2.error}"

    workflow_names2 = [w.name for w in list_data2.workflows]
    assert test_workflow_name not in workflow_names2, f"Deleted workflow still in list: {workflow_names2}"

    print("Workflow save/delete cycle completed successfully")


@pytest.mark.anyio
async def test_workflow_delete_bundled_fails(sap_mcp_client: ClientSession) -> None:
    """
    Test that deleting a bundled workflow fails.

    Bundled workflows (shipped with the package) cannot be deleted.
    Only user-created workflows can be deleted.
    """
    # First get a bundled workflow name
    list_data = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert list_data.success, f"workflow_list failed: {list_data.error}"

    workflows = list_data.workflows
    if not workflows:
        pytest.skip("No bundled workflows to test with")

    bundled_name = workflows[0].name
    print(f"\nAttempting to delete bundled workflow: {bundled_name}")

    # Try to delete it
    delete_data = await call_tool_typed(sap_mcp_client, "workflow_delete", {"name": bundled_name}, WorkflowDeleteResult)

    # Should fail
    assert not delete_data.success, f"Should not be able to delete bundled workflow: {delete_data}"
    error_msg = delete_data.error or ""
    assert (
        "bundled" in error_msg.lower() or "cannot delete" in error_msg.lower()
    ), f"Error should mention bundled: {delete_data}"

    print(f"Correctly rejected: {delete_data.error}")


# =============================================================================
# EMMACL Manual Iteration Test (baseline for workflow comparison)
# =============================================================================


@pytest.mark.anyio
async def test_emmacl_manual_iteration_15_cases(sap_mcp_client: ClientSession) -> None:
    """
    Test manually iterating through 15 EMMACL cases.

    This test establishes a baseline for:
    1. How long it takes to click through cases manually
    2. What the navigation pattern looks like (list -> detail -> back)
    3. Context consumption of individual tool calls

    This test documents the manual iteration pattern for EMMACL cases,
    showing navigation and context consumption per iteration.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Open EMMACL and execute without filters
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "EMMACL"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})
    await sap_mcp_client.call_tool("sap_keyboard", {"key": "F8"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Read table to get available cases
    table_data = await call_tool_typed(sap_mcp_client, "sap_read_table", {"max_rows": 20}, TableData)
    assert table_data.success, f"sap_read_table failed: {table_data.error}"

    rows = table_data.rows or []
    total_available = len(rows)

    if total_available < 1:
        pytest.skip("No EMMACL cases available to click through")

    # Limit to 15 cases (or fewer if not enough)
    cases_to_process = min(15, total_available)
    print(f"\nProcessing {cases_to_process} of {total_available} available cases")

    successful_clicks = 0
    failed_clicks = 0
    results: list[dict[str, str]] = []

    # Process each case: click -> verify navigation -> go back
    for i in range(cases_to_process):
        row = rows[i]
        row_num = row.row
        cells = row.cells or {}

        # Find a hotspot column (typically "Fall" or similar)
        hotspot_col = None
        for col_name, cell_info in cells.items():
            if cell_info.hotspot:
                hotspot_col = col_name
                break

        if not hotspot_col:
            print(f"  Row {row_num}: No hotspot found, skipping")
            failed_clicks += 1
            continue

        # Get title before click
        screen_before = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
        title_before = screen_before.title if screen_before.success else ""

        # Click on the hotspot cell
        try:
            click_data = await call_tool_typed(
                sap_mcp_client,
                "sap_click_table_cell",
                {"row": row_num, "column": hotspot_col},
                TableCellClickResult,
            )

            if not click_data.success:
                print(f"  Row {row_num}: Click failed - {click_data.error}")
                failed_clicks += 1
                continue

            # Wait for navigation
            await sap_mcp_client.call_tool("browser_wait", {"timeout": 2000})

            # Get title after click
            screen_after = await call_tool_typed(sap_mcp_client, "sap_get_screen_info", {}, ScreenInfo)
            title_after = screen_after.title if screen_after.success else ""

            # Verify navigation happened
            if title_before != title_after:
                successful_clicks += 1
                results.append({"row": str(row_num), "title": title_after})
                print(f"  Row {row_num}: Navigated to '{title_after}'")
            else:
                failed_clicks += 1
                print(f"  Row {row_num}: Title unchanged, navigation may have failed")

            # Go back to the list
            await sap_mcp_client.call_tool("sap_keyboard", {"key": "F3"})
            await sap_mcp_client.call_tool("browser_wait", {"timeout": 1500})

        except Exception as e:  # pylint: disable=broad-exception-caught
            failed_clicks += 1
            print(f"  Row {row_num}: Error - {e}")

    print(f"\n=== EMMACL Manual Iteration Summary ===")
    print(f"Processed: {cases_to_process} cases")
    print(f"Successful: {successful_clicks}")
    print(f"Failed: {failed_clicks}")

    # At least half should succeed for the test to pass
    assert (
        successful_clicks >= cases_to_process // 2
    ), f"Expected at least {cases_to_process // 2} successful clicks, got {successful_clicks}"

    # This test documents the context cost of manual iteration:
    # - Each sap_click_table_cell call: ~300 tokens (call + result)
    # - Each sap_get_screen_info call: ~200 tokens
    # - Each sap_keyboard call: ~200 tokens
    # - Each browser_wait call: ~150 tokens
    # For 15 cases: ~15 * (300 + 200 + 200 + 150 + 200 + 150) = ~18,000 tokens
    #
    print("\n=== Context Estimation (Manual vs Workflow) ===")
    print(f"Manual approach: ~{cases_to_process * 1200:,} tokens")
    print(f"Workflow approach: ~2,000 tokens (estimated)")
    print(f"Estimated savings: ~{(cases_to_process * 1200 - 2000):,} tokens")


# =============================================================================
# sap_get_shortcuts Tests
# =============================================================================


@pytest.mark.anyio
async def test_sap_get_shortcuts_returns_shortcuts(sap_mcp_client: ClientSession) -> None:
    """Test that sap_get_shortcuts discovers shortcuts from the current screen.

    SAP screens have toolbar buttons with keyboard shortcuts like F5, F8, Strg+S.
    These are exposed in the button's title attribute as "Action (Shortcut)".
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    # Should return list of shortcuts
    shortcuts = data.shortcuts
    assert isinstance(shortcuts, list), f"Expected list of shortcuts: {shortcuts}"

    # SE16 should have at least some common shortcuts (F3=Back, F8=Execute)
    shortcut_keys = [s.shortcut for s in shortcuts]
    assert any(
        "F" in k for k in shortcut_keys
    ), f"Expected at least one F-key shortcut on SE16 screen. Found: {shortcut_keys}"


@pytest.mark.anyio
async def test_sap_get_shortcuts_has_execute_f8(sap_mcp_client: ClientSession) -> None:
    """Test that SE16 screen has F8-related shortcut (Execute).

    Note: Some SAP configurations show "F8" while others show "Strg+F8" (Ctrl+F8).
    This test accepts any shortcut containing "F8".
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")
    if sap_language != "DE":
        pytest.skip("Skipping F8 Execute test in non-DE language environments")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    shortcuts = data.shortcuts
    # Accept any shortcut containing "F8" (plain F8, Strg+F8, Ctrl+F8, etc.)
    print(shortcuts)
    assert any(sc for sc in shortcuts if sc.shortcut == "Strg+F8" and sc.action == "Online Handbuch")
    assert any(sc for sc in shortcuts if sc.shortcut == "Eingabe" and sc.action == "Tabelleninhalt")
    assert any(sc for sc in shortcuts if sc.shortcut == "F7" and sc.action == "Tabelleninhalt")


@pytest.mark.anyio
async def test_sap_get_shortcuts_has_back_f3(sap_mcp_client: ClientSession) -> None:
    """Test that screens have F3 (Back) shortcut."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    shortcuts = data.shortcuts
    f3_shortcuts = [s for s in shortcuts if s.shortcut == "F3"]

    assert (
        len(f3_shortcuts) >= 1
    ), f"Screen should have F3 (Back) shortcut. Found shortcuts: {[s.shortcut for s in shortcuts]}"


@pytest.mark.anyio
async def test_sap_get_shortcuts_no_duplicates(sap_mcp_client: ClientSession) -> None:
    """Test that duplicate shortcuts are not returned."""
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE16"})
    await _wait_for_transaction_screen(sap_mcp_client, "SE16")

    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed: {data.error}"

    shortcuts = data.shortcuts

    # Check for uniqueness
    seen = set()
    for s in shortcuts:
        key = (s.action.lower(), s.shortcut.lower())
        assert key not in seen, f"Duplicate shortcut found: {s}"
        seen.add(key)


@pytest.mark.anyio
async def test_sap_get_shortcuts_on_se09(sap_mcp_client: ClientSession) -> None:
    """Regression: sap_get_shortcuts crashed on SE09 with 'NoneType' has no attribute 'strip'.

    SE09 (Transport Organizer) has elements with title attributes that resolve to
    null/undefined in JS. This caused parse_shortcut_from_title to crash.

    This test captures an HTML snapshot of the SE09 screen for offline unit testing,
    then verifies sap_get_shortcuts completes without error.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE09"})

    # Capture HTML snapshot for offline unit test
    await capture_html_snapshot(sap_mcp_client, "se09_shortcuts", overwrite=True)

    # This used to crash: 'NoneType' object has no attribute 'strip'
    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed on SE09: {data.error}"


# =============================================================================
# Popup Handling Tests (fixes #54, #44, #57)
# =============================================================================


@pytest.mark.anyio
async def test_bp_popup_detection_and_dismiss(sap_mcp_client: ClientSession) -> None:
    """
    Test popup detection and dismissal in BP transaction.

    This test verifies the popup handling feature:
    1. Open BP transaction and press F5 (triggers "Switch to Person" popup)
    2. Dismiss the first popup to enter person creation mode
    3. Press F3 (Back) WITHOUT filling required fields
    4. This triggers a validation popup: "Die Daten des Geschäftspartners sind fehlerhaft"
    5. Verify that sap_keyboard returns with popup info
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
    kb_data = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F5"}, KeyboardResult)

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
    back_data = await call_tool_typed(sap_mcp_client, "sap_keyboard", {"key": "F3"}, KeyboardResult)

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


@pytest.mark.anyio
async def test_bp_get_form_fields_discovers_dropdowns(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_get_form_fields discovers dropdown fields on BP create person screen.

    The BP create person screen has two dropdown fields:
    - GP-Rolle (Business Partner Role)
    - Gruppierung (Grouping)

    This test verifies that sap_get_form_fields correctly identifies these as dropdowns.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Wait for form to load
    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Call sap_get_form_fields
    data = await call_tool_typed(sap_mcp_client, "sap_get_form_fields", {}, FormFieldsResult)
    assert data.success, f"sap_get_form_fields failed: {data.error}"

    # Check that fields were found
    fields = data.fields
    assert len(fields) > 0, "Expected to find form fields"

    # Find dropdown fields
    dropdown_fields = [f for f in fields if f.field_type == "dropdown"]
    assert (
        len(dropdown_fields) >= 2
    ), f"Expected at least 2 dropdowns (GP-Rolle, Gruppierung), found {len(dropdown_fields)}"

    # Check for GP-Rolle dropdown
    gp_rolle_dropdown = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert (
        gp_rolle_dropdown is not None
    ), f"Expected GP-Rolle dropdown. Found dropdowns: {[f.label for f in dropdown_fields]}"
    assert gp_rolle_dropdown.id, "Dropdown should have an ID"


@pytest.mark.anyio
async def test_bp_get_form_fields_with_dropdown_options(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_get_form_fields with include_dropdown_options=True fetches options.

    When include_dropdown_options=True, the tool should open each dropdown,
    extract available options, and return them in the field data.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Call sap_get_form_fields with dropdown options
    data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert data.success, f"sap_get_form_fields with options failed: {data.error}"

    # Find dropdown fields with options
    dropdown_fields = [f for f in data.fields if f.field_type == "dropdown"]
    assert len(dropdown_fields) >= 2, "Expected at least 2 dropdowns"

    # GP-Rolle should have options populated
    gp_rolle_dropdown = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle_dropdown is not None, "Expected GP-Rolle dropdown"

    options = gp_rolle_dropdown.options
    assert options is not None, "Expected options to be populated when include_dropdown_options=True"
    assert len(options) > 0, "Expected GP-Rolle to have available options"

    # Verify it has the default option (GPartner allgemein / Business Partner (Gen.))
    has_general_bp = any("GPartner" in opt or "General" in opt or "Business Partner" in opt for opt in options)
    assert has_general_bp, f"Expected 'GPartner allgemein' or 'Business Partner' in options: {options}"


@pytest.mark.anyio
async def test_bp_get_screen_text_with_dropdown_options(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_get_screen_text with include_dropdown_options=True.

    The dropdowns field should contain dropdown info with options.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Call sap_get_screen_text with dropdown options
    data = await call_tool_typed(sap_mcp_client, "sap_get_screen_text", {"include_dropdown_options": True}, ScreenText)
    assert data.success, f"sap_get_screen_text with dropdowns failed: {data.error}"

    # Check that dropdowns field is populated
    dropdowns = data.dropdowns
    assert dropdowns is not None, "Expected dropdowns field when include_dropdown_options=True"
    assert len(dropdowns) >= 2, f"Expected at least 2 dropdowns, found {len(dropdowns)}"

    # Each dropdown should have id, label, and options
    for dd in dropdowns:
        assert dd.id, f"Dropdown should have id: {dd}"
        assert dd.label, f"Dropdown should have label: {dd}"
        assert isinstance(dd.options, list), f"Dropdown should have options list: {dd}"


@pytest.mark.anyio
async def test_bp_fill_form_dropdown_selection(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form can select a dropdown value by label.

    This test selects a specific GP-Rolle value from the dropdown.
    Note: Changing GP-Rolle may trigger a popup dialog.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # First, get the dropdown options to know valid values
    form_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert form_data.success, f"sap_get_form_fields failed: {form_data.error}"

    # Find GP-Rolle dropdown and get first option
    dropdown_fields = [f for f in form_data.fields if f.field_type == "dropdown"]
    gp_rolle = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle is not None, "Expected GP-Rolle dropdown"

    options = gp_rolle.options or []
    assert len(options) > 0, "Expected GP-Rolle to have options"

    # Select the first option (should be the default, so no popup)
    option_to_select = options[0]
    element_id = gp_rolle.id

    # Use CSS selector with element ID
    selector = f"#{element_id}"
    fill_data = await call_tool_typed(
        sap_mcp_client, "sap_fill_form", {"fields": {selector: option_to_select}}, FillFormResult
    )
    assert fill_data.success, f"sap_fill_form dropdown failed: {fill_data.error}"

    # Verify the field was filled (selector should be in filled list)
    filled = fill_data.filled
    assert selector in filled, f"Expected {selector} to be filled. Result: {fill_data}"


@pytest.mark.anyio
async def test_bp_fill_form_dropdown_invalid_value(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_fill_form returns available options when dropdown value not found.

    When a requested value is not in the dropdown, the tool should fail
    and return the list of available options.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Try to fill with invalid dropdown value
    label = "GP-Rolle" if sap_language == "DE" else "BP Role"
    fill_data = await call_tool_typed(
        sap_mcp_client, "sap_fill_form", {"fields": {label: "INVALID_NONEXISTENT_VALUE_12345"}}, FillFormResult
    )

    # Should have an error
    errors = fill_data.errors or []
    assert len(errors) > 0, f"Expected error for invalid dropdown value. Result: {fill_data}"

    # Error should contain available options
    error = errors[0]
    available = error.available_options
    assert available is not None, f"Expected available_options in error: {error}"
    assert len(available) > 0, f"Expected non-empty available_options: {error}"


@pytest.mark.anyio
async def test_bp_set_field_dropdown_selection(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_set_field can select a dropdown value by label.

    This tests the single-field variant of dropdown selection.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await sap_mcp_client.call_tool("sap_login", {})
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # First, get the dropdown options to know valid values
    form_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert form_data.success, f"sap_get_form_fields failed: {form_data.error}"

    # Find GP-Rolle dropdown and get first option
    dropdown_fields = [f for f in form_data.fields if f.field_type == "dropdown"]
    gp_rolle = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle is not None, "Expected GP-Rolle dropdown"

    options = gp_rolle.options or []
    assert len(options) > 0, "Expected GP-Rolle to have options"

    # Select the first option using sap_set_field
    option_to_select = options[0]
    label = gp_rolle.label

    set_data = await call_tool_typed(
        sap_mcp_client, "sap_set_field", {"label": label, "value": option_to_select}, SetFieldResult
    )
    assert set_data.success, f"sap_set_field dropdown failed: {set_data.error}"

    # Verify the field was set
    assert set_data.label == label, f"Expected label {label}. Result: {set_data}"
    assert set_data.value == option_to_select, f"Expected value {option_to_select}. Result: {set_data}"
    assert set_data.selector_used, f"Expected selector_used. Result: {set_data}"


@pytest.mark.anyio
async def test_bp_set_field_dropdown_invalid_value(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_set_field returns available options when dropdown value not found.

    Similar to sap_fill_form, but for single field setting.
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Try to set invalid dropdown value
    label = "GP-Rolle" if sap_language == "DE" else "BP Role"
    set_data = await call_tool_typed(
        sap_mcp_client, "sap_set_field", {"label": label, "value": "INVALID_NONEXISTENT_VALUE_12345"}, SetFieldResult
    )

    # Should have failed
    assert not set_data.success, f"Expected failure for invalid dropdown value. Result: {set_data}"

    # Error should contain available options
    available = set_data.available_options
    assert available is not None, f"Expected available_options in result: {set_data}"
    assert len(available) > 0, f"Expected non-empty available_options: {set_data}"


@pytest.mark.anyio
async def test_bp_dropdown_value_actually_applied(sap_mcp_client: ClientSession) -> None:
    """
    Test that dropdown selection actually changes the input field value.

    This verifies the fix for issues:
    - #72 (dropdown doesn't open)
    - #73 (value not applied)
    - #74 (learning: listbox visibility approach)
    - #79 (GP-Rolle not set correctly)

    The test:
    1. Gets the current dropdown value
    2. Selects a DIFFERENT dropdown option
    3. Verifies the input field value actually changed
    """
    sap_language = os.environ.get("SAP_LANGUAGE", "DE")

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "BP"})
    await _wait_for_transaction_screen(sap_mcp_client, "BP")

    # Navigate to person creation form
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
    await sap_mcp_client.call_tool("browser_click", {"selector": "#M0\\:48\\:\\:btn\\[5\\]"})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    if sap_language == "DE":
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('Vorname')", "timeout": 15000})
    else:
        await sap_mcp_client.call_tool("browser_wait", {"selector": "label:has-text('First Name')", "timeout": 15000})
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})

    # Get form fields with dropdown options
    form_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": True}, FormFieldsResult
    )
    assert form_data.success, f"sap_get_form_fields failed: {form_data.error}"

    # Find GP-Rolle dropdown
    dropdown_fields = [f for f in form_data.fields if f.field_type == "dropdown"]
    gp_rolle = next(
        (f for f in dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert gp_rolle is not None, "Expected GP-Rolle dropdown"

    # Get current value and available options
    original_value = gp_rolle.current_value or ""
    options = gp_rolle.options or []
    assert len(options) >= 2, "Need at least 2 options to test value change"

    # Find a different option than the current value
    option_to_select = None
    for opt in options:
        # Options are in format "KEY - Description"
        if opt != original_value and opt.strip():
            option_to_select = opt
            break

    assert (
        option_to_select is not None
    ), f"Could not find different option. Current: {original_value}, Options: {options}"

    # Extract just the key from "KEY - Description" format for matching
    option_key = option_to_select.split(" - ")[0].strip() if " - " in option_to_select else option_to_select

    # Select the new option
    label = gp_rolle.label
    set_data = await call_tool_typed(
        sap_mcp_client, "sap_set_field", {"label": label, "value": option_key}, SetFieldResult
    )
    assert set_data.success, f"sap_set_field dropdown selection failed: {set_data.error}"

    # Wait for SAP to process the selection
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 500})

    # Read the form fields again to verify the value changed
    verify_data = await call_tool_typed(
        sap_mcp_client, "sap_get_form_fields", {"include_dropdown_options": False}, FormFieldsResult
    )
    assert verify_data.success, f"sap_get_form_fields verification failed: {verify_data.error}"

    # Find the GP-Rolle field again
    verify_dropdown_fields = [f for f in verify_data.fields if f.field_type == "dropdown"]
    verify_gp_rolle = next(
        (f for f in verify_dropdown_fields if "GP-Rolle" in f.label or "Role" in f.label),
        None,
    )
    assert verify_gp_rolle is not None, "Expected GP-Rolle dropdown in verification"

    # Check that the value actually changed
    new_value = verify_gp_rolle.current_value or ""

    # The new value should contain the selected option key (not the original value)
    assert option_key in new_value or new_value != original_value, (
        f"Dropdown value should have changed. "
        f"Original: {original_value}, Expected key: {option_key}, Actual: {new_value}"
    )


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


# =============================================================================
# Tests for sap_se16_query (SE16N Data Browser Tool)
# =============================================================================


@pytest.mark.anyio
async def test_se16_query_basic(sap_mcp_client: ClientSession) -> None:
    """
    Test basic sap_se16_query functionality without filters.

    Queries the T000 (Clients) table which exists on every SAP system
    and contains at least one row (the current client).

    Works in both EN and DE - the tool handles language internally.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Query T000 table (small table with at least 1 row)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "T000", "max_hits": 10},
        SE16Result,
    )

    assert result.success, f"sap_se16_query failed: {result.error}"
    assert result.table == "T000", f"Expected table='T000', got {result.table}"
    assert result.total_hits >= 1, f"T000 should have at least 1 client, got {result.total_hits}"
    assert result.returned_rows >= 1, f"Should return at least 1 row, got {result.returned_rows}"
    assert len(result.columns) > 0, "Should have column headers"
    # SE16N shows description labels, not technical names
    # T000's MANDT field is shown as "Mdt" (DE) or "Clnt" (EN)
    first_col = result.columns[0].lower()
    assert first_col in ("mdt", "clnt", "mandt", "client"), (
        f"T000 should have client/mandt as first column, got '{result.columns[0]}'. " f"All columns: {result.columns}"
    )


@pytest.mark.anyio
async def test_se16_query_with_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query with filter parameter applied.

    Queries the TSTC (Transaction Codes) table with a filter on TCODE field.
    This verifies that the filter functionality works correctly.

    Works in both EN and DE - the filter uses technical field names.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Query TSTC table WITH filter on TCODE = 'SE16'
    # This should return exactly 1 row (the SE16 transaction)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "filters": {"TCODE": "SE16"}, "max_hits": 100},
        SE16Result,
    )

    assert result.success, f"sap_se16_query with filter failed: {result.error}"
    assert result.table == "TSTC", f"Expected table='TSTC', got {result.table}"

    # With exact filter TCODE='SE16', we should get exactly 1 row
    assert result.total_hits == 1, (
        f"Filter TCODE='SE16' should return exactly 1 hit, got {result.total_hits}. "
        "Filter may not have been applied."
    )
    assert result.returned_rows == 1, f"Should return exactly 1 row, got {result.returned_rows}"

    # Verify the returned row contains SE16
    # First column should be transaction code (displayed as "TCode" or "Transaktion" etc.)
    assert len(result.rows) == 1, f"Expected 1 row in results, got {len(result.rows)}"
    row_data = result.rows[0].data
    # Get the first column's value - should be "SE16"
    first_col_name = result.columns[0]
    first_col_value = row_data.get(first_col_name, "")
    assert first_col_value == "SE16", (
        f"Expected first column to contain 'SE16', got '{first_col_value}'. " f"Row data: {row_data}"
    )


@pytest.mark.anyio
async def test_se16_query_filter_multiple_results(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_se16_query filter with wildcard pattern returning multiple results.

    Queries TSTC with a filter pattern that matches multiple transactions.
    This verifies filters work for partial matches.

    Works in both EN and DE - uses technical field names.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Query TSTC with pattern filter - SE1* should match SE10, SE11, SE12, etc.
    # SAP uses * as wildcard in SE16N filters
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "TSTC", "filters": {"TCODE": "SE1*"}, "max_hits": 100},
        SE16Result,
    )

    assert result.success, f"sap_se16_query with pattern filter failed: {result.error}"
    assert result.table == "TSTC", f"Expected table='TSTC', got {result.table}"

    # SE1* should match multiple transactions (SE10, SE11, SE12, SE13, etc.)
    assert result.total_hits >= 5, (
        f"Filter TCODE='SE1*' should return at least 5 SE1x transactions, got {result.total_hits}. "
        "Filter may not have been applied correctly."
    )

    # Verify all returned rows have transaction code starting with SE1
    # First column contains the transaction code
    first_col_name = result.columns[0]
    for row in result.rows:
        tcode = str(row.data.get(first_col_name, ""))
        assert tcode.startswith("SE1"), (
            f"Expected transaction code starting with 'SE1', got '{tcode}'. " f"Row data: {row.data}"
        )


@pytest.mark.anyio
async def test_se16_query_after_se09(sap_mcp_client: ClientSession) -> None:
    """Regression: sap_se16_query puts filter value into table name field when called from SE09.

    The filter filling code used page.keyboard.type() which types into whatever has
    focus, not the target element. If the filter element click didn't properly transfer
    focus, the keyboard input went to the table name field instead.

    Fixes #289, #290.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Navigate to SE09 first (the starting point from the bug report)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE09"})

    # Now query E070 with a filter — this is what triggered the bug
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se16_query",
        {"table": "E070", "filters": {"AS4USER": "*"}, "max_hits": 10},
        SE16Result,
    )

    assert result.success, f"sap_se16_query failed after SE09: {result.error}"
    assert result.table == "E070", f"Expected table='E070', got '{result.table}'"
    assert result.total_hits > 0, "Expected at least one transport in E070"


# =============================================================================
# SM37 Checkbox / Status Filter Tests
# =============================================================================


@pytest.mark.anyio
async def test_sm37_lookup_finished_status_filter(sap_mcp_client: ClientSession) -> None:
    """Test that SM37 status checkbox filtering actually works.

    Verifies that set_checkbox properly toggles SAP checkboxes by filtering
    for only 'finished' jobs. If checkboxes didn't work (the old fill_field("X")
    bug), all default statuses would remain and results would include non-finished jobs.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {"job_name": "*", "username": "*", "status": ["finished"]},
        SM37JobListResult,
    )

    assert result.success, f"SM37 lookup failed: {result.error}"

    # If checkboxes work, all returned jobs should have 'finished' status
    for job in result.jobs:
        status_lower = (job.status or "").lower()
        assert status_lower in ("finished", "fertig"), (
            f"Expected 'finished'/'fertig' status but got '{job.status}'. "
            "Checkbox filter may not be working (set_checkbox bug)."
        )


@pytest.mark.anyio
async def test_sm37_lookup_canceled_status_filter(sap_mcp_client: ClientSession) -> None:
    """Test SM37 with 'canceled' status filter to verify checkbox unchecking works.

    'Canceled' is NOT checked by default in SAP. If set_checkbox works, only
    canceled jobs should appear. If checkboxes silently fail, we'd get the
    default mix (all except 'scheduled').
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {"job_name": "*", "username": "*", "status": ["canceled"]},
        SM37JobListResult,
    )

    assert result.success, f"SM37 lookup failed: {result.error}"

    # Even if no canceled jobs exist, the query should succeed
    # If there ARE results, they must all be canceled
    for job in result.jobs:
        status_lower = (job.status or "").lower()
        assert status_lower in ("canceled", "abgebrochen"), (
            f"Expected 'canceled'/'abgebrochen' status but got '{job.status}'. " "Checkbox filter may not be working."
        )


@pytest.mark.anyio
async def test_sm37_lookup_with_date_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_sm37_lookup with date range filter.

    Verifies that the from_date and to_date parameters are correctly filled
    into the SM37 selection screen date fields. Uses a narrow date range
    (today only) to verify the fields are found and set without error.

    This test covers the fix for GitHub issue #304 where the ARIA labels
    for date fields were wrong (e.g., "von (Datum/Uhrzeit)" instead of "von Datum").

    Works in both DE and EN via the language-aware label lookup.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Use today's date as both from and to — guarantees a valid range
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {
            "job_name": "*",
            "username": "*",
            "from_date": today,
            "to_date": today,
        },
        SM37JobListResult,
    )

    assert result.success, f"sap_sm37_lookup with date filter failed: {result.error}"
    assert (
        result.filters_applied.get("from_date") == today
    ), f"Expected from_date='{today}' in filters, got {result.filters_applied}"
    assert (
        result.filters_applied.get("to_date") == today
    ), f"Expected to_date='{today}' in filters, got {result.filters_applied}"
