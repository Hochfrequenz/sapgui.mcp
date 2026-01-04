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
- sap_read_table: Read data from ALV grids and tables (with cell selectors)
- sap_click_table_cell: Click a cell in an ALV grid table
- sap_read_status_bar: Read status bar messages
- sap_get_screen_info: Get technical screen information
- sap_lookup_fields: Look up known field selectors for a transaction
- sap_discover_fields: Discover input fields on current screen
"""

import asyncio
import json
import logging
import re
from functools import lru_cache
from importlib import resources
from typing import Any, Optional

from fastmcp import FastMCP

from sapwebguimcp.models import (
    AlvCellInfo,
    AlvMetadata,
    BrowserManager,
    DiscoveredFields,
    DismissPopupResult,
    FieldFillError,
    FieldInfo,
    FieldLookupResult,
    FillFormResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    PopupButton,
    PopupInfo,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    SetFieldResult,
    ShortcutInfo,
    ShortcutsResult,
    StatusBarInfo,
    TableCellClickResult,
    TableData,
    TableRow,
    TransactionResult,
    get_browser_manager,
    get_settings,
)
from sapwebguimcp.tools.browser_tools import _escape_css_selector
from sapwebguimcp.utils import is_sap_shortcut

__all__ = ["register_sap_tools", "SELECTORS", "parse_shortcut_from_title"]

logger = logging.getLogger(__name__)


@lru_cache(maxsize=16)
def _load_js(filename: str) -> str:
    """Load a JavaScript file from the sapwebguimcp.js package."""
    return resources.files("sapwebguimcp.js").joinpath(filename).read_text(encoding="utf-8")


# =============================================================================
# Popup Detection
# =============================================================================


async def _check_blocking_popup(page: Any) -> PopupInfo | None:
    """
    Fast check for blocking popup dialog.

    Checks for SAP popup overlay layers and extracts popup info if present.
    This is designed to be fast (~5-10ms) to avoid slowing down normal operations.

    Args:
        page: Playwright Page instance

    Returns:
        PopupInfo if a blocking popup is present, None otherwise
    """
    js_code = _load_js("check_popup.js")
    result = await page.evaluate(js_code)

    if result is None:
        return None

    buttons = [
        PopupButton(
            label=btn["label"],
            accesskey=btn.get("accesskey"),
            id=btn.get("id"),
        )
        for btn in result.get("buttons", [])
    ]

    return PopupInfo(
        message=result.get("message"),
        buttons=buttons,
        close_button_id=result.get("close_button_id"),
    )


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

            logger.info("Keepalive ping sent")

        except asyncio.CancelledError:
            logger.info("Keepalive task cancelled")
            break
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Keepalive error (will retry): %s", e)


async def _start_keepalive(interval_seconds: int = 300) -> KeepaliveResult:
    """
    Start the keepalive background task.

    This is the implementation used by both the sap_keepalive_start tool
    and called internally from sap_login.

    Args:
        interval_seconds: Seconds between keepalive pings (default: 300 = 5 minutes)

    Returns:
        KeepaliveResult indicating the keepalive is running.
    """
    global _keepalive_task, _keepalive_interval  # pylint: disable=global-statement

    browser_manager = await get_browser_manager()

    # Stop existing task if running
    if _keepalive_task is not None and not _keepalive_task.done():
        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass

    _keepalive_interval = interval_seconds
    _keepalive_task = asyncio.create_task(_keepalive_loop(browser_manager, interval_seconds))

    return KeepaliveResult(
        running=True,
        interval_seconds=interval_seconds,
    )


# =============================================================================
# Shortcut Extraction
# =============================================================================

# Pattern: "Action Text (Shortcut)" where Shortcut can be:
# F1-F12, Strg+F1, Umschalt+F1, Strg+Umschalt+F1, Eingabe, Strg+S, etc.
_SHORTCUT_PATTERN = re.compile(r"(.+)\s+\(([^)]+)\)$")


def _is_keyboard_shortcut(shortcut: str) -> bool:
    """
    Check if a string looks like a keyboard shortcut.

    Valid shortcuts include:
    - F1-F12, Eingabe, Enter, Escape, Esc
    - Strg+S, Ctrl+S, Strg+F1
    - Umschalt+F1, Shift+F1
    - Strg+Umschalt+F1, Ctrl+Shift+F1
    """
    shortcut_lower = shortcut.lower()

    # Function keys
    if re.match(r"^f\d{1,2}$", shortcut_lower):
        return True

    # Special keys
    if shortcut_lower in ("eingabe", "enter", "escape", "esc", "entf", "delete"):
        return True

    # Modifier + key combinations
    if any(mod in shortcut_lower for mod in ("strg", "ctrl", "umschalt", "shift", "alt")):
        return True

    return False


def parse_shortcut_from_title(title: str) -> ShortcutInfo | None:
    """
    Parse a title attribute value for keyboard shortcut.

    SAP buttons have title attributes like:
    - "Person anlegen (F5)"
    - "Beenden (Umschalt+F3)"
    - "Als Variante sichern (Strg+S)"

    This function is exported for unit testing - the MCP tool sap_get_shortcuts
    uses Playwright to get title attributes directly, then passes them here.

    Args:
        title: Title attribute value (e.g., "Person anlegen (F5)")

    Returns:
        ShortcutInfo if a valid keyboard shortcut is found, None otherwise.
        Returns None for non-keyboard patterns like dates or numbers.

    Examples:
        >>> parse_shortcut_from_title("Person anlegen (F5)")
        ShortcutInfo(action='Person anlegen', shortcut='F5')
        >>> parse_shortcut_from_title("Save (Strg+S)")
        ShortcutInfo(action='Save', shortcut='Strg+S')
        >>> parse_shortcut_from_title("Created (2024-01-01)")  # Not a shortcut
        None
    """
    match = _SHORTCUT_PATTERN.match(title.strip())
    if not match:
        return None

    action = match.group(1).strip()
    shortcut = match.group(2).strip()

    if not _is_keyboard_shortcut(shortcut):
        return None

    return ShortcutInfo(action=action, shortcut=shortcut)


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


def register_sap_tools(mcp: FastMCP) -> None:  # pylint: disable=too-many-statements,too-many-locals
    """Register all SAP-specific tools with the MCP server."""

    @mcp.tool(description="Start a background task that keeps the SAP session alive")
    async def sap_keepalive_start(interval_seconds: int = 300) -> KeepaliveResult:
        """
        Start a background task that keeps the SAP session alive.

        This prevents SAP from logging you out due to inactivity.
        The task runs in the background and periodically pings the browser
        to maintain the session.

        Args:
            interval_seconds: Seconds between keepalive pings (default: 300 = 5 minutes)

        Returns:
            KeepaliveResult indicating the keepalive is running.
        """
        return await _start_keepalive(interval_seconds)

    @mcp.tool(description="Stop the background keepalive task")
    async def sap_keepalive_stop() -> KeepaliveResult:
        """
        Stop the background keepalive task.

        Call this when you're done with SAP or want to allow the session to timeout naturally.

        Returns:
            KeepaliveResult indicating the keepalive is stopped.
        """
        global _keepalive_task  # pylint: disable=global-statement

        if _keepalive_task is None or _keepalive_task.done():
            return KeepaliveResult(running=False)

        _keepalive_task.cancel()
        try:
            await _keepalive_task
        except asyncio.CancelledError:
            pass

        _keepalive_task = None
        return KeepaliveResult(running=False)

    @mcp.tool(description="Log into SAP Web GUI")
    async def sap_login(  # pylint: disable=too-many-return-statements
        url: Optional[str] = None,
    ) -> LoginResult:
        """
        Log into SAP Web GUI.

        Opens the SAP Web GUI URL and automatically logs in using credentials
        from environment variables (SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE).

        If credentials are not configured, opens the login page for manual entry.

        Args:
            url: SAP Web GUI URL. If not provided, uses SAP_URL from environment.

        Returns:
            LoginResult indicating login success or what action is needed.
        """
        browser_manager = await get_browser_manager()

        settings = get_settings()

        page = await browser_manager.get_current_page()
        effective_url = url or settings.sap_url

        if not effective_url:
            return LoginResult.failure(
                "No SAP URL provided. Either pass a URL parameter or set the SAP_URL environment variable."
            )

        try:
            logger.info("Navigating to SAP Web GUI: %s", effective_url)
            await page.goto(effective_url)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Check if we're already logged in
            okcode_field = await _find_okcode_field(page)
            if okcode_field:
                # Start keepalive to prevent session timeout
                await _start_keepalive()
                return LoginResult(
                    url=effective_url,
                    already_logged_in=True,
                )

            # Check for login form
            login_form = await page.query_selector('input[type="password"], input[id*="user" i]')
            if not login_form:
                return LoginResult.failure(
                    f"Navigated to {effective_url}. No login form detected - please check browser window.",
                    url=effective_url,
                )

            # Check if we have credentials for auto-login
            if not all([settings.sap_user, settings.sap_password, settings.sap_mandant]):
                return LoginResult.failure(
                    "Credentials not configured (SAP_USER, SAP_PASSWORD, SAP_MANDANT). "
                    "Please enter credentials manually in the browser window.",
                    url=effective_url,
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
                    _load_js("set_language_field.js"),
                    {"language": settings.sap_language},
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
                # Start keepalive to prevent session timeout
                await _start_keepalive()
                return LoginResult(
                    url=effective_url,
                    user=settings.sap_user,
                )
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
                        # Start keepalive to prevent session timeout
                        await _start_keepalive()
                        return LoginResult(
                            url=effective_url,
                            user=settings.sap_user,
                            already_logged_in=True,
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

                return LoginResult.failure(
                    "Login attempted but SAP Easy Access not detected. "
                    "Please check browser window for errors or dialogs.",
                    url=effective_url,
                )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error during SAP login")
            return LoginResult.failure(f"Error during SAP login: {e}", url=effective_url)

    @mcp.tool(description="Enter and execute an SAP transaction code")
    async def sap_transaction(  # pylint: disable=too-many-return-statements
        tcode: str, new_window: bool = False
    ) -> TransactionResult:
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
            TransactionResult indicating success or describing any issues.
        """
        browser_manager = await get_browser_manager()

        page = await browser_manager.get_current_page()

        # Fast popup check (~5ms)
        popup = await _check_blocking_popup(page)
        if popup:
            return TransactionResult.failure(
                f"Popup blocking: {popup.message or 'confirmation required'}",
                tcode=tcode,
                blocking_popup=popup,
            )

        try:
            # Step 1: Check if OK-Code field exists
            okcode_field = await _find_okcode_field(page)

            if not okcode_field:
                logger.info("OK-Code field not found, attempting to enable it")

                # Step 2: Try to enable the OK-Code field
                success, message = await _enable_okcode_field(page)
                logger.info("Enable OK-Code result: %s - %s", success, message)

                if not success:
                    return TransactionResult.failure(
                        f"Could not find or enable OK-Code field. {message} "
                        "Possible causes: (1) A popup/dialog may be blocking the screen - "
                        "close any open dialogs first. (2) The OK-Code field may need to be "
                        "enabled manually: Menu → Settings → Enable 'OK-Code Field' or "
                        "'Transaction Field'.",
                        tcode=tcode,
                    )

                okcode_field = await _find_okcode_field(page)
                if not okcode_field:
                    return TransactionResult.failure(
                        f"OK-Code field still not visible after enabling. {message} "
                        "Possible causes: (1) A popup/dialog may be blocking the screen - "
                        "close any open dialogs first. (2) Please try enabling it manually "
                        "in SAP settings.",
                        tcode=tcode,
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
            logger.debug("Clicked OK-Code field to ensure focus")

            await page.evaluate(
                _load_js("set_okcode_field.js"),
                {"transactionInput": transaction_input},
            )

            await page.wait_for_timeout(300)
            logger.debug("Set transaction code via JavaScript: %s", transaction_input)

            # Now use Playwright's keyboard to press Enter - this triggers SAP's navigation
            await page.keyboard.press("Enter")
            logger.debug("Pressed Enter to execute transaction")

            await page.wait_for_load_state("networkidle", timeout=15000)

            # Small wait to let popup render if it appeared
            await page.wait_for_timeout(200)

            # Check if a popup appeared after navigation (e.g., "Discard changes?")
            popup = await _check_blocking_popup(page)
            logger.debug("Popup check after Enter: %s", popup)
            if popup:
                return TransactionResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    tcode=tcode,
                    blocking_popup=popup,
                )

            title = await page.title()

            # Build response
            if new_window:
                # When opening in new window, count browser pages/tabs
                # SAP opens new sessions in new browser windows/tabs
                context = page.context
                pages = context.pages
                session_count = len(pages)
                return TransactionResult(
                    tcode=tcode,
                    page_title=title,
                    new_window=True,
                    session_count=session_count,
                )

            return TransactionResult(
                tcode=tcode,
                page_title=title,
                new_window=False,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error executing transaction")
            return TransactionResult.failure(f"Error executing transaction {tcode}: {e}", tcode=tcode)

    @mcp.tool(description="Check the current SAP session status")
    async def sap_session_status() -> SessionStatus:
        """
        Check the current SAP session status.

        Useful to verify the session is still active before performing actions,
        especially after long pauses or agent questions.

        Returns:
            SessionStatus with status one of:
            - "active": Session is alive and responsive
            - "timed_out": Session has timed out
            - "logged_off": User has been logged off
            - "no_page": No browser page available
            - "unknown": Cannot determine status
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            if page.is_closed():
                return SessionStatus(status="no_page", message="Browser page is closed.")

            # Check for OK-Code field (indicates active SAP session)
            okcode_field = await _find_okcode_field(page)
            if okcode_field:
                return SessionStatus(status="active", message="SAP session is alive and responsive.")

            # Check for login form (indicates logged off)
            login_form = await page.query_selector('input[type="password"], input[id*="sap-user" i], #sap-user')
            if login_form:
                return SessionStatus(
                    status="logged_off",
                    message="Login page detected. Please use sap_login to log in again.",
                )

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
                return SessionStatus(
                    status="timed_out",
                    message="Session has timed out. Please use sap_login to reconnect.",
                )

            return SessionStatus(
                status="unknown",
                message="Cannot determine session status. Please check browser window.",
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error checking session status")
            return SessionStatus(status="unknown", message=f"Error checking status: {e}")

    @mcp.tool(description="Send a keyboard shortcut to SAP Web GUI")
    async def sap_keyboard(key: str) -> KeyboardResult:
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
            KeyboardResult with the key sent, page title, and status bar (for shortcuts).
            Status bar is auto-read for F-keys and Ctrl+* since SAP often shows feedback there.
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Fast popup check (~5ms) - only blocks if popup exists BEFORE keystroke
            popup = await _check_blocking_popup(page)
            if popup:
                logger.debug("sap_keyboard(%s): popup already present before keystroke", key)
                return KeyboardResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    key=key,
                    blocking_popup=popup,
                )

            # Ensure page is in front
            await page.bring_to_front()
            await page.wait_for_timeout(100)

            # Send the keystroke
            await page.keyboard.press(key)

            # Wait for SAP to respond
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Wait for popup to render (SAP popups may appear after networkidle)
            await page.wait_for_timeout(300)

            # Check if a popup appeared after the keystroke
            popup_after = await _check_blocking_popup(page)
            if popup_after:
                logger.debug("sap_keyboard(%s): popup appeared after keystroke", key)
                return KeyboardResult.failure(
                    f"Popup blocking: {popup_after.message or 'confirmation required'}",
                    key=key,
                    blocking_popup=popup_after,
                )

            title = await page.title()

            # Auto-read status bar for shortcuts (F-keys or Ctrl+*)
            if is_sap_shortcut(key):
                try:
                    status_info = await page.evaluate(_load_js("extract_status_bar.js"))
                    return KeyboardResult(
                        key=key,
                        page_title=title,
                        status_bar_read=True,
                        status_bar_type=status_info.get("type", "none"),
                        status_bar_message=status_info.get("message", ""),
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    # Status bar read failed, but keystroke succeeded
                    return KeyboardResult(
                        key=key,
                        page_title=title,
                        status_bar_read=False,
                    )

            return KeyboardResult(key=key, page_title=title)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error sending keyboard shortcut")
            return KeyboardResult.failure(f"Error sending keyboard shortcut {key}: {e}", key=key)

    @mcp.tool(description="Get all readable text from the current SAP screen")
    async def sap_get_screen_text() -> ScreenText:
        """
        Get all readable text from the current SAP screen.

        This tool extracts text content for adaptive field discovery.
        Use it to identify field labels, button texts, and screen content
        when you need to work with screens that vary by system configuration.

        Returns:
            ScreenText with structured content including:
            - Screen title
            - Field labels and values
            - Button labels
            - Tab labels
            - Status messages
            - Table headers
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Extract text using JavaScript for comprehensive coverage
            screen_text = await page.evaluate(_load_js("extract_screen_text.js"))

            # Deduplicate lists
            unique_labels = list(dict.fromkeys(screen_text.get("labels", [])))[:50]
            unique_buttons = list(dict.fromkeys(screen_text.get("buttons", [])))[:20]
            unique_headers = list(dict.fromkeys(screen_text.get("tableHeaders", [])))[:20]
            content_sample = screen_text.get("mainContent", [])[:30]

            return ScreenText(
                title=screen_text.get("title", ""),
                status_bar=screen_text.get("statusBar"),
                tabs=screen_text.get("tabs", []),
                labels=unique_labels,
                buttons=unique_buttons,
                table_headers=unique_headers,
                main_content=content_sample,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting screen text")
            return ScreenText.failure(f"Error getting screen text: {e}", title="")

    @mcp.tool(description="Read data from an ALV grid or table on the current screen")
    async def sap_read_table(start_row: int = 1, end_row: Optional[int] = None, max_rows: int = 100) -> TableData:
        """
        Read rows from an ALV grid or table on the current screen.

        Works with SAP ALV grids, step loops, and list displays.

        Args:
            start_row: First row to read (1-indexed, default: 1)
            end_row: Last row to read (None = up to max_rows visible rows)
            max_rows: Maximum rows to return (default: 100, prevents huge responses)

        Returns:
            TableData with column headers and row values.
            Empty columns are excluded to reduce response size.
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Extract table data using JavaScript
            table_data = await page.evaluate(
                _load_js("extract_table_data.js"),
                {"startRow": start_row, "endRow": end_row, "maxRows": max_rows},
            )

            if "error" in table_data:
                return TableData.failure(str(table_data["error"]))

            # Parse rows, converting cell metadata for ALV grids
            rows = []
            for row_data in table_data.get("rows", []):
                cells = None
                if "cells" in row_data and row_data["cells"]:
                    cells = {
                        col: AlvCellInfo(
                            selector=info["selector"],
                            clickable=info.get("clickable", False),
                            hotspot=info.get("hotspot", False),
                        )
                        for col, info in row_data["cells"].items()
                    }
                rows.append(
                    TableRow(
                        row=row_data["row"],
                        data=row_data["data"],
                        cells=cells,
                    )
                )

            # Parse ALV metadata if present
            alv = None
            if "alv" in table_data and table_data["alv"]:
                alv_data = table_data["alv"]
                alv = AlvMetadata(
                    table_id=alv_data["table_id"],
                    selection_mode=alv_data.get("selection_mode", "NONE"),
                    hotspot_columns=alv_data.get("hotspot_columns", []),
                    column_map=alv_data.get("column_map", {}),
                )

            return TableData(
                headers=table_data.get("headers", []),
                rows=rows,
                total_rows=table_data.get("totalRows", 0),
                start_row=table_data.get("startRow", start_row),
                end_row=table_data.get("endRow"),
                alv=alv,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error reading table")
            return TableData.failure(f"Error reading table: {e}")

    @mcp.tool(
        description=(
            "Click a cell in an ALV grid table. "
            "Automatically targets the correct clickable element (hotspot span vs TD). "
            "Use after sap_read_table to navigate to detail views."
        )
    )
    async def sap_click_table_cell(
        row: int,
        column: int | str,
        action: str = "click",
    ) -> TableCellClickResult:
        """
        Click a cell in the current ALV grid table.

        Automatically detects the table structure and targets the correct
        clickable element. For hotspot cells (underlined, navigable), clicks
        the inner span. For regular cells, clicks the TD element.

        Args:
            row: Row number (1-indexed, data rows start at 1)
            column: Column index (0-based) or column header name
            action: "click" for single click, "dblclick" for double-click

        Returns:
            TableCellClickResult with the selector used and page title after click.
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Use JavaScript to find the correct click target (but not click yet)
            result = await page.evaluate(
                _load_js("click_table_cell.js"),
                {"row": row, "column": column, "action": action, "performClick": False},
            )

            if "error" in result:
                return TableCellClickResult.failure(
                    str(result["error"]),
                    row=row,
                    column=column,
                    selector_used="",
                )

            selector = result["selector"]

            # Use Playwright's native click - provides trusted events SAP requires
            if action == "dblclick":
                await page.dblclick(selector)
            else:
                await page.click(selector)

            # Wait for SAP to process the click event
            await asyncio.sleep(0.5)

            # Wait for navigation/network activity
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Additional wait for SAP AJAX updates
            await asyncio.sleep(0.3)

            title = await page.title()

            return TableCellClickResult(
                row=row,
                column=result.get("column", column),
                selector_used=selector,
                page_title=title,
                was_hotspot=result.get("wasHotspot", False),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error clicking table cell")
            return TableCellClickResult.failure(
                f"Error clicking table cell: {e}",
                row=row,
                column=column,
                selector_used="",
            )

    @mcp.tool(description="Read the current message from SAP's status bar")
    async def sap_read_status_bar() -> StatusBarInfo:
        """
        Read the current message from SAP's status bar.

        SAP displays success, error, warning, and info messages in the status bar.
        Whenever you're stuck, maybe check the status bar for hints what to do.
        This tool extracts that message for programmatic checking.

        Returns:
            StatusBarInfo with:
            - type: "S" (success), "E" (error), "W" (warning), "I" (info), or "none"
            - message: The status bar text
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Extract status bar content using JavaScript
            status_info = await page.evaluate(_load_js("extract_status_bar.js"))

            return StatusBarInfo(
                type=status_info.get("type", "none"),
                message=status_info.get("message", ""),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error reading status bar")
            return StatusBarInfo.failure(f"Error reading status bar: {e}", type="none")

    @mcp.tool(description="Get technical information about the current SAP screen")
    async def sap_get_screen_info() -> ScreenInfo:
        """
        Get technical information about the current SAP screen.

        Returns:
            ScreenInfo with:
            - transaction: Current transaction code (if detectable)
            - title: Window/page title
            - url: Current URL
            - program: ABAP program name (if available in page)
            - dynpro: Screen number (if available)
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Check for blocking popup
            popup = await _check_blocking_popup(page)

            # Extract screen info using JavaScript
            screen_info = await page.evaluate(_load_js("extract_screen_info.js"))

            return ScreenInfo(
                transaction=screen_info.get("transaction"),
                title=screen_info.get("title", ""),
                url=screen_info.get("url", ""),
                program=screen_info.get("program"),
                dynpro=screen_info.get("dynpro"),
                blocking_popup=popup,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting screen info")
            return ScreenInfo.failure(f"Error getting screen info: {e}", title="", url="")

    @mcp.tool(description="Look up known field selectors for an SAP transaction")
    async def sap_lookup_fields(transaction: str) -> FieldLookupResult:
        """
        Look up known field selectors for an SAP transaction.

        This tool returns pre-discovered CSS selectors for input fields
        in common SAP transactions. Use this BEFORE trying to interact
        with a transaction to find the correct field selectors.

        Args:
            transaction: Transaction code (e.g., SE16, VA01, BP)

        Returns:
            FieldLookupResult with known field selectors for the transaction.
        """
        tcode_upper = transaction.upper().strip()

        try:
            # Load the field registry
            try:
                registry_file = resources.files("sapwebguimcp.data").joinpath("sap_field_registry.json")
                registry_data = json.loads(registry_file.read_text(encoding="utf-8"))
            except Exception:  # pylint: disable=broad-exception-caught
                return FieldLookupResult.failure(
                    "Field registry not available. Use sap_discover_fields to find fields on current screen.",
                    transaction=tcode_upper,
                )

            # Look up the transaction (case-insensitive)
            if tcode_upper in registry_data:
                tcode_data = registry_data[tcode_upper]

                # Flatten nested screens structure into a single dict
                # Registry format: {"screens": {"initial": {"field": "selector"}, ...}}
                fields: dict[str, str] = {}
                screens = tcode_data.get("screens", {})
                for screen_name, screen_fields in screens.items():
                    if isinstance(screen_fields, dict):
                        for field_name, selector in screen_fields.items():
                            # Prefix with screen name if field name would collide
                            key = f"{screen_name}.{field_name}" if field_name in fields else field_name
                            fields[key] = selector

                return FieldLookupResult(
                    transaction=tcode_upper,
                    fields=fields,
                )

            # Check if it's a partial match
            matches = [k for k in registry_data.keys() if not k.startswith("_") and tcode_upper in k]
            if matches:
                return FieldLookupResult.failure(
                    f"Transaction '{tcode_upper}' not found.",
                    transaction=tcode_upper,
                    similar_transactions=matches,
                )

            return FieldLookupResult.failure(
                f"Transaction '{tcode_upper}' not in field registry. "
                "Use sap_discover_fields to discover fields on the current screen.",
                transaction=tcode_upper,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error looking up fields")
            return FieldLookupResult.failure(f"Error looking up fields: {e}", transaction=tcode_upper)

    @mcp.tool(
        description=(
            "Discover input fields on the current SAP screen. "
            "Returns fields with reliable CSS selectors (use the 'selector' field). "
            "Call once per screen, not repeatedly - results are consistent."
        )
    )
    async def sap_discover_fields() -> DiscoveredFields:
        """
        Discover all input fields on the current SAP screen.

        This tool analyzes the current page and returns information about
        all visible input fields with reliable CSS selectors.

        IMPORTANT: Use the 'selector' field directly with sap_fill_form or
        sap_set_field - it is designed to work reliably. Avoid using raw
        element IDs which may contain special characters.

        Returns:
            DiscoveredFields with list of fields including:
            - field_id: SAP field ID (e.g., 'NAME_FIRST', 'STREET')
            - label: Associated label text (for display)
            - selector: Reliable CSS selector to use with sap_fill_form
            - alternative_selectors: Other valid selectors (fallbacks)
            - type: Input type (text, checkbox, etc.)
            - value: Current value (if any)
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Discover fields using JavaScript
            fields_data = await page.evaluate(_load_js("discover_fields.js"))

            fields = [
                FieldInfo(
                    id=f.get("id"),
                    name=f.get("name"),
                    field_id=f.get("fieldId"),
                    label=f.get("label"),
                    type=f.get("type"),
                    selector=f.get("selector", ""),
                    alternative_selectors=f.get("alternativeSelectors", []),
                    value=f.get("value"),
                )
                for f in fields_data
            ]

            return DiscoveredFields(
                field_count=len(fields),
                fields=fields,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error discovering fields")
            return DiscoveredFields.failure(f"Error discovering fields: {e}", field_count=0)

    @mcp.tool(
        description=(
            "Discover keyboard shortcuts available on the current SAP screen. "
            "Use BEFORE clicking buttons - shortcuts like F5, Strg+S are faster and more reliable. "
            "Returns action text and key combination for each available shortcut."
        )
    )
    async def sap_get_shortcuts() -> ShortcutsResult:
        """
        Discover keyboard shortcuts available on the current SAP screen.

        SAP buttons often have keyboard shortcuts that are faster and more reliable
        than clicking. This tool finds all available shortcuts by analyzing button
        titles like "Person anlegen (F5)" or "Speichern (Strg+S)".

        Use this tool to discover shortcuts BEFORE attempting button clicks.
        Then use sap_keyboard to execute the shortcut.

        Returns:
            ShortcutsResult with list of ShortcutInfo objects containing:
            - action: Button/action text (e.g., "Person anlegen")
            - shortcut: Key combination (e.g., "F5", "Strg+S")
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Get all title attributes via JavaScript - much more efficient than parsing HTML
            titles: list[str] = await page.evaluate(
                """() => {
                    const elements = document.querySelectorAll('[title]');
                    return Array.from(elements).map(el => el.title);
                }"""
            )

            # Parse titles for shortcuts
            shortcuts: list[ShortcutInfo] = []
            seen: set[tuple[str, str]] = set()

            for title in titles:
                shortcut_info: ShortcutInfo | None = parse_shortcut_from_title(title)
                if shortcut_info is None:
                    continue

                # Skip duplicates (action and shortcut are str fields)
                # pylint: disable=no-member  # False positive: ShortcutInfo.action/shortcut are str
                action_lower: str = shortcut_info.action.lower()
                shortcut_lower: str = shortcut_info.shortcut.lower()
                key = (action_lower, shortcut_lower)
                if key in seen:
                    continue
                seen.add(key)

                shortcuts.append(shortcut_info)

            return ShortcutsResult(shortcuts=shortcuts)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error getting shortcuts")
            return ShortcutsResult.failure(f"Error getting shortcuts: {e}")

    @mcp.tool(
        description=(
            "Dismiss a blocking popup dialog by clicking a button. "
            "Use after a tool returns blocking_popup info. "
            "Specify button by label ('Ja', 'Nein') or accesskey ('J', 'N'), "
            "or use close=True to click the X button if available."
        )
    )
    async def sap_dismiss_popup(  # pylint: disable=too-many-branches
        button: Optional[str] = None,
        close: bool = False,
    ) -> DismissPopupResult:
        """
        Dismiss a blocking popup dialog.

        Args:
            button: Button label (e.g., 'Ja', 'Nein') or accesskey (e.g., 'J', 'N')
            close: Click the X close button instead of a specific button

        Returns:
            DismissPopupResult with success status and button clicked
        """
        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Check if popup is present
            popup = await _check_blocking_popup(page)
            if popup is None:
                return DismissPopupResult.failure("No popup to dismiss")

            # Determine what to click and the label for the result
            clicked_label: str
            if close:
                if not popup.has_close_button:
                    return DismissPopupResult.failure("No close button available")
                # SAP IDs contain special characters - use CSS escaping
                await page.click(_escape_css_selector(f"#{popup.close_button_id}"))
                clicked_label = "[X]"
            elif not button:
                return DismissPopupResult.failure("Specify button or close=True")
            else:
                # Find matching button by label or accesskey
                button_lower = button.lower()
                matched_button: PopupButton | None = None

                for btn in popup.buttons:
                    if btn.label.lower() == button_lower:
                        matched_button = btn
                        break
                    if btn.accesskey and btn.accesskey.lower() == button_lower:
                        matched_button = btn
                        break

                if not matched_button:
                    available = [b.label for b in popup.buttons]
                    return DismissPopupResult.failure(f"Button '{button}' not found. Available: {available}")

                # Click the button using best available method
                if matched_button.id:
                    # SAP IDs contain special characters - use CSS escaping
                    await page.click(_escape_css_selector(f"#{matched_button.id}"))
                elif matched_button.accesskey:
                    await page.keyboard.press(f"Alt+{matched_button.accesskey}")
                else:
                    await page.click(f"button:has-text('{matched_button.label}')")
                clicked_label = matched_button.label

            # Wait and verify popup is gone
            await page.wait_for_timeout(500)
            popup_after = await _check_blocking_popup(page)
            return DismissPopupResult(
                button_clicked=clicked_label,
                popup_dismissed=popup_after is None,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error dismissing popup")
            return DismissPopupResult.failure(f"Error dismissing popup: {e}")

    @mcp.tool(
        description=(
            "Fill multiple SAP form fields in a single call. "
            "Use this when filling 2+ fields on the SAME screen without UI navigation between them. "
            "Much faster than multiple browser_fill/browser_keyboard calls.\n\n"
            "Keys can be:\n"
            "- Visible label text (e.g., 'First Name', 'Straße')\n"
            "- CSS selectors starting with '#' (e.g., '#M0:46:1:1::0:21')\n\n"
            "When to use:\n"
            "- Filling a form with multiple input fields\n"
            "- All fields visible on current screen\n"
            "- No button clicks or navigation needed between fields\n\n"
            "When NOT to use:\n"
            "- Single field only (use browser_fill)\n"
            "- Fields on different screens/tabs\n"
            "- Need to click buttons between fills"
        )
    )
    async def sap_fill_form(fields: dict[str, str], strict: bool = False) -> FillFormResult:
        """
        Fill multiple SAP form fields in a single call.

        This is much faster than filling fields one by one, as it executes
        all fills in a single browser round-trip.

        Args:
            fields: Dictionary mapping field identifiers to values.
                    Keys can be visible label text (e.g., 'First Name')
                    or CSS selectors (e.g., '#M0:46:1:1::0:21').
            strict: If True, fail if any field is not found.
                    If False, skip missing fields and report them.

        Returns:
            FillFormResult with lists of filled, not_found, and errored fields.
        """
        if not fields:
            return FillFormResult.failure("fields cannot be empty")

        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Fast popup check (~5ms)
            popup = await _check_blocking_popup(page)
            if popup:
                return FillFormResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    blocking_popup=popup,
                )

            # Execute JavaScript to fill all fields
            result = await page.evaluate(
                _load_js("fill_form_fields.js"),
                {"fields": fields},
            )

            filled = result.get("filled", [])
            not_found = result.get("notFound", [])
            errors = [FieldFillError(field=e["field"], error=e["error"]) for e in result.get("errors", [])]

            # Log debug info if fields were not found
            debug_info = result.get("debug", [])
            if debug_info:
                logger.warning("sap_fill_form debug: %s", debug_info)

            # In strict mode, fail if any field was not found
            if strict and not_found:
                return FillFormResult.failure(
                    f"Fields not found: {', '.join(not_found)}",
                    filled=filled,
                    not_found=not_found,
                    errors=errors,
                )

            return FillFormResult(filled=filled, not_found=not_found, errors=errors)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error filling form fields")
            return FillFormResult.failure(f"Error filling form fields: {e}")

    @mcp.tool(
        description=(
            "Set a single SAP form field by label or CSS selector. "
            "Finds the field dynamically and fills it with the given value.\n\n"
            "The label parameter can be:\n"
            "- Visible label text (e.g., 'Last Name', 'Nachname')\n"
            "- CSS selector (e.g., '#M0:46:1:1::0:21', '[lsdata*=\"NAME_LAST\"]')\n\n"
            "This is simpler than sap_fill_form for single fields, and returns "
            "the CSS selector that was matched (useful for debugging)."
        )
    )
    async def sap_set_field(label: str, value: str) -> SetFieldResult:
        """
        Set a single SAP form field by label or CSS selector.

        This tool finds the field dynamically using label text or CSS selector,
        and returns information about what was matched. Useful for:
        - Single field updates
        - Debugging field discovery (returns the matched selector)

        Args:
            label: Field label text (e.g., 'Last Name') or CSS selector
            value: Value to set in the field

        Returns:
            SetFieldResult with label, value, and the CSS selector that was used.
        """
        if not label:
            return SetFieldResult.failure("label cannot be empty", label="", value=value)

        browser_manager = await get_browser_manager()

        try:
            page = await browser_manager.get_current_page()

            # Fast popup check (~5ms)
            popup = await _check_blocking_popup(page)
            if popup:
                return SetFieldResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    label=label,
                    value=value,
                    blocking_popup=popup,
                )

            # Execute JavaScript to set the field
            result = await page.evaluate(
                _load_js("set_field.js"),
                {"label": label, "value": value},
            )

            if not result.get("success", False):
                return SetFieldResult.failure(
                    result.get("error", "Unknown error"),
                    label=label,
                    value=value,
                )

            return SetFieldResult(
                label=label,
                value=value,
                selector_used=result.get("selectorUsed"),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error setting field")
            return SetFieldResult.failure(f"Error setting field: {e}", label=label, value=value)
