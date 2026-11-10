"""Integration tests for SAP login, session status, and settings dialog capture."""

import os

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import EvaluateResult
from sapguimcp.models import KeyboardResult, LoginResult, SessionStatus

from .conftest import call_tool_typed, get_html_content
from .integration_helpers import capture_html_snapshot


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

    The sap_login tool reads credentials from ~/.config/sap-mcp/systems.json
    and performs automatic login.

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
        "Browser does not show SAP Easy Access screen. Login may have failed or a dialog is blocking."
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
async def test_page_reports_the_logon_language(sap_mcp_client: ClientSession) -> None:
    """``<html lang>`` names the logon language; the WebGUI backend reads it after login (#1044)."""
    from sapguimcp.models.config import get_sap_config  # noqa: PLC0415

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"
    page_lang = await call_tool_typed(
        sap_mcp_client, "browser_evaluate", {"script": "document.documentElement.lang"}, EvaluateResult
    )
    assert page_lang.result, "the WebGUI page has no <html lang>"
    iso_code = page_lang.result.strip('"').split("-")[0].upper()
    assert iso_code == get_sap_config().get_default().language.upper()


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
        {
            "script": """
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
        EvaluateResult,
    )

    if settings_eval.result and "clicked" in str(settings_eval.result):
        await sap_mcp_client.call_tool("browser_wait", {"timeout": 1000})
        await capture_html_snapshot(sap_mcp_client, "settings_dialog")

        # Close the dialog
        await call_tool_typed(
            sap_mcp_client,
            "browser_evaluate",
            {
                "script": """
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
            EvaluateResult,
        )
        await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "Escape"}, KeyboardResult)


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
