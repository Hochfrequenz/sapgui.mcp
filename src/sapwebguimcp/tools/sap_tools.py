"""
SAP-specific MCP tools for SAP Web GUI automation.

This module contains tools for:
- sap_login: Log into SAP Web GUI
- sap_transaction: Enter and execute SAP transaction codes
- sap_keepalive_start/stop: Keep SAP session alive
"""

import asyncio
import logging
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

            # Set language via JavaScript (field is often hidden)
            await page.evaluate(
                f'document.querySelector(\'input[name="sap-language"]\').value = "{settings.sap_language}"'
            )

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
                        "You may need to enable it manually: "
                        "Menu → Settings → Enable 'OK-Code Field' or 'Transaction Field'"
                    )

                await page.wait_for_timeout(500)

                okcode_field = await _find_okcode_field(page)
                if not okcode_field:
                    return (
                        f"OK-Code field still not visible after enabling. {message} "
                        "Please try enabling it manually in SAP settings."
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
