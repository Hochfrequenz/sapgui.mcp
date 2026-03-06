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
import time
from importlib import resources
from typing import Any, Optional
from urllib.parse import urlparse

from fastmcp import Context, FastMCP

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.backend.webgui.browser import BrowserManager, get_browser_manager
from sapwebguimcp.backend.webgui.js_helpers import load_js as _load_js
from sapwebguimcp.middleware.logging import set_sap_identity
from sapwebguimcp.models import (
    CapabilitiesResult,
    ClosePopupResult,
    DiscoveredButtons,
    DiscoveredFields,
    FieldLookupResult,
    FillFormResult,
    FormFieldsResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SessionBindResult,
    SessionCloseResult,
    SessionListResult,
    SessionReleaseResult,
    SessionStatus,
    SetFieldResult,
    ShortcutInfo,
    ShortcutsResult,
    StatusBarInfo,
    TableCellClickResult,
    TableData,
    ToolInfo,
    TransactionResult,
    get_settings,
)
from sapwebguimcp.models.middleware import SapIdentity
from sapwebguimcp.tools.session_tools import (
    sap_session_bind_impl,
    sap_session_close_impl,
    sap_session_list_impl,
    sap_session_release_impl,
)

__all__ = ["register_sap_tools", "SELECTORS", "parse_shortcut_from_title"]

logger = logging.getLogger(__name__)


async def _capture_sap_identity(
    page: Any,
    effective_url: str,
    mandant: str,
    session_id: str | None,
) -> None:
    """Extract SAP username from DOM and store identity for log correlation.

    Tries DOM extraction first. If it fails, logs a warning and leaves
    identity unset (no guessing from env vars).
    """
    hostname = urlparse(effective_url).hostname or "unknown"

    try:
        js = _load_js("extract_sap_user.js")
        result = await page.evaluate(js)
        sap_user = result.get("user") if result else None
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning(
            "DOM extraction failed for SAP username; identity not set",
            extra={"error": str(exc)},
        )
        return

    if sap_user:
        identity = SapIdentity(sap_user=sap_user, sap_host=hostname, sap_mandant=mandant)
        set_sap_identity(session_id, identity)
        logger.info("SAP identity captured", extra=identity.model_dump(mode="json"))
    else:
        logger.warning("SAP username not found in page DOM; identity not set for log correlation")


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
    logger.info("Keepalive task started", extra={"interval_s": interval})

    while True:
        try:
            await asyncio.sleep(interval)

            page = await browser_manager.get_current_page()

            if page.is_closed():
                logger.warning("Keepalive page closed, stopping")
                break

            # Perform a harmless action - evaluate JS to keep connection alive
            await page.evaluate("() => { /* keepalive ping */ }")

            logger.info("Keepalive ping sent successfully")

        except asyncio.CancelledError:
            logger.info("Keepalive task cancelled successfully")
            break
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Keepalive error, will retry", extra={"error": str(e)})


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


async def _wait_for_new_page(context: Any, pages_before: int, timeout_ms: int = 5000) -> bool:
    """
    Wait for a new browser page/tab to appear in the context.

    Args:
        context: The browser context
        pages_before: Number of pages before the action
        timeout_ms: Maximum time to wait in milliseconds

    Returns:
        True if a new page appeared, False if timeout was reached
    """
    poll_interval_s = 0.1
    timeout_s = timeout_ms / 1000
    start_time = time.monotonic()

    while len(context.pages) <= pages_before:
        elapsed = time.monotonic() - start_time
        if elapsed >= timeout_s:
            return False
        await asyncio.sleep(poll_interval_s)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    logger.debug("New browser tab detected", extra={"elapsed_ms": elapsed_ms})
    return True


