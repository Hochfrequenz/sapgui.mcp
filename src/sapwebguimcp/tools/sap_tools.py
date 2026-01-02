# pylint: disable=too-many-lines
"""
SAP-specific MCP tools for SAP Web GUI automation.

This module contains tools for:
- sap_login: Log into SAP Web GUI
- sap_transaction: Enter and execute SAP transaction codes
- sap_keepalive_start/stop: Keep SAP session alive
- sap_session_status: Check SAP session status
- sap_keyboard: Send keyboard shortcuts (F-keys, Ctrl+S, etc.)
- sap_get_screen_text: Get all readable text from current screen
- sap_read_table: Read data from ALV grids and tables
- sap_read_status_bar: Read status bar messages
- sap_get_screen_info: Get technical screen information
- sap_lookup_fields: Look up known field selectors for a transaction
- sap_discover_fields: Discover input fields on current screen
"""

import asyncio
import json
import logging
from importlib import resources
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from sapwebguimcp.models import BrowserManager, get_settings

__all__ = ["register_sap_tools"]

logger = logging.getLogger(__name__)

# =============================================================================
# Keepalive Management
# =============================================================================

_keepalive_task: Optional[asyncio.Task[None]] = None
_keepalive_interval: int = 300  # 5 minutes default


async def _keepalive_loop(browser_manager: BrowserManager, interval: int) -> None:
    """
    Background task that periodically performs a harmless action to keep SAP session alive.

    Args:
        browser_manager: The browser manager instance
        interval: Seconds between keepalive actions
    """
    logger.info("Keepalive task started with interval %d seconds", interval)

    while True:
        try:
            await asyncio.sleep(interval)

            page = await browser_manager.get_current_page()

            if page.is_closed():
                logger.warning("Keepalive: Page is closed, stopping keepalive")
                break

            # Perform a harmless action - evaluate JS to keep connection alive
            await page.evaluate("() => { /* keepalive ping */ }")

            logger.debug("Keepalive ping sent")

        except asyncio.CancelledError:
            logger.info("Keepalive task cancelled")
            break
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Keepalive error (will retry): %s", e)


# =============================================================================
# SAP Selectors and Helpers
# =============================================================================

# Common selectors for SAP Web GUI elements
SELECTORS: dict[str, str] = {
    "okcode_field": (
        'input[id*="ToolbarOkCode"], ' 'input[name*="okcode" i], ' 'input[id*="okcd" i], ' 'input[id*="OkCodeField" i]'
    ),
    "settings_button": (
        '[id*="settingsButton"], '
        '[title*="Setting" i], '
        '[title*="Einstellung" i], '
        'button[id*="gear" i], '
        '[aria-label*="Setting" i]'
    ),
    "menu_expand": ('[id*="shellMnuExp"], ' '[title*="Menu" i], ' '[title*="Menü" i], ' '[aria-label*="Menu" i]'),
    "okcode_checkbox": ('input[type="checkbox"][id*="okCode" i], ' 'input[type="checkbox"][name*="okCode" i]'),
    "okcode_label": (
        'label:has-text("OK-Code"), '
        'label:has-text("OKCode"), '
        'label:has-text("Transaction"), '
        'span:has-text("OK-Code")'
    ),
    "save_settings": (
        'button:has-text("Save"), '
        'button:has-text("Speichern"), '
        'button:has-text("OK"), '
        'button:has-text("Apply"), '
        'input[type="submit"]'
    ),
    "close_dialog": (
        'button:has-text("Close"), '
        'button:has-text("Schließen"), '
        'button[aria-label*="Close" i], '
        '[id*="closeButton"]'
    ),
}


async def _find_okcode_field(page: Any) -> Optional[Any]:
    """Try to find the OK-Code/transaction input field."""
    return await page.query_selector(SELECTORS["okcode_field"])


async def _try_find_checkbox_by_label(page: Any) -> Optional[Any]:
    """Try to find OK-Code checkbox by its label."""
    okcode_label = await page.query_selector(SELECTORS["okcode_label"])
    if not okcode_label:
        return None

    for_id = await okcode_label.get_attribute("for")
    if for_id:
        return await page.query_selector(f"#{for_id}")

    parent = await okcode_label.evaluate_handle("el => el.parentElement")
    if parent:
        return await parent.query_selector('input[type="checkbox"]')
    return None


async def _try_find_checkbox_in_tabs(page: Any, steps_taken: list[str]) -> Optional[Any]:
    """Try to find OK-Code checkbox by searching through settings tabs."""
    settings_tabs = await page.query_selector_all('[role="tab"], .sapMTabStrip button, [class*="tab" i] button')
    for tab in settings_tabs:
        tab_text = await tab.text_content()
        if tab_text and any(
            keyword in tab_text.lower()
            for keyword in ["display", "anzeige", "layout", "toolbar", "general", "allgemein"]
        ):
            await tab.click()
            await page.wait_for_timeout(500)
            okcode_checkbox = await page.query_selector(SELECTORS["okcode_checkbox"])
            if okcode_checkbox:
                steps_taken.append(f"Found OK-Code setting in tab: {tab_text}")
                return okcode_checkbox
    return None


async def _close_settings_dialog(page: Any) -> None:
    """Close the settings dialog if open."""
    close_btn = await page.query_selector(SELECTORS["close_dialog"])
    if close_btn:
        await close_btn.click()
        await page.wait_for_timeout(500)


async def _enable_okcode_field(page: Any) -> tuple[bool, str]:
    """
    Enable the OK-Code field through SAP Web GUI settings.

    Returns:
        Tuple of (success: bool, message: str)
    """
    steps_taken: list[str] = []

    try:
        # Step 1: Try to expand menu if there's an expand button
        menu_expand = await page.query_selector(SELECTORS["menu_expand"])
        if menu_expand:
            await menu_expand.click()
            await page.wait_for_timeout(500)
            steps_taken.append("Expanded menu")

        # Step 2: Find and click settings/gear button
        settings_btn = await page.query_selector(SELECTORS["settings_button"])
        if not settings_btn:
            settings_btn = await page.query_selector(
                '[role="menu"] [title*="Setting" i], '
                '[role="menu"] [title*="Einstellung" i], '
                '[class*="menu"] [title*="Setting" i]'
            )

        if not settings_btn:
            return False, "Could not find settings/gear button. Please enable OK-Code field manually."

        await settings_btn.click()
        await page.wait_for_timeout(1000)
        steps_taken.append("Opened settings")

        # Step 3: Look for OK-Code checkbox or setting
        okcode_checkbox = await page.query_selector(SELECTORS["okcode_checkbox"])

        if not okcode_checkbox:
            okcode_checkbox = await _try_find_checkbox_by_label(page)

        if not okcode_checkbox:
            okcode_checkbox = await _try_find_checkbox_in_tabs(page, steps_taken)

        if not okcode_checkbox:
            await _close_settings_dialog(page)
            return False, f"Could not find OK-Code checkbox in settings. Steps taken: {', '.join(steps_taken)}"

        # Step 4: Check if already enabled
        is_checked = await okcode_checkbox.is_checked()
        if is_checked:
            steps_taken.append("OK-Code field already enabled")
            await _close_settings_dialog(page)
            return True, f"OK-Code field was already enabled. Steps: {', '.join(steps_taken)}"

        # Step 5: Enable the checkbox
        await okcode_checkbox.click()
        await page.wait_for_timeout(300)
        steps_taken.append("Enabled OK-Code checkbox")

        # Step 6: Save settings
        save_btn = await page.query_selector(SELECTORS["save_settings"])
        if save_btn:
            await save_btn.click()
            await page.wait_for_timeout(1000)
            steps_taken.append("Saved settings")
        else:
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)
            steps_taken.append("Pressed Enter to confirm")

        # Close any remaining dialog
        await _close_settings_dialog(page)

        return True, f"OK-Code field enabled. Steps: {', '.join(steps_taken)}"

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error enabling OK-Code field")
        return False, f"Error enabling OK-Code field: {e}. Steps taken: {', '.join(steps_taken)}"


# =============================================================================
# Tool Registration
# =============================================================================