async def _register_new_window_session(
    browser_manager: "BrowserManager",
    context: Any,
    pages_before: int,
    tcode: str | None = None,
    wait_timeout_ms: int = 5000,
) -> tuple[str | None, int, str | None]:
    """
    Wait for and register a new session created by new_window=True.

    Args:
        browser_manager: The browser manager instance
        context: The browser context
        pages_before: Number of pages before the transaction
        tcode: Transaction code (for logging context)
        wait_timeout_ms: Max time to wait for new page (default 5000ms)

    Returns:
        Tuple of (session_id, session_count, page_title):
        - session_id: The registered ID (e.g., "s2") or None if no new page was detected
        - session_count: Total number of pages in context
        - page_title: Title of the new page, or None if no new page
    """
    # Wait for the new browser tab to appear
    await _wait_for_new_page(context, pages_before, timeout_ms=wait_timeout_ms)

    pages = context.pages
    session_count = len(pages)
    new_session_id: str | None = None
    title: str | None = None

    if session_count > pages_before:
        # Assumption: The last page in the list is the newly created one.
        # SAP's synchronous UI behavior makes this reliable in practice.
        new_page = pages[-1]
        registry = browser_manager.registry
        new_session_id = registry.register(new_page)
        logger.info("Auto-registered new session from new_window=True", extra={"session": new_session_id})
        title = await new_page.title()
    else:
        logger.warning(
            "No new page detected after new_window=True (/o prefix)",
            extra={
                "tcode": tcode or "unknown",
                "wait_timeout_ms": wait_timeout_ms,
                "pages_before": pages_before,
                "pages_after": session_count,
            },
        )

    return new_session_id, session_count, title


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
        logger.exception("Enabling OK-Code field")
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

    @mcp.tool(
        description=(
            "Log into SAP Web GUI. "
            "REQUIRES: Chrome with --remote-debugging-port=9222, VPN connected (if internal SAP). "
            "If connection fails, ask user to verify Chrome is running with debugging and VPN is connected."
        )
    )
    async def sap_login(  # pylint: disable=too-many-return-statements,too-many-statements
        url: Optional[str] = None,
        ctx: Context | None = None,
    ) -> LoginResult:
        """
        Log into SAP Web GUI.

        Opens the SAP Web GUI URL and automatically logs in using credentials
        from environment variables (SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE).

        If credentials are not configured, opens the login page for manual entry.

        PREREQUISITES:
        - Chrome running with --remote-debugging-port=9222
        - VPN connected (if SAP system is on internal network)
        - CDP proxy running (for Docker setups)

        Args:
            url: SAP Web GUI URL. If not provided, uses SAP_URL from environment.

        Returns:
            LoginResult indicating login success or what action is needed.
        """
        browser_manager = await get_browser_manager()

        settings = get_settings()
        session_id = getattr(ctx, "session_id", None) if ctx else None

        page = await browser_manager.get_current_page()
        effective_url = url or settings.sap_url

        if not effective_url:
            return LoginResult.failure(
                "No SAP URL provided. Either pass a URL parameter or set the SAP_URL environment variable."
            )

        try:
            logger.info("Navigating to SAP Web GUI", extra={"sap_host": urlparse(effective_url).hostname or "unknown"})
            await page.goto(effective_url)
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Check if we're already logged in
            okcode_field = await _find_okcode_field(page)
            if okcode_field:
                # Start keepalive to prevent session timeout
                await _start_keepalive()
                # Register page as primary session (s1) if not already registered
                if not browser_manager.registry.has_session("s1"):
                    browser_manager.registry.register(page)
                await _capture_sap_identity(page, effective_url, settings.sap_mandant, session_id)
                return LoginResult(
                    url=effective_url,
                    already_logged_in=True,
                    guidance=(
                        "RECOMMENDED: Call sap_get_capabilities() to review all available "
                        "tools and their descriptions before proceeding."
                    ),
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
            logger.info("Performing automatic login", extra={"sap_user": settings.sap_user})

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
                logger.debug("Set language field", extra={"language": settings.sap_language})
            except Exception as lang_err:  # pylint: disable=broad-exception-caught
                logger.warning("Could not set language field", extra={"error": str(lang_err)})

            # Click login button (it's a div with role="button", not a button element)
            await page.click("#LOGON_BUTTON")

            # Wait for SAP Easy Access to load (OK-Code field appears after login)
            try:
                await page.wait_for_selector("#ToolbarOkCode", timeout=15000, state="visible")
                logger.info("Login successful, OK-Code field visible")
                # Start keepalive to prevent session timeout
                await _start_keepalive()
                # Register page as primary session (s1) if not already registered
                if not browser_manager.registry.has_session("s1"):
                    browser_manager.registry.register(page)
                await _capture_sap_identity(page, effective_url, settings.sap_mandant, session_id)
                return LoginResult(
                    url=effective_url,
                    user=settings.sap_user,
                    guidance=(
                        "RECOMMENDED: Call sap_get_capabilities() to review all available "
                        "tools and their descriptions before proceeding."
                    ),
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
                        # Register page as primary session (s1) if not already registered
                        if not browser_manager.registry.has_session("s1"):
                            browser_manager.registry.register(page)
                        await _capture_sap_identity(page, effective_url, settings.sap_mandant, session_id)
                        return LoginResult(
                            url=effective_url,
                            user=settings.sap_user,
                            already_logged_in=True,
                            guidance=(
                                "RECOMMENDED: Call sap_get_capabilities() to review all available "
                                "tools and their descriptions before proceeding."
                            ),
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

                return LoginResult.failure(
                    "Login attempted but SAP Easy Access not detected. "
                    "Please check browser window for errors or dialogs.",
                    url=effective_url,
                )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Logging in to SAP")
            return LoginResult.failure(f"Error during SAP login: {e}", url=effective_url)

    @mcp.tool(
        description=(
            "Enter and execute an SAP transaction code. "
            "IMPORTANT: Do NOT use this for SE11, SE16, SE24, SE37, or SE93 - "
            "use the dedicated sap_se11_lookup, sap_se16_query, sap_se24_lookup, "
            "sap_se37_lookup, or sap_se93_lookup tools instead, which are faster and return structured data.\n\n"
            "**Multi-Session Support (for parallel agents):**\n"
            "- `new_window=True`: Opens transaction in a NEW browser tab (SAP session)\n"
            "- Returns `session_count` showing total open sessions\n"
            "- Use `session` parameter on subsequent tool calls to target that session\n\n"
            "Example workflow for 5 parallel agents:\n"
            '1. `sap_transaction("BP", new_window=True)` → Creates session s2\n'
            "2. `sap_session_list()` → See all sessions with IDs\n"
            '3. `sap_fill_form({...}, session="s2")` → Target specific session\n\n'
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2", "s3", etc.: Targets specific session'
        )
    )
    async def sap_transaction(  # pylint: disable=too-many-return-statements,too-many-locals,too-many-branches
        tcode: str,
        new_window: bool = False,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TransactionResult:
        """
        Enter and execute an SAP transaction code.

        IMPORTANT: For the following transactions, use dedicated tools instead:
        - SE11 (Data Dictionary): Use sap_se11_lookup for structured table/structure metadata
        - SE16 (Data Browser): Use sap_se16_query for reading table data
        - SE24 (Class Builder): Use sap_se24_lookup for class/interface metadata
        - SE37 (Function Builder): Use sap_se37_lookup for function module signatures
        - SE93 (Transaction Maintenance): Use sap_se93_lookup for transaction metadata

        This tool will:
        1. Check if the OK-Code field is visible
        2. If not, attempt to enable it via Settings (gear icon -> enable OK-Code field)
        3. Enter the transaction code and execute it

        Transaction modes:
        - new_window=False (default): Opens transaction in current window, canceling any
          active transaction. Uses /n prefix (e.g., /nSE11).
        - new_window=True: Opens transaction in a NEW SAP session/window, preserving the
          current transaction. Uses /o prefix (e.g., /oSE11). This creates an additional
          SAP session. The new session is **auto-registered** and the session_id is
          returned in the result (e.g., "s2").

        Args:
            tcode: Transaction code (e.g., VA01, MM03, SE80, SU01)
            new_window: If True, open in new SAP session window (preserves current transaction).
                        The new session is auto-registered and session_id is returned.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransactionResult indicating success or describing any issues.
            When new_window=True, includes session_id of the new session.
        """
        # Need browser_manager for new_window session registry operations
        browser_manager = await get_browser_manager()

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_transaction")
        except ValueError as e:
            return TransactionResult.failure(str(e), tcode=tcode)

        page = backend._page  # type: ignore[attr-defined]  # pylint: disable=protected-access

        # Fast popup check (~5ms)
        popup = await backend.check_popup()
        if popup:
            return TransactionResult.failure(
                f"Popup blocking: {popup.message or 'confirmation required'}",
                tcode=tcode,
                popup=popup,
            )

        try:
            if not new_window:
                # For non-new_window: use backend.enter_transaction (handles OK-Code field)
                # Backend always uses /n prefix for non-prefixed tcodes
                result = await backend.enter_transaction(tcode)

                # Small wait to let popup render if it appeared
                await page.wait_for_timeout(200)

                # Check if a popup appeared after navigation
                popup = await backend.check_popup()
                if popup:
                    return TransactionResult.failure(
                        f"Popup blocking: {popup.message or 'confirmation required'}",
                        tcode=tcode,
                        popup=popup,
                    )

                return result

            # new_window=True: need manual OK-Code handling with /o prefix
            okcode_field = await _find_okcode_field(page)

            if not okcode_field:
                logger.info("OK-Code field not found, attempting to enable")
                success, message = await _enable_okcode_field(page)
                logger.info("Enable OK-Code result", extra={"success": success, "result_message": message})

                if not success:
                    return TransactionResult.failure(
                        f"Could not find or enable OK-Code field. {message} "
                        "Possible causes: (1) A popup/dialog may be blocking the screen - "
                        "close any open dialogs first. (2) The OK-Code field may need to be "
                        "enabled manually: Menu -> Settings -> Enable 'OK-Code Field' or "
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

            # Build transaction input with /o prefix
            if tcode.startswith("/n") or tcode.startswith("/o"):
                transaction_input = tcode
            else:
                transaction_input = f"/o{tcode}"

            # Track page count before transaction (for new_window detection)
            context = page.context
            pages_before = len(context.pages)

            await page.bring_to_front()
            await page.wait_for_timeout(500)

            logger.info("Entering transaction", extra={"tcode": transaction_input})

            await okcode_field.click()
            await page.wait_for_timeout(200)

            await page.evaluate(
                _load_js("set_okcode_field.js"),
                {"transactionInput": transaction_input},
            )

            await page.wait_for_timeout(300)
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("networkidle", timeout=15000)
            await page.wait_for_timeout(200)

            # Check if a popup appeared after navigation
            popup = await backend.check_popup()
            if popup:
                return TransactionResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    tcode=tcode,
                    popup=popup,
                )

            title = await page.title()

            # Detect and register new session created by /o command
            new_session_id, session_count, new_title = await _register_new_window_session(
                browser_manager, context, pages_before, tcode=tcode
            )
            if new_session_id is None:
                return TransactionResult.failure(
                    f"new_window=True but no new session was created for {tcode}. "
                    "Possible causes: SAP session limit reached, popup blocking, or network delay.",
                    tcode=tcode,
                    new_window=True,
                    session_count=session_count,
                )
            return TransactionResult(
                tcode=tcode,
                page_title=new_title or title,
                new_window=True,
                session_id=new_session_id,
                session_count=session_count,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Executing transaction", extra={"tcode": tcode})
            return TransactionResult.failure(f"Error executing transaction {tcode}: {e}", tcode=tcode)

    @mcp.tool(description="Check the current SAP session status")
    async def sap_session_status(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SessionStatus:
        """
        Check the current SAP session status.

        Useful to verify the session is still active before performing actions,
        especially after long pauses or agent questions.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SessionStatus with status one of:
            - "active": Session is alive and responsive
            - "timed_out": Session has timed out
            - "logged_off": User has been logged off
            - "no_page": No browser page available
            - "unknown": Cannot determine status
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_session_status")
        except ValueError as e:
            return SessionStatus(status="unknown", message=f"Session error: {e}")

        try:
            return await backend.get_session_status()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Checking session status")
            return SessionStatus(status="unknown", message=f"Error checking status: {e}")

    @mcp.tool(
        description=(
            "RECOMMENDED: Call at the start of every SAP session. "
            "Returns all available tools with their full descriptions. "
            "Reading this first helps you understand what capabilities are available, "
            "work faster, and avoid common mistakes like clicking buttons when keyboard "
            "shortcuts are available."
        )
    )
    async def sap_get_capabilities() -> CapabilitiesResult:  # pylint: disable=missing-function-docstring
        # Introspect MCP registry to get all registered tools
        try:
            registered = await mcp.list_tools()
            tools = sorted(
                [ToolInfo(name=t.name, description=t.description or "") for t in registered],
                key=lambda t: t.name,
            )

            # Load SAP knowledge from markdown file
            sap_knowledge = None
            try:
                knowledge_file = resources.files("sapwebguimcp.data").joinpath("sap_knowledge.md")
                sap_knowledge = knowledge_file.read_text(encoding="utf-8")
            except Exception as knowledge_err:  # pylint: disable=broad-exception-caught
                logger.warning("Could not load SAP knowledge file", extra={"error": str(knowledge_err)})

            return CapabilitiesResult(tools=tools, sap_knowledge=sap_knowledge)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting capabilities")
            return CapabilitiesResult.failure(f"Error getting capabilities: {e}")

    @mcp.tool(
        description=(
            "Send a keyboard shortcut to SAP Web GUI\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_keyboard(  # pylint: disable=too-many-return-statements
        key: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> KeyboardResult:
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
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            KeyboardResult with the key sent, page title, and status bar (for shortcuts).
            Status bar is auto-read for F-keys and Ctrl+* since SAP often shows feedback there.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_keyboard")
        except ValueError as e:
            return KeyboardResult.failure(str(e), key=key)

        try:
            # Fast popup check (~5ms) - only blocks if popup exists BEFORE keystroke
            popup = await backend.check_popup()
            if popup:
                logger.debug("Popup already present before keystroke", extra={"key": key})
                return KeyboardResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    key=key,
                    popup=popup,
                )

            # Send the keystroke (backend handles bring_to_front, networkidle, status bar)
            result = await backend.press_key(key)

            # Wait for popup to render (SAP popups may appear after networkidle)
            page = backend._page  # type: ignore[attr-defined]  # pylint: disable=protected-access
            await page.wait_for_timeout(300)

            # Check if a popup appeared after the keystroke
            popup_after = await backend.check_popup()
            if popup_after:
                logger.debug("Popup appeared after keystroke", extra={"key": key})
                return KeyboardResult.failure(
                    f"Popup blocking: {popup_after.message or 'confirmation required'}",
                    key=key,
                    popup=popup_after,
                )

            return result

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Sending keyboard shortcut", extra={"key": key})
            return KeyboardResult.failure(f"Error sending keyboard shortcut {key}: {e}", key=key)

    @mcp.tool(
        description=(
            "Get all readable text from the current SAP screen. "
            "Use include_dropdown_options=True to also fetch available options for dropdown fields.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_get_screen_text(
        include_dropdown_options: bool = False,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ScreenText:
        """
        Get all readable text from the current SAP screen.

        This tool extracts text content for adaptive field discovery.
        Use it to identify field labels, button texts, and screen content
        when you need to work with screens that vary by system configuration.

        Args:
            include_dropdown_options: If True, opens each dropdown to capture available
                options. This is slower but provides complete information for dropdowns.
                Default is False.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ScreenText with structured content including:
            - Screen title
            - Field labels and values
            - Button labels
            - Tab labels
            - Status messages
            - Table headers
            - Dropdowns with options (when include_dropdown_options=True)
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_get_screen_text")
        except ValueError as e:
            return ScreenText.failure(str(e), title="")

        try:
            return await backend.get_screen_text(include_dropdown_options=include_dropdown_options)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting screen text")
            return ScreenText.failure(f"Error getting screen text: {e}", title="")

    @mcp.tool(
        description=(
            "Discover fillable form fields on the current SAP screen. "
            "Returns field IDs, labels, types (text/dropdown/checkbox/radio), and current values. "
            "Use include_dropdown_options=True to also fetch available options for dropdown fields.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_get_form_fields(
        include_dropdown_options: bool = False,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> FormFieldsResult:
        """
        Discover all fillable form fields on the current SAP screen.

        This tool scans the screen for input fields and categorizes them by type.
        Use it to understand what fields are available before filling a form.

        Args:
            include_dropdown_options: If True, opens each dropdown to capture available
                options. This is slower but provides complete information for dropdowns.
                Default is False (lazy fetching).
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            FormFieldsResult with list of FormField objects containing:
            - id: Element ID for targeting
            - label: Visible label text
            - field_type: text, dropdown, checkbox, or radio
            - current_value: Current field value (if any)
            - readonly: Whether field is editable
            - options: Available options (dropdowns only, when include_dropdown_options=True)
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_get_form_fields")
        except ValueError as e:
            return FormFieldsResult.failure(str(e))

        try:
            return await backend.get_form_fields(include_dropdown_options=include_dropdown_options)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting form fields")
            return FormFieldsResult.failure(f"Error getting form fields: {e}")

    @mcp.tool(
        description=(
            "Read data from an ALV grid or table on the current screen\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_read_table(
        start_row: int = 1,
        end_row: Optional[int] = None,
        max_rows: int = 100,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> TableData:
        """
        Read rows from an ALV grid or table on the current screen.

        Works with SAP ALV grids, step loops, and list displays.

        Args:
            start_row: First row to read (1-indexed, default: 1)
            end_row: Last row to read (None = up to max_rows visible rows)
            max_rows: Maximum rows to return (default: 100, prevents huge responses)
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TableData with column headers and row values.
            Empty columns are excluded to reduce response size.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_read_table")
        except ValueError as e:
            return TableData.failure(str(e))

        try:
            return await backend.read_table(start_row=start_row, end_row=end_row, max_rows=max_rows)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Reading table")
            return TableData.failure(f"Error reading table: {e}")

    @mcp.tool(
        description=(
            "Click a cell in an ALV grid table. "
            "Automatically targets the correct clickable element (hotspot span vs TD). "
            "Use after sap_read_table to navigate to detail views.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_click_table_cell(
        row: int,
        column: int | str,
        action: str = "click",
        session: str | None = None,
        agent_id: str | None = None,
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
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TableCellClickResult with the selector used and page title after click.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_click_table_cell")
        except ValueError as e:
            return TableCellClickResult.failure(
                str(e),
                row=row,
                column=column,
                selector_used="",
            )

        try:
            return await backend.click_table_cell(row, column, action)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Clicking table cell", extra={"row": row, "column": column})
            return TableCellClickResult.failure(
                f"Error clicking table cell: {e}",
                row=row,
                column=column,
                selector_used="",
            )

    @mcp.tool(
        description=(
            "Read the current message from SAP's status bar\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_read_status_bar(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> StatusBarInfo:
        """
        Read the current message from SAP's status bar.

        SAP displays success, error, warning, and info messages in the status bar.
        Whenever you're stuck, maybe check the status bar for hints what to do.
        This tool extracts that message for programmatic checking.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            StatusBarInfo with:
            - type: "S" (success), "E" (error), "W" (warning), "I" (info), or "none"
            - message: The status bar text
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_read_status_bar")
        except ValueError as e:
            return StatusBarInfo.failure(str(e), type="none")

        try:
            return await backend.get_status_bar()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Reading status bar")
            return StatusBarInfo.failure(f"Error reading status bar: {e}", type="none")

    @mcp.tool(
        description=(
            "Get technical information about the current SAP screen\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_get_screen_info(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ScreenInfo:
        """
        Get technical information about the current SAP screen.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ScreenInfo with:
            - transaction: Current transaction code (if detectable)
            - title: Window/page title
            - url: Current URL
            - program: ABAP program name (if available in page)
            - dynpro: Screen number (if available)
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_get_screen_info")
        except ValueError as e:
            return ScreenInfo.failure(str(e), title="", url="")

        try:
            # Check for blocking popup
            popup = await backend.check_popup()

            # Get screen info via backend
            screen_info = await backend.get_screen_info()
            screen_info.popup = popup
            return screen_info

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting screen info")
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
            logger.exception("Looking up fields", extra={"transaction": tcode_upper})
            return FieldLookupResult.failure(f"Error looking up fields: {e}", transaction=tcode_upper)

    @mcp.tool(
        description=(
            "Discover input fields on the current SAP screen. "
            "Returns fields with reliable CSS selectors (use the 'selector' field). "
            "For buttons, use sap_discover_buttons instead.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_discover_fields(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> DiscoveredFields:
        """
        Discover all input fields on the current SAP screen.

        This tool analyzes the current page and returns information about
        all visible input fields with reliable CSS selectors.

        IMPORTANT: Use the 'selector' field directly with sap_fill_form or
        sap_set_field - it is designed to work reliably. Avoid using raw
        element IDs which may contain special characters.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            DiscoveredFields with list of fields including:
            - field_id: SAP field ID (e.g., 'NAME_FIRST', 'STREET')
            - label: Associated label text (for display)
            - selector: Reliable CSS selector to use with sap_fill_form
            - alternative_selectors: Other valid selectors (fallbacks)
            - type: Input type (text, checkbox, etc.)
            - value: Current value (if any)
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_discover_fields")
        except ValueError as e:
            return DiscoveredFields.failure(str(e), field_count=0)

        try:
            fields = await backend.discover_fields()
            return DiscoveredFields(
                field_count=len(fields),
                fields=fields,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Discovering fields")
            return DiscoveredFields.failure(f"Error discovering fields: {e}", field_count=0)

    @mcp.tool(
        description=(
            "Discover clickable buttons on the current SAP screen. "
            "Returns buttons with label, selector (for browser_click), shortcut (e.g. F3), and accesskey. "
            "Use the 'selector' field with browser_click to click buttons reliably. "
            "Prefer keyboard shortcuts when available - they're faster. "
            "For input fields use sap_discover_fields instead.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_discover_buttons(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> DiscoveredButtons:
        """Discover all clickable buttons on the current SAP screen.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_discover_buttons")
        except ValueError as e:
            return DiscoveredButtons.failure(str(e), button_count=0)

        try:
            buttons = await backend.discover_buttons()
            return DiscoveredButtons(
                button_count=len(buttons),
                buttons=buttons,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Discovering buttons")
            return DiscoveredButtons.failure(f"Error discovering buttons: {e}", button_count=0)

    @mcp.tool(
        description=(
            "Discover keyboard shortcuts available on the current SAP screen. "
            "Use BEFORE clicking buttons - shortcuts like F5, Strg+S are faster and more reliable. "
            "Returns action text and key combination for each available shortcut.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_get_shortcuts(
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ShortcutsResult:
        """
        Discover keyboard shortcuts available on the current SAP screen.

        SAP buttons often have keyboard shortcuts that are faster and more reliable
        than clicking. This tool finds all available shortcuts by analyzing button
        titles like "Person anlegen (F5)" or "Speichern (Strg+S)".

        Use this tool to discover shortcuts BEFORE attempting button clicks.
        Then use sap_keyboard to execute the shortcut.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ShortcutsResult with list of ShortcutInfo objects containing:
            - action: Button/action text (e.g., "Person anlegen")
            - shortcut: Key combination (e.g., "F5", "Strg+S")
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_get_shortcuts")
        except ValueError as e:
            return ShortcutsResult.failure(str(e))

        try:
            # Get all title attributes via JavaScript - much more efficient than parsing HTML
            page = backend._page  # type: ignore[attr-defined]  # pylint: disable=protected-access
            titles: list[str] = await page.evaluate("""() => {
                    const elements = document.querySelectorAll('[title]');
                    return Array.from(elements).map(el => el.title);
                }""")

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
            logger.exception("Getting shortcuts")
            return ShortcutsResult.failure(f"Error getting shortcuts: {e}")

    @mcp.tool(
        description=(
            "Close an active popup dialog by clicking a button. "
            "Use after a tool returns popup info. "
            "Note: Not all popups are errors - F4 help dialogs are expected behavior. "
            "For F4 help popups, consider reading the values first before closing. "
            "Specify button by label ('Ja', 'Nein') or accesskey ('J', 'N'), "
            "or use close=True to click the X button if available.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_close_popup(  # pylint: disable=too-many-branches,too-many-return-statements
        button: Optional[str] = None,
        close: bool = False,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> ClosePopupResult:
        """
        Close an active popup dialog.

        Args:
            button: Button label (e.g., 'Ja', 'Nein') or accesskey (e.g., 'J', 'N')
            close: Click the X close button instead of a specific button
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            ClosePopupResult with success status and button clicked
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_close_popup")
        except ValueError as e:
            return ClosePopupResult.failure(str(e))

        try:
            return await backend.dismiss_popup(button_label=button, use_close_button=close)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Dismissing popup")
            return ClosePopupResult.failure(f"Error dismissing popup: {e}")

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
            "- Need to click buttons between fills\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_fill_form(
        fields: dict[str, str],
        strict: bool = False,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> FillFormResult:
        """
        Fill multiple SAP form fields in a single call.

        This is much faster than filling fields one by one, as it executes
        all fills in a single browser round-trip.

        Dropdown fields (ComboBox) are automatically detected and handled:
        the dropdown is opened, the matching option is selected. If the
        requested value is not found, an error is returned with all
        available options.

        Args:
            fields: Dictionary mapping field identifiers to values.
                    Keys can be visible label text (e.g., 'First Name')
                    or CSS selectors (e.g., '#M0:46:1:1::0:21').
            strict: If True, fail if any field is not found.
                    If False, skip missing fields and report them.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            FillFormResult with lists of filled, not_found, and errored fields.
            If a popup appears after filling (e.g., role change confirmation),
            it's returned in popup.
        """
        if not fields:
            return FillFormResult.failure("fields cannot be empty")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_fill_form")
        except ValueError as e:
            return FillFormResult.failure(str(e))

        try:
            # Fast popup check (~5ms)
            popup = await backend.check_popup()
            if popup:
                return FillFormResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    popup=popup,
                )

            result = await backend.fill_form(fields)

            # In strict mode, fail if any field was not found
            if strict and result.not_found:
                return FillFormResult.failure(
                    f"Fields not found: {', '.join(result.not_found)}",
                    filled=result.filled,
                    not_found=result.not_found,
                    errors=result.errors,
                    popup=result.popup,
                )

            return result

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Filling form fields")
            return FillFormResult.failure(f"Error filling form fields: {e}")

    @mcp.tool(
        description=(
            "Set a single SAP form field by label or CSS selector. "
            "Finds the field dynamically and fills it with the given value.\n\n"
            "The label parameter can be:\n"
            "- Visible label text (e.g., 'Last Name', 'Nachname')\n"
            "- CSS selector (e.g., '#M0:46:1:1::0:21', '[lsdata*=\"NAME_LAST\"]')\n\n"
            "This is simpler than sap_fill_form for single fields, and returns "
            "the CSS selector that was matched (useful for debugging).\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session (for parallel agents)'
        )
    )
    async def sap_set_field(  # pylint: disable=too-many-return-statements
        label: str,
        value: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SetFieldResult:
        """
        Set a single SAP form field by label or CSS selector.

        This tool finds the field dynamically using label text or CSS selector,
        and returns information about what was matched. Supports both regular
        text inputs and dropdown/combobox fields.

        For dropdown fields, the tool automatically detects the field type and
        uses the appropriate selection mechanism. If the requested value is not
        in the dropdown options, returns available_options listing valid choices.

        Args:
            label: Field label text (e.g., 'Last Name', 'GP-Rolle') or CSS selector
            value: Value to set in the field (for dropdowns: exact option text)
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SetFieldResult with label, value, and the CSS selector that was used.
            For dropdown errors, includes available_options.
        """
        if not label:
            return SetFieldResult.failure("label cannot be empty", label="", value=value)

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_set_field")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value=value)

        try:
            # Fast popup check (~5ms)
            popup = await backend.check_popup()
            if popup:
                return SetFieldResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    label=label,
                    value=value,
                    popup=popup,
                )

            await backend.fill_field(label, value)
            # selector_used is unavailable via the backend protocol (fill_field returns None)
            return SetFieldResult(label=label, value=value)

        except ValueError as ve:
            return SetFieldResult.failure(str(ve), label=label, value=value)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Setting field", extra={"label": label})
            return SetFieldResult.failure(f"Error setting field: {e}", label=label, value=value)

    # =========================================================================
    # Session Management Tools
    # =========================================================================

    @mcp.tool(description="""List all active SAP sessions.

Returns session IDs, current transaction, and screen title for each.
Use this to see what sessions exist before targeting one.

Primary session ("s1") is created on sap_login().
Additional sessions created via sap_transaction(tcode, new_window=True).
""")
    async def sap_session_list() -> SessionListResult:
        """List all active sessions."""
        return await sap_session_list_impl()

    @mcp.tool(description="""Close a SAP session.

Closes the browser tab and removes the session from the registry.
Cannot close primary session ("s1") - use sap_login() to start fresh.

Args:
    session_id: Session to close (e.g., "s2")
""")
    async def sap_session_close(session_id: str) -> SessionCloseResult:
        """Close a specific session."""
        return await sap_session_close_impl(session_id)

    @mcp.tool(
        description=(
            "Bind a session to an agent for parallel workflow management. "
            "When bound, other agents using this session trigger warnings. "
            "Use for transfer of session ownership between agents."
        )
    )
    async def sap_session_bind(session_id: str, agent_id: str) -> SessionBindResult:
        """Bind or rebind a session to an agent.

        Args:
            session_id: Session ID to bind (e.g., "s2")
            agent_id: Agent identifier claiming the session

        Returns:
            SessionBindResult with binding info
        """
        return await sap_session_bind_impl(session_id, agent_id)

    @mcp.tool(
        description=(
            "Release agent binding from a session. "
            "Use when an agent finishes work and wants to free the session "
            "for other agents or general use."
        )
    )
    async def sap_session_release(session_id: str) -> SessionReleaseResult:
        """Unbind a session from its current agent.

        Args:
            session_id: Session ID to release

        Returns:
            SessionReleaseResult
        """
        return await sap_session_release_impl(session_id)