def register_sap_tools(mcp: FastMCP) -> None:  # pylint: disable=too-many-statements
    """Register all SAP-specific tools with the MCP server."""

    @mcp.tool(description="Start a background task that keeps the SAP session alive")
    async def sap_keepalive_start(interval_seconds: int = 300) -> str:
        """
        Start a background task that keeps the SAP session alive.

        This prevents SAP from logging you out due to inactivity.
        The task runs in the background and periodically pings the browser
        to maintain the session.

        Args:
            interval_seconds: Seconds between keepalive pings (default: 300 = 5 minutes)

        Returns:
            Status message confirming keepalive is running.
        """
        global _keepalive_task, _keepalive_interval  # pylint: disable=global-statement

        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        # Stop existing task if running
        if _keepalive_task is not None and not _keepalive_task.done():
            _keepalive_task.cancel()
            try:
                await _keepalive_task
            except asyncio.CancelledError:
                pass

        _keepalive_interval = interval_seconds
        _keepalive_task = asyncio.create_task(_keepalive_loop(browser_manager, interval_seconds))

        return (
            f"Keepalive started. Will ping every {interval_seconds} seconds "
            f"({interval_seconds // 60} minutes) to prevent session timeout."
        )

    @mcp.tool(description="Stop the background keepalive task")
    async def sap_keepalive_stop() -> str:
        """
        Stop the background keepalive task.

        Call this when you're done with SAP or want to allow the session to timeout naturally.

        Returns:
            Status message confirming keepalive is stopped.
        """
        global _keepalive_task  # pylint: disable=global-statement

        if _keepalive_task is None or _keepalive_task.done():
            return "Keepalive was not running."

        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass

        _keepalive_task = None
        return "Keepalive stopped."

    @mcp.tool(description="Log into SAP Web GUI")
    async def sap_login(  # pylint: disable=too-many-return-statements
        url: Optional[str] = None,
    ) -> str:
        """
        Log into SAP Web GUI.

        Opens the SAP Web GUI URL and automatically logs in using credentials
        from environment variables (SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE).

        If credentials are not configured, opens the login page for manual entry.

        Args:
            url: SAP Web GUI URL. If not provided, uses SAP_URL from environment.

        Returns:
            Status message indicating login success or what action is needed.
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager
        settings = get_settings()

        page = await browser_manager.get_current_page()
        effective_url = url or settings.sap_url

        if not effective_url:
            return "No SAP URL provided. Either pass a URL parameter or set the SAP_URL environment variable."

        try:
            logger.info("Navigating to SAP Web GUI: %s", effective_url)
            await page.goto(effective_url)
            await page.wait_for_load_state("networkidle")

            # Check if we're already logged in
            okcode_field = await _find_okcode_field(page)
            if okcode_field:
                return (
                    f"Already logged in to SAP at {effective_url}. "
                    "OK-Code field is available. Ready to run transactions."
                )

            # Check for login form
            login_form = await page.query_selector('input[type="password"], input[id*="user" i]')
            if not login_form:
                return f"Navigated to {effective_url}. No login form detected - please check browser window."

            # Check if we have credentials for auto-login
            if not all([settings.sap_user, settings.sap_password, settings.sap_mandant]):
                return (
                    f"SAP login page opened at {effective_url}. "
                    "Credentials not configured (SAP_USER, SAP_PASSWORD, SAP_MANDANT). "
                    "Please enter credentials manually in the browser window."
                )

            # Perform automatic login
            logger.info("Performing automatic login for user: %s", settings.sap_user)

            # Fill mandant/client
            await page.fill('#sap-client, input[name="sap-client"]', settings.sap_mandant)

            # Fill username
            await page.fill('#sap-user, input[name="sap-user"]', settings.sap_user)

            # Fill password
            await page.fill('#sap-password, input[name="sap-password"]', settings.sap_password)

            # Set language - SAP login has a hidden #sap-language input and visible dropdown
            # We need to set the hidden input value via JavaScript since fill() won't work
            try:
                await page.evaluate(
                    f"""
                    (function() {{
                        // Set hidden language input
                        var hiddenField = document.querySelector('#sap-language, input[name="sap-language"]');
                        if (hiddenField) {{
                            hiddenField.value = "{settings.sap_language}";
                            hiddenField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            hiddenField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                        // Also try to update the visible dropdown display if it exists
                        var dropdown = document.querySelector('#sap-language-dropdown');
                        if (dropdown) {{
                            var lang = "{settings.sap_language}";
                            var langDisplay = lang === "EN" ? "English" :
                                              lang === "DE" ? "Deutsch" : lang;
                            dropdown.value = langDisplay;
                        }}
                    }})()
                    """
                )
                logger.debug("Set language field to: %s", settings.sap_language)
            except Exception as lang_err:  # pylint: disable=broad-exception-caught
                logger.warning("Could not set language field: %s", lang_err)

            # Click login button (it's a div with role="button", not a button element)
            await page.click("#LOGON_BUTTON")

            # Wait for SAP Easy Access to load (OK-Code field appears after login)
            try:
                await page.wait_for_selector("#ToolbarOkCode", timeout=15000, state="visible")
                logger.info("Login successful - OK-Code field visible")
                return f"Successfully logged into SAP as {settings.sap_user}. Ready to run transactions."
            except Exception:  # pylint: disable=broad-exception-caught
                # Login might have failed or there's a dialog
                page_content = await page.content()

                # Check for "user already logged in" dialog
                if "already logged" in page_content.lower() or "bereits angemeldet" in page_content.lower():
                    # Try to click Continue/Weiter button
                    try:
                        continue_btn_selector = (
                            'button:has-text("Continue"), '
                            'button:has-text("Weiter"), '
                            'button:has-text("Fortfahren")'
                        )
                        await page.click(continue_btn_selector, timeout=5000)
                        await page.wait_for_selector("#ToolbarOkCode", timeout=10000, state="visible")
                        return (
                            f"Successfully logged into SAP as {settings.sap_user} "
                            "(continued existing session). Ready to run transactions."
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

                return (
                    "Login attempted but SAP Easy Access not detected. "
                    "Please check browser window for errors or dialogs."
                )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error during SAP login")
            return f"Error during SAP login: {e}"

    @mcp.tool(description="Enter and execute an SAP transaction code")
    async def sap_transaction(tcode: str, new_window: bool = False) -> str:
        """
        Enter and execute an SAP transaction code.

        This tool will:
        1. Check if the OK-Code field is visible
        2. If not, attempt to enable it via Settings (gear icon → enable OK-Code field)
        3. Enter the transaction code and execute it

        Transaction modes:
        - new_window=False (default): Opens transaction in current window, canceling any
          active transaction. Uses /n prefix (e.g., /nSE11).
        - new_window=True: Opens transaction in a NEW SAP session/window, preserving the
          current transaction. Uses /o prefix (e.g., /oSE11). This creates an additional
          SAP session.

        Args:
            tcode: Transaction code (e.g., VA01, MM03, SE80, SU01)
            new_window: If True, open in new SAP session window (preserves current transaction)

        Returns:
            Status message indicating success or describing any issues.
            Includes session count when opening new windows.
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        page = await browser_manager.get_current_page()

        try:
            # Step 1: Check if OK-Code field exists
            okcode_field = await _find_okcode_field(page)

            if not okcode_field:
                logger.info("OK-Code field not found, attempting to enable it")

                # Step 2: Try to enable the OK-Code field
                success, message = await _enable_okcode_field(page)
                logger.info("Enable OK-Code result: %s - %s", success, message)

                if not success:
                    return (
                        f"Could not find or enable OK-Code field. {message} "
                        "Possible causes: (1) A popup/dialog may be blocking the screen - "
                        "close any open dialogs first. (2) The OK-Code field may need to be "
                        "enabled manually: Menu → Settings → Enable 'OK-Code Field' or "
                        "'Transaction Field'."
                    )

                await page.wait_for_timeout(500)

                okcode_field = await _find_okcode_field(page)
                if not okcode_field:
                    return (
                        f"OK-Code field still not visible after enabling. {message} "
                        "Possible causes: (1) A popup/dialog may be blocking the screen - "
                        "close any open dialogs first. (2) Please try enabling it manually "
                        "in SAP settings."
                    )

            # Step 3: Enter the transaction code
            # SAP transaction code prefixes:
            # - /n = open in current window (cancels current transaction)
            # - /o = open in new window (creates new SAP session)
            #
            # Examples:
            # - "SU3" with new_window=False → "/nSU3"
            # - "SU3" with new_window=True → "/oSU3"
            # - "/IWFND/GW_CLIENT" with new_window=False → "/n/IWFND/GW_CLIENT"
            # - "/IWFND/GW_CLIENT" with new_window=True → "/o/IWFND/GW_CLIENT"
            prefix = "/o" if new_window else "/n"

            # Handle codes that already have a prefix
            if tcode.startswith("/n") or tcode.startswith("/o"):
                # Respect user's explicit prefix choice
                transaction_input = tcode
            else:
                transaction_input = f"{prefix}{tcode}"

            # Ensure page is in front and active
            await page.bring_to_front()
            await page.wait_for_timeout(500)

            # ============================================================================
            # SAP Web GUI OK-Code Field Automation - Important Findings
            # ============================================================================
            #
            # The OK-Code field (id="ToolbarOkCode") in SAP Web GUI is NOT a standard HTML
            # input. It has custom SAP event handlers defined in the "lsevents" attribute.
            #
            # What DOES NOT work:
            # - Playwright's fill() method - sets value but SAP doesn't recognize it
            # - Playwright's type() method - characters don't appear in the field
            # - page.keyboard.type() - keystrokes don't reach the SAP field
            # - Direct click + keyboard input - same issue, SAP intercepts events
            #
            # What DOES work:
            # - JavaScript: Set field.value directly, then dispatch Enter keyboard events
            # - The Enter event triggers SAP's lsevents handler which processes the value
            # - The text may not visually appear in the field, but the transaction executes
            #
            # ============================================================================

            logger.info("Attempting to enter transaction code: %s", transaction_input)

            # Use JavaScript to set value, then Playwright to press Enter
            # IMPORTANT: We must click on the OK-Code field first to ensure it has focus.
            await okcode_field.click()
            await page.wait_for_timeout(200)
            logger.info("Clicked OK-Code field to ensure focus")

            await page.evaluate(
                f"""
                (function() {{
                    var field = document.getElementById('ToolbarOkCode');
                    if (field) {{
                        // Focus the field first
                        field.focus();

                        // Set the value directly
                        field.value = '{transaction_input}';

                        // Trigger input/change events so SAP knows the value changed
                        field.dispatchEvent(new Event('input', {{ bubbles: true, cancelable: true }}));
                        field.dispatchEvent(new Event('change', {{ bubbles: true, cancelable: true }}));
                    }}
                }})()
                """
            )

            await page.wait_for_timeout(300)
            logger.info("Set transaction code via JavaScript: %s", transaction_input)

            # Now use Playwright's keyboard to press Enter - this triggers SAP's navigation
            await page.keyboard.press("Enter")
            logger.info("Pressed Enter to execute transaction")

            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(500)

            title = await page.title()

            # Build response message
            if new_window:
                # When opening in new window, count browser pages/tabs
                # SAP opens new sessions in new browser windows/tabs
                context = page.context
                pages = context.pages
                session_count = len(pages)
                return (
                    f"Transaction {tcode} opened in NEW session window. "
                    f"Current page: {title}. "
                    f"SAP sessions open: {session_count}. "
                    "The new transaction window should now be active."
                )

            return (
                f"Transaction {tcode} executed in current window. "
                f"Current page: {title}. "
                "Any previous transaction was cancelled."
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error executing transaction")
            return f"Error executing transaction {tcode}: {e}"

    @mcp.tool(description="Check the current SAP session status")
    async def sap_session_status() -> str:
        """
        Check the current SAP session status.

        Useful to verify the session is still active before performing actions,
        especially after long pauses or agent questions.

        Returns:
            Status message containing one of:
            - "active": Session is alive and responsive
            - "timed_out": Session has timed out
            - "logged_off": User has been logged off
            - "no_page": No browser page available
            - "unknown": Cannot determine status
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            if page.is_closed():
                return "Status: no_page - Browser page is closed."

            # Check for OK-Code field (indicates active SAP session)
            okcode_field = await _find_okcode_field(page)
            if okcode_field:
                return "Status: active - SAP session is alive and responsive."

            # Check for login form (indicates logged off)
            login_form = await page.query_selector('input[type="password"], input[id*="sap-user" i], #sap-user')
            if login_form:
                return "Status: logged_off - Login page detected. Please use sap_login to log in again."

            # Check for timeout message
            page_content = await page.content()
            timeout_indicators = [
                "session timeout",
                "sitzung abgelaufen",
                "session expired",
                "zeitüberschreitung",
                "logged off",
                "abgemeldet",
            ]
            if any(indicator in page_content.lower() for indicator in timeout_indicators):
                return "Status: timed_out - Session has timed out. Please use sap_login to reconnect."

            return "Status: unknown - Cannot determine session status. Please check browser window."

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error checking session status")
            return f"Status: unknown - Error checking status: {e}"

    @mcp.tool(description="Send a keyboard shortcut to SAP Web GUI")
    async def sap_keyboard(key: str) -> str:
        """
        Send a keyboard shortcut to SAP Web GUI.

        Common SAP shortcuts:
        - "F3" - Back (Zurück)
        - "F4" - Search Help (F4-Hilfe)
        - "F5" - Refresh / Create Person (context dependent)
        - "F6" - Create Organization (in BP)
        - "F8" - Execute (Ausführen)
        - "Ctrl+S" - Save (Sichern)
        - "Ctrl+Y" - Select text mode (Markieren)
        - "Shift+F3" - Exit (Beenden)
        - "Enter" - Confirm
        - "Escape" - Cancel dialog

        Args:
            key: Keyboard shortcut. Use "Ctrl+", "Shift+", "Alt+" prefixes for modifiers.

        Returns:
            Confirmation message or error description.
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            # Ensure page is in front
            await page.bring_to_front()
            await page.wait_for_timeout(100)

            # Send the keystroke
            await page.keyboard.press(key)

            # Wait for SAP to respond
            await page.wait_for_timeout(500)
            await page.wait_for_load_state("networkidle")

            title = await page.title()
            return f"Sent keyboard shortcut: {key}. Current page: {title}"

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error sending keyboard shortcut")
            return f"Error sending keyboard shortcut {key}: {e}"

    @mcp.tool(description="Get all readable text from the current SAP screen")
    async def sap_get_screen_text() -> str:
        """
        Get all readable text from the current SAP screen.

        This tool extracts text content for adaptive field discovery.
        Use it to identify field labels, button texts, and screen content
        when you need to work with screens that vary by system configuration.

        Returns:
            Structured text content including:
            - Screen title
            - Field labels and values
            - Button labels
            - Tab labels
            - Status messages
            - Table headers
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            # Extract text using JavaScript for comprehensive coverage
            screen_text = await page.evaluate(
                """
                () => {
                    const result = {
                        title: document.title,
                        statusBar: '',
                        mainContent: [],
                        labels: [],
                        buttons: [],
                        tabs: [],
                        tableHeaders: []
                    };

                    // Get status bar message
                    const statusBar = document.querySelector(
                        '.urMsgBarTxt, .sapMSGtext, [class*="message" i], [id*="StatusBar" i]'
                    );
                    if (statusBar) {
                        result.statusBar = statusBar.textContent.trim();
                    }

                    // Get all labels (for adaptive field discovery)
                    document.querySelectorAll('label, .urLbl, [class*="label" i]').forEach(el => {
                        const text = el.textContent.trim();
                        if (text && text.length < 100) {
                            result.labels.push(text);
                        }
                    });

                    // Get all buttons
                    document.querySelectorAll(
                        'button, [role="button"], input[type="button"], input[type="submit"]'
                    ).forEach(el => {
                        const text = el.textContent.trim() || el.value || el.getAttribute('title') || '';
                        if (text && text.length < 50) {
                            result.buttons.push(text);
                        }
                    });

                    // Get tab labels
                    document.querySelectorAll('[role="tab"], .sapMTabStrip button').forEach(el => {
                        const text = el.textContent.trim();
                        if (text) {
                            result.tabs.push(text);
                        }
                    });

                    // Get table headers
                    document.querySelectorAll('th, [role="columnheader"]').forEach(el => {
                        const text = el.textContent.trim();
                        if (text) {
                            result.tableHeaders.push(text);
                        }
                    });

                    // Get main content text (limited to avoid too much noise)
                    const mainArea = document.querySelector(
                        '#content, #MAIN_CONTENT, [role="main"], .sapMPage, body'
                    );
                    if (mainArea) {
                        // Get visible text, excluding scripts and styles
                        const walker = document.createTreeWalker(
                            mainArea,
                            NodeFilter.SHOW_TEXT,
                            {
                                acceptNode: function(node) {
                                    const parent = node.parentElement;
                                    if (!parent) return NodeFilter.FILTER_REJECT;
                                    const tag = parent.tagName.toLowerCase();
                                    if (tag === 'script' || tag === 'style' || tag === 'noscript') {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    const text = node.textContent.trim();
                                    if (text.length > 0 && text.length < 200) {
                                        return NodeFilter.FILTER_ACCEPT;
                                    }
                                    return NodeFilter.FILTER_REJECT;
                                }
                            }
                        );
                        let count = 0;
                        while (walker.nextNode() && count < 200) {
                            const text = walker.currentNode.textContent.trim();
                            if (text && !result.mainContent.includes(text)) {
                                result.mainContent.push(text);
                                count++;
                            }
                        }
                    }

                    return result;
                }
                """
            )

            # Format output
            output_parts = []
            output_parts.append(f"=== Screen: {screen_text['title']} ===")

            if screen_text["statusBar"]:
                output_parts.append(f"\nStatus Bar: {screen_text['statusBar']}")

            if screen_text["tabs"]:
                output_parts.append("\nTabs: " + ", ".join(screen_text["tabs"]))

            if screen_text["labels"]:
                # Deduplicate and limit
                unique_labels = list(dict.fromkeys(screen_text["labels"]))[:50]
                output_parts.append("\nLabels/Fields:\n  " + "\n  ".join(unique_labels))

            if screen_text["buttons"]:
                unique_buttons = list(dict.fromkeys(screen_text["buttons"]))[:20]
                output_parts.append("\nButtons: " + ", ".join(unique_buttons))

            if screen_text["tableHeaders"]:
                unique_headers = list(dict.fromkeys(screen_text["tableHeaders"]))[:20]
                output_parts.append("\nTable Headers: " + ", ".join(unique_headers))

            if screen_text["mainContent"]:
                # Show first 30 content items
                content_sample = screen_text["mainContent"][:30]
                output_parts.append("\nContent:\n  " + "\n  ".join(content_sample))

            return "\n".join(output_parts)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting screen text")
            return f"Error getting screen text: {e}"

    @mcp.tool(description="Read data from an ALV grid or table on the current screen")
    async def sap_read_table(start_row: int = 1, end_row: Optional[int] = None, max_rows: int = 100) -> str:
        """
        Read rows from an ALV grid or table on the current screen.

        Works with SAP ALV grids, step loops, and list displays.

        Args:
            start_row: First row to read (1-indexed, default: 1)
            end_row: Last row to read (None = up to max_rows visible rows)
            max_rows: Maximum rows to return (default: 100, prevents huge responses)

        Returns:
            JSON-formatted table data with column headers and row values.
            Empty columns are excluded to reduce response size.
            Returns error message if no table found.
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            # Extract table data using JavaScript
            table_data = await page.evaluate(
                """
                (params) => {
                    const { startRow, endRow, maxRows } = params;

                    // Find table elements (various SAP table implementations)
                    const tableSelectors = [
                        'table[role="grid"]',           // ALV Grid
                        '.sapMList table',              // SAPUI5 List
                        'table.urTbl',                  // Classic SAP table
                        '[role="treegrid"]',            // Tree grid
                        'table',                        // Fallback to any table
                    ];

                    let table = null;
                    for (const selector of tableSelectors) {
                        table = document.querySelector(selector);
                        if (table) break;
                    }

                    if (!table) {
                        return { error: 'No table found on current screen' };
                    }

                    // Get headers
                    const headers = [];
                    const headerCells = table.querySelectorAll('th, [role="columnheader"]');
                    headerCells.forEach(cell => {
                        // Limit header text length and clean whitespace
                        let text = cell.textContent.trim().substring(0, 50);
                        headers.push(text);
                    });

                    // If no headers found in th, try first row
                    if (headers.length === 0) {
                        const firstRow = table.querySelector('tr');
                        if (firstRow) {
                            firstRow.querySelectorAll('td').forEach(cell => {
                                let text = cell.textContent.trim().substring(0, 50);
                                headers.push(text);
                            });
                        }
                    }

                    // Get rows with limits
                    const rows = [];
                    const dataRows = table.querySelectorAll('tbody tr, tr[role="row"]');
                    const maxEnd = startRow + maxRows - 1;
                    const actualEndRow = endRow ? Math.min(endRow, maxEnd) : Math.min(dataRows.length, maxEnd);

                    // Track which columns have data (to filter out empty columns)
                    const columnsWithData = new Set();

                    for (let i = startRow - 1; i < Math.min(actualEndRow, dataRows.length); i++) {
                        const row = dataRows[i];
                        if (!row) continue;

                        const cells = row.querySelectorAll('td, [role="gridcell"]');
                        const rowData = {};

                        cells.forEach((cell, idx) => {
                            // Limit cell text to 200 chars to prevent huge values
                            let cellText = cell.textContent.trim().substring(0, 200);
                            if (cellText) {
                                const headerName = headers[idx] || `col_${idx + 1}`;
                                rowData[headerName] = cellText;
                                columnsWithData.add(headerName);
                            }
                        });

                        if (Object.keys(rowData).length > 0) {
                            rows.push({ row: i + 1, data: rowData });
                        }
                    }

                    // Filter headers to only include columns that have data
                    const usedHeaders = headers.filter((h, idx) =>
                        columnsWithData.has(h) || columnsWithData.has(`col_${idx + 1}`)
                    );

                    return {
                        headers: usedHeaders,
                        totalRows: dataRows.length,
                        returnedRows: rows.length,
                        truncated: dataRows.length > actualEndRow,
                        rows: rows
                    };
                }
                """,
                {"startRow": start_row, "endRow": end_row, "maxRows": max_rows},
            )

            if "error" in table_data:
                return str(table_data["error"])

            return json.dumps(table_data, indent=2, ensure_ascii=False)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error reading table")
            return f"Error reading table: {e}"

    @mcp.tool(description="Read the current message from SAP's status bar")
    async def sap_read_status_bar() -> str:
        """
        Read the current message from SAP's status bar.

        SAP displays success, error, warning, and info messages in the status bar.
        This tool extracts that message for programmatic checking.

        Returns:
            JSON with:
            - type: "S" (success), "E" (error), "W" (warning), "I" (info), or "none"
            - message: The status bar text
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            # Extract status bar content using JavaScript
            status_info = await page.evaluate(
                """
                () => {
                    // Various SAP Web GUI status bar selectors
                    const statusSelectors = [
                        '#LSMSG_AREA',                  // Classic status area
                        '.urMsgBarTxt',                 // SAP message bar
                        '.sapMSGtext',                  // SAPUI5 message
                        '[id*="StatusBar" i]',          // Status bar variations
                        '[class*="msgbar" i]',          // Message bar variations
                        '[id*="msgarea" i]',            // Message area
                    ];

                    let statusElement = null;
                    for (const selector of statusSelectors) {
                        statusElement = document.querySelector(selector);
                        if (statusElement && statusElement.textContent.trim()) {
                            break;
                        }
                    }

                    if (!statusElement || !statusElement.textContent.trim()) {
                        return { type: 'none', message: '' };
                    }

                    const message = statusElement.textContent.trim();

                    // Determine message type based on CSS classes or icons
                    let type = 'I';  // Default to info

                    const parentClasses = (statusElement.className + ' ' +
                        (statusElement.parentElement?.className || '')).toLowerCase();

                    // Check for error indicators
                    if (parentClasses.includes('error') ||
                        parentClasses.includes('fehler') ||
                        statusElement.querySelector('[class*="error" i], .sapMsgError')) {
                        type = 'E';
                    }
                    // Check for warning indicators
                    else if (parentClasses.includes('warning') ||
                             parentClasses.includes('warnung') ||
                             statusElement.querySelector('[class*="warning" i], .sapMsgWarning')) {
                        type = 'W';
                    }
                    // Check for success indicators
                    else if (parentClasses.includes('success') ||
                             parentClasses.includes('erfolg') ||
                             statusElement.querySelector('[class*="success" i], .sapMsgSuccess')) {
                        type = 'S';
                    }

                    // Also check message content for common patterns
                    const msgLower = message.toLowerCase();
                    if (type === 'I') {  // Only override if not already detected
                        if (msgLower.includes('fehler') || msgLower.includes('error') ||
                            msgLower.includes('nicht gefunden') || msgLower.includes('not found') ||
                            msgLower.includes('ungültig') || msgLower.includes('invalid')) {
                            type = 'E';
                        } else if (msgLower.includes('warnung') || msgLower.includes('warning')) {
                            type = 'W';
                        } else if (msgLower.includes('gesichert') || msgLower.includes('saved') ||
                                   msgLower.includes('angelegt') || msgLower.includes('created') ||
                                   msgLower.includes('erfolgreich') || msgLower.includes('successful')) {
                            type = 'S';
                        }
                    }

                    return { type: type, message: message };
                }
                """
            )

            return json.dumps(status_info, ensure_ascii=False)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error reading status bar")
            return f"Error reading status bar: {e}"

    @mcp.tool(description="Get technical information about the current SAP screen")
    async def sap_get_screen_info() -> str:
        """
        Get technical information about the current SAP screen.

        Returns:
            JSON with:
            - transaction: Current transaction code (if detectable)
            - title: Window/page title
            - url: Current URL
            - program: ABAP program name (if available in page)
            - dynpro: Screen number (if available)
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            # Extract screen info using JavaScript
            screen_info = await page.evaluate(
                """
                () => {
                    const info = {
                        transaction: '',
                        title: document.title,
                        url: window.location.href,
                        program: '',
                        dynpro: ''
                    };

                    // Try to find transaction code from various locations
                    // OK-Code field might contain current transaction
                    const okCodeField = document.querySelector(
                        '#ToolbarOkCode, input[id*="okcode" i]'
                    );
                    if (okCodeField && okCodeField.value) {
                        info.transaction = okCodeField.value.replace(/^\\/[no]/, '');
                    }

                    // Check title bar for transaction info
                    // SAP often shows "Transaction - Description" or similar
                    const titleMatch = document.title.match(/^([A-Z0-9_\\/]+)\\s*[-:]|\\(([A-Z0-9_]+)\\)/);
                    if (titleMatch) {
                        info.transaction = info.transaction || (titleMatch[1] || titleMatch[2] || '').trim();
                    }

                    // Look for technical info in hidden fields or data attributes
                    const techInfo = document.querySelector(
                        '[data-program], [data-dynpro], [data-tcode], ' +
                        'input[name*="program" i], input[name*="dynpro" i]'
                    );
                    if (techInfo) {
                        info.program = techInfo.getAttribute('data-program') ||
                                      techInfo.getAttribute('name') || '';
                        info.dynpro = techInfo.getAttribute('data-dynpro') || '';
                    }

                    // Try to extract from URL if it contains transaction info
                    const urlMatch = window.location.href.match(/[?&](?:tcode|transaction)=([^&]+)/i);
                    if (urlMatch) {
                        info.transaction = info.transaction || urlMatch[1];
                    }

                    return info;
                }
                """
            )

            return json.dumps(screen_info, indent=2, ensure_ascii=False)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting screen info")
            return f"Error getting screen info: {e}"

    @mcp.tool(description="Look up known field selectors for an SAP transaction")
    async def sap_lookup_fields(transaction: str) -> str:
        """
        Look up known field selectors for an SAP transaction.

        This tool returns pre-discovered CSS selectors for input fields
        in common SAP transactions. Use this BEFORE trying to interact
        with a transaction to find the correct field selectors.

        Args:
            transaction: Transaction code (e.g., SE16, VA01, BP)

        Returns:
            JSON with known field selectors for the transaction,
            or a message if the transaction is not in the registry.
        """
        try:
            # Load the field registry
            try:
                registry_file = resources.files("sapwebguimcp.data").joinpath("sap_field_registry.json")
                registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-exception-caught
                return "Field registry not available. Use sap_discover_fields to find fields on current screen."

            # Look up the transaction (case-insensitive)
            tcode_upper = transaction.upper().strip()
            if tcode_upper in registry_data:
                result = {
                    "transaction": tcode_upper,
                    "fields": registry_data[tcode_upper],
                }
                return json.dumps(result, indent=2, ensure_ascii=False)

            # Check if it's a partial match
            matches = [k for k in registry_data.keys() if not k.startswith("_") and tcode_upper in k]
            if matches:
                return f"Transaction '{tcode_upper}' not found. Similar: {', '.join(matches)}"

            return (
                f"Transaction '{tcode_upper}' not in field registry. "
                "Use sap_discover_fields to discover fields on the current screen."
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error looking up fields")
            return f"Error looking up fields: {e}"

    @mcp.tool(description="Discover input fields on the current SAP screen")
    async def sap_discover_fields() -> str:
        """
        Discover all input fields on the current SAP screen.

        This tool analyzes the current page and returns information about
        all visible input fields, including their IDs, names, labels, and
        suggested CSS selectors.

        Use this when sap_lookup_fields doesn't have information for
        the current transaction.

        Returns:
            JSON with discovered fields including:
            - id: Element ID
            - name: Element name attribute
            - label: Associated label text (if found)
            - type: Input type
            - selector: Suggested CSS selector to use
            - value: Current value (if any)
        """
        ctx = mcp.get_context()
        browser_manager: BrowserManager = ctx.request_context.lifespan_context.browser_manager

        try:
            page = await browser_manager.get_current_page()

            # Discover fields using JavaScript
            fields = await page.evaluate(
                """
                () => {
                    const fields = [];

                    // Find all input elements
                    document.querySelectorAll('input, select, textarea').forEach(el => {
                        // Skip hidden and submit buttons
                        if (el.type === 'hidden' || el.type === 'submit' || el.type === 'button') {
                            return;
                        }

                        // Skip if not visible
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 || rect.height === 0) {
                            return;
                        }

                        const field = {
                            id: el.id || '',
                            name: el.name || '',
                            type: el.type || el.tagName.toLowerCase(),
                            value: el.value ? el.value.substring(0, 50) : '',
                            label: '',
                            selector: ''
                        };

                        // Find associated label
                        if (el.id) {
                            const label = document.querySelector(`label[for="${el.id}"]`);
                            if (label) {
                                field.label = label.textContent.trim().substring(0, 50);
                            }
                        }

                        // If no label found, look for nearby text
                        if (!field.label) {
                            const parent = el.parentElement;
                            if (parent) {
                                const prevSibling = el.previousElementSibling;
                                if (prevSibling && prevSibling.tagName !== 'INPUT') {
                                    field.label = prevSibling.textContent.trim().substring(0, 50);
                                }
                            }
                        }

                        // Generate best selector
                        if (el.id) {
                            field.selector = `#${el.id}`;
                        } else if (el.name) {
                            field.selector = `input[name="${el.name}"]`;
                        } else if (field.label) {
                            field.selector = `input:near(:text("${field.label}"))`;
                        }

                        fields.push(field);
                    });

                    return fields;
                }
                """
            )

            return json.dumps(
                {
                    "fieldCount": len(fields),
                    "fields": fields,
                    "hint": "Use the 'selector' values with browser_fill or browser_click tools",
                },
                indent=2,
                ensure_ascii=False,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error discovering fields")
            return f"Error discovering fields: {e}"
