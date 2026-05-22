# pylint: disable=too-many-lines
"""WebGUI backend implementation using Playwright/CDP.

Each ``WebGuiBackend`` instance wraps a single Playwright ``Page``
(one SAP session).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError

from sapguimcp.backend.webgui.browser import get_browser_manager
from sapguimcp.backend.webgui.js_helpers import load_js, load_js_with_field_utils
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.backend.webgui.utils import escape_css_selector, is_sap_shortcut
from sapguimcp.middleware.logging import set_sap_identity
from sapguimcp.models.alv_models import AlvCellInfo, AlvMetadata, TableCellClickResult
from sapguimcp.models.base import CheckActivateResult, PopupButton, PopupInfo
from sapguimcp.models.middleware import SapIdentity
from sapguimcp.models.sap_results import (
    ButtonInfo,
    ClosePopupResult,
    DropdownFillResult,
    DropdownInfo,
    FieldFillError,
    FieldInfo,
    FillFormResult,
    FormField,
    FormFieldsResult,
    KeyboardResult,
    LoginResult,
    SapFieldType,
    ScreenInfo,
    ScreenText,
    SessionInfo,
    SessionStatus,
    StatusBarInfo,
    TableData,
    TableRow,
    TransactionResult,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

    from sapguimcp.backend.webgui.models.session_registry import SessionRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers private to WebGuiBackend
# ---------------------------------------------------------------------------

# Success/error prefixes used in SAP toolbar notes.
_SUCCESS_PREFIXES = ("Erfolgreich ", "Success ")
_ERROR_PREFIXES = ("Fehler ", "Error ")
_PREFIX_STRIP = re.compile(
    r"^(Erfolgreich|Success|Fehler|Error)\s+(Meldungsleiste|Message Bar)\s+",
)
_SUCCESS_PATTERNS = re.compile(
    r"keine Syntaxfehler|No syntax errors|"
    r"Aktives Objekt wurde generiert|Objekt wurde aktiviert|Object activated|"
    r"generated successfully",
    re.IGNORECASE,
)
_ERROR_PATTERNS = re.compile(
    r"Syntaxfehler|syntax error",
    re.IGNORECASE,
)


def _parse_toolbar_note(snapshot_text: str) -> tuple[bool, str]:
    """Parse toolbar note from an ARIA snapshot to determine success/failure."""
    match = re.search(r'note\s+"([^"]+)"', snapshot_text)
    if not match:
        return False, "No status message found in toolbar"

    full_note = match.group(1)
    message = _PREFIX_STRIP.sub("", full_note).strip() or full_note

    if full_note.startswith(_SUCCESS_PREFIXES):
        return True, message
    if full_note.startswith(_ERROR_PREFIXES):
        return False, message

    if _SUCCESS_PATTERNS.search(full_note):
        return True, message
    if _ERROR_PATTERNS.search(full_note):
        return False, message
    return False, message


# ---------------------------------------------------------------------------
# WebGuiBackend
# ---------------------------------------------------------------------------


class WebGuiBackend:  # pylint: disable=too-many-public-methods
    """WebGUI backend using Playwright browser automation.

    Each instance wraps a single Playwright ``Page`` (one SAP session).
    """

    _TX_MAX_RETRIES: int = 3
    """Max retries for ``enter_transaction`` when Enter is not processed."""

    def __init__(self, page: Page) -> None:
        self._page = page
        self._keepalive_task: asyncio.Task[None] | None = None

    @property
    def backend_type(self) -> str:
        """Return backend identifier."""
        return "webgui"

    def load_js(self, filename: str) -> str:
        """Load a bundled JavaScript helper file by name and return its source text."""
        return load_js(filename)

    # ---- private helpers ----

    async def _find_okcode_field(self, page: Any | None = None) -> Any | None:
        """Find the OK-Code field on the (given or current) page.

        Returns a Playwright Locator (lazy, re-evaluates on each action) instead
        of an ElementHandle to avoid stale DOM references when tests run
        back-to-back and the page is mid-rebuild.

        Args:
            page: Optional explicit Playwright Page. If ``None``, defaults to
                ``self._page`` (the backend's primary page). Used by
                ``get_session_status(session_id=...)`` to probe a specific
                session's page from the registry without mutating
                ``self._page``.
        """
        target = page if page is not None else self._page
        for selector in [
            "#ToolbarOkCode",
            "input[id*='OkCode']",
            "input[lsdata*='OKCODE']",
            "#M0\\:46\\:11\\:1",
        ]:
            loc = target.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return loc
        return None

    async def _enable_okcode_field(self) -> tuple[bool, str]:
        """Attempt to enable the OK-Code field via SAP settings menu."""
        try:
            settings_selectors = [
                "span[title*='Einstellungen']",
                "span[title*='Settings']",
                "[lsdata*='SETTINGS']",
                "span.urBtnEmph[title]",
            ]
            for selector in settings_selectors:
                element = await self._page.query_selector(selector)
                if element and await element.is_visible():
                    await element.click()
                    await self._page.wait_for_timeout(500)
                    for option_selector in [
                        "text=OK-Code",
                        "text=Transaktionsfeld",
                        "text=Transaction Field",
                    ]:
                        option = await self._page.query_selector(option_selector)
                        if option and await option.is_visible():
                            await option.click()
                            await self._page.wait_for_timeout(300)
                            return True, "Enabled OK-Code field via settings menu"
            return False, "Could not find settings menu or OK-Code option"
        except Exception as e:  # pylint: disable=broad-exception-caught
            return False, f"Error enabling OK-Code field: {e}"

    async def dismiss_language_dialog(self) -> None:
        """Handle SAP's 'Different original and logon languages' popup."""
        snap = await self._page.locator("body").aria_snapshot()
        if "Different original and logon languages" not in snap and "Originalsprache und Anmeldesprache" not in snap:
            return
        logger.info("Detected language mismatch dialog, confirming maintenance in original language")
        maint_btn = self._page.get_by_role("button", name="Maint. in orig. lang.")
        if not await maint_btn.is_visible(timeout=2000):
            maint_btn = self._page.get_by_role("button", name="Pflege in Originalsprache")
        if await maint_btn.is_visible(timeout=2000):
            await maint_btn.click()
            await self._page.wait_for_timeout(1000)
            await self._page.wait_for_load_state("networkidle")
        else:
            logger.warning("Language dialog detected but maintenance button not found")

    # ===================================================================
    # SapNavigation
    # ===================================================================

    async def _capture_sap_identity(
        self,
        effective_url: str,
        mandant: str,
        session_id: str | None,
    ) -> None:
        """Extract SAP username from DOM and store identity for log correlation."""
        hostname = urlparse(effective_url).hostname or "unknown"

        try:
            js = load_js("extract_sap_user.js")
            result = await self._page.evaluate(js)
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

    async def _post_login_setup(
        self,
        effective_url: str,
        mandant: str,
        session_id: str | None,
    ) -> None:
        """Register session and capture identity after a successful login."""
        registry = await self._get_registry()
        if not registry.has_session("s1"):
            registry.register(self._page)
        await self._capture_sap_identity(effective_url, mandant, session_id)

    async def login(  # pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument
        self,
        url: str,
        username: str,
        password: str,
        client: str,
        language: str,
        session_id: str | None = None,
        connection_name: str | None = None,  # ignored for WebGUI; SAP_URL is the system selector
    ) -> LoginResult:
        """Navigate to SAP WebGUI and log in.

        After successful login (any path), registers the page in the session
        registry and captures SAP identity for log correlation.
        """
        guidance_msg = (
            "RECOMMENDED: Call sap_get_capabilities() to review all available "
            "tools and their descriptions before proceeding."
        )
        try:
            logger.info(
                "Navigating to SAP Web GUI",
                extra={"sap_host": urlparse(url).hostname or "unknown"},
            )
            await self._page.goto(url)
            await self._page.wait_for_load_state("networkidle", timeout=15000)

            # Already logged in?
            okcode_field = await self._find_okcode_field()
            if okcode_field:
                await self._post_login_setup(url, client, session_id)
                return LoginResult(url=url, already_logged_in=True, guidance=guidance_msg)

            # Check for login form
            login_form = await self._page.query_selector('input[type="password"], input[id*="user" i]')
            if not login_form:
                return LoginResult.failure(
                    f"Navigated to {url}. No login form detected - please check browser window.",
                    url=url,
                )

            # Wait for all login fields to be ready before filling.
            # On first load the fields may appear in the DOM before they are
            # interactable, causing fill() to silently miss a field (#468).
            for field_selector in (
                '#sap-client, input[name="sap-client"]',
                '#sap-user, input[name="sap-user"]',
                '#sap-password, input[name="sap-password"]',
            ):
                await self._page.wait_for_selector(field_selector, state="visible", timeout=10000)

            # Fill credentials
            logger.info("Performing automatic login", extra={"sap_user": username})
            await self._page.fill('#sap-client, input[name="sap-client"]', client)
            await self._page.fill('#sap-user, input[name="sap-user"]', username)
            await self._page.fill('#sap-password, input[name="sap-password"]', password)

            try:
                await self._page.evaluate(
                    load_js("set_language_field.js"),
                    {"language": language},
                )
                logger.debug("Set language field", extra={"language": language})
            except Exception as lang_err:  # pylint: disable=broad-exception-caught
                logger.warning("Could not set language field", extra={"error": str(lang_err)})

            await self._page.click("#LOGON_BUTTON")

            try:
                await self._page.wait_for_selector("#ToolbarOkCode", timeout=15000, state="visible")
                logger.info("Login successful, OK-Code field visible")
                await self._post_login_setup(url, client, session_id)
                return LoginResult(url=url, user=username, guidance=guidance_msg)
            except Exception:  # pylint: disable=broad-exception-caught
                page_content = await self._page.content()
                if "already logged" in page_content.lower() or "bereits angemeldet" in page_content.lower():
                    try:
                        await self._page.click(
                            'button:has-text("Continue"), '
                            'button:has-text("Weiter"), '
                            'button:has-text("Fortfahren")',
                            timeout=5000,
                        )
                        await self._page.wait_for_selector("#ToolbarOkCode", timeout=10000, state="visible")
                        await self._post_login_setup(url, client, session_id)
                        return LoginResult(url=url, user=username, already_logged_in=True, guidance=guidance_msg)
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass
                return LoginResult.failure(
                    "Login attempted but SAP Easy Access not detected. "
                    "Please check browser window for errors or dialogs.",
                    url=url,
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Logging in to SAP")
            return LoginResult.failure(f"Error during SAP login: {e}", url=url)

    async def list_connections(self) -> list[Any]:
        """WebGUI backend has no SAP Logon entries."""
        return []

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        """Enter a transaction code via the OK-Code field.

        Supports parameterised transactions (e.g. ``/NZ_ABAPGIT_PULL_MCP P_REPO=...``).
        The ``TransactionResult.tcode`` field stores only the base tcode
        (first token before any parameters).

        Verifies that navigation actually happened after pressing Enter and
        retries up to ``_TX_MAX_RETRIES`` times if the OK-code field still
        contains the unsubmitted transaction code (race condition where
        ``keyboard.press("Enter")`` fires before SAP processes the field value).
        """
        # TransactionResult.tcode validates against a strict pattern;
        # extract the base tcode (first token) for the result model.
        base_tcode = tcode.split()[0] if " " in tcode else tcode
        if base_tcode.startswith("/n") or base_tcode.startswith("/o"):
            stripped = base_tcode[2:]
            if stripped:
                base_tcode = stripped
            # else: bare navigation command (/n or /o alone) — keep as-is
        try:
            if tcode.startswith("/n") or tcode.startswith("/o"):
                transaction_input = tcode
            else:
                transaction_input = f"/n{tcode}"

            for attempt in range(1, self._TX_MAX_RETRIES + 1):
                # Re-find the OK-code field on every attempt to avoid stale
                # DOM references after page transitions.
                okcode_field = await self._find_okcode_field()
                if not okcode_field:
                    success, message = await self._enable_okcode_field()
                    if not success:
                        return TransactionResult.failure(
                            f"Could not find or enable OK-Code field. {message}",
                            tcode=base_tcode,
                        )
                    okcode_field = await self._find_okcode_field()
                    if not okcode_field:
                        return TransactionResult.failure(
                            "OK-Code field still not visible after enabling.",
                            tcode=base_tcode,
                        )

                await self._page.bring_to_front()
                await self._page.wait_for_timeout(500)

                # Capture page title before navigation to detect change.
                title_before = await self._page.title()

                await okcode_field.click()
                await self._page.wait_for_timeout(200)
                await self._page.evaluate(
                    load_js("set_okcode_field.js"),
                    {"transactionInput": transaction_input},
                )
                await self._page.wait_for_timeout(300)
                await self._page.keyboard.press("Enter")

                try:
                    await self._page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("networkidle timeout on attempt %d", attempt)

                # Verify navigation actually happened by checking that either
                # the page title changed or the OK-code field was cleared.
                navigated = await self._verify_transaction_submitted(transaction_input, title_before)
                if navigated:
                    title = await self._poll_title_change(title_before)
                    if attempt > 1:
                        logger.info(
                            "enter_transaction succeeded on attempt %d",
                            attempt,
                            extra={"tcode": tcode},
                        )
                    return TransactionResult(tcode=base_tcode, page_title=title)

                logger.warning(
                    "enter_transaction: Enter not processed (attempt %d/%d)",
                    attempt,
                    self._TX_MAX_RETRIES,
                    extra={"tcode": tcode},
                )

            return TransactionResult.failure(
                f"Navigation to {tcode} failed after {self._TX_MAX_RETRIES} attempts "
                "(Enter keypress not processed by SAP)",
                tcode=base_tcode,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Executing transaction")
            return TransactionResult.failure(f"Error executing transaction {tcode}: {e}", tcode=base_tcode)

    async def _verify_transaction_submitted(self, transaction_input: str, title_before: str) -> bool:
        """Return True if the transaction navigation actually happened.

        Checks two signals:
        1. The page title changed (SAP updates the title on navigation).
        2. The OK-code field no longer holds the transaction string we typed.

        Navigation is considered successful if *either* signal fires:
        - Title changed → definitive navigation.
        - Field cleared → SAP processed the Enter (even if the title stays
          the same, e.g. ``/nSE24`` from within SE24).
        """
        try:
            title_after = await self._page.title()
            if title_after != title_before:
                return True

            ok_field = await self._page.query_selector("#ToolbarOkCode")
            if not ok_field:
                return True
            current_value = await ok_field.get_attribute("value") or ""
            field_has_our_value = current_value.strip().upper() == transaction_input.strip().upper()

            # If the field still holds our exact transaction string, Enter
            # was not processed — need to retry.
            return not field_has_our_value

        except Exception:  # pylint: disable=broad-exception-caught
            # Element detached / page navigated → success.
            return True

    async def _poll_title_change(self, old_title: str, *, timeout_ms: int = 3000, interval_ms: int = 200) -> str:
        """Poll until the page title differs from *old_title*, or timeout.

        Returns the new title, or the current title if timeout is reached
        (e.g. navigating from SE24 back to SE24 where the title stays the same).
        """
        title = await self._page.title()
        if title != old_title:
            return title

        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            await self._page.wait_for_timeout(interval_ms)
            title = await self._page.title()
            if title != old_title:
                return title

        logger.debug(
            "Title unchanged after %dms (may be same-tcode navigation)",
            timeout_ms,
            extra={"old_title": old_title},
        )
        return title

    # ---- keepalive ----

    async def start_keepalive(self, interval_seconds: int = 300) -> None:
        """Start a background keepalive ping to prevent session timeout."""
        if self._keepalive_task is not None and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        self._keepalive_task = asyncio.create_task(self._keepalive_loop(interval_seconds))

    async def stop_keepalive(self) -> bool:
        """Stop the keepalive task. Returns True if a task was running."""
        if self._keepalive_task is None or self._keepalive_task.done():
            return False
        self._keepalive_task.cancel()
        try:
            await self._keepalive_task
        except asyncio.CancelledError:
            pass
        self._keepalive_task = None
        return True

    async def _keepalive_loop(self, interval: int) -> None:
        """Background loop that pings the browser to keep the SAP session alive."""
        logger.info("Keepalive started", extra={"interval_s": interval})
        while True:
            try:
                await asyncio.sleep(interval)
                if self._page.is_closed():
                    logger.warning("Keepalive page closed, stopping")
                    break
                await self._page.evaluate("() => { /* keepalive ping */ }")
                logger.info("Keepalive ping sent")
            except asyncio.CancelledError:
                logger.info("Keepalive cancelled")
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Keepalive error", extra={"error": str(e)})

    # ---- new session (open_new_session) ----

    async def _wait_for_new_page(self, pages_before: int, timeout_ms: int = 5000) -> bool:
        """Wait for a new browser page/tab to appear in the context."""
        poll_interval_s = 0.1
        timeout_s = timeout_ms / 1000
        start_time = time.monotonic()

        while len(self._page.context.pages) <= pages_before:
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout_s:
                return False
            await asyncio.sleep(poll_interval_s)

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.debug("New browser tab detected", extra={"elapsed_ms": elapsed_ms})
        return True

    async def _register_new_window_session(
        self,
        pages_before: int,
        tcode: str | None = None,
        wait_timeout_ms: int = 5000,
    ) -> tuple[str | None, int, str | None]:
        """Wait for and register a new session created by /o prefix.

        Returns (session_id, session_count, page_title).
        """
        context = self._page.context
        await self._wait_for_new_page(pages_before, timeout_ms=wait_timeout_ms)

        pages = context.pages
        session_count = len(pages)
        new_session_id: str | None = None
        title: str | None = None

        if session_count > pages_before:
            new_page = pages[-1]
            registry = await self._get_registry()
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

    async def open_new_session(self, tcode: str) -> tuple[str | None, int, str | None]:
        """Open a transaction in a new SAP session window (/o prefix).

        Returns (session_id, session_count, page_title).
        session_id is None if no new session was created.
        """
        okcode_field = await self._find_okcode_field()

        if not okcode_field:
            logger.info("OK-Code field not found, attempting to enable")
            success, message = await self._enable_okcode_field()
            logger.info("Enable OK-Code result", extra={"success": success, "result_message": message})

            if not success:
                raise ValueError(
                    f"Could not find or enable OK-Code field. {message} "
                    "Possible causes: (1) A popup/dialog may be blocking the screen - "
                    "close any open dialogs first. (2) The OK-Code field may need to be "
                    "enabled manually: Menu -> Settings -> Enable 'OK-Code Field' or "
                    "'Transaction Field'."
                )

            okcode_field = await self._find_okcode_field()
            if not okcode_field:
                raise ValueError(
                    f"OK-Code field still not visible after enabling. {message} "
                    "Possible causes: (1) A popup/dialog may be blocking the screen - "
                    "close any open dialogs first. (2) Please try enabling it manually "
                    "in SAP settings."
                )

        # Build transaction input with /o prefix
        if tcode.startswith("/n") or tcode.startswith("/o"):
            transaction_input = tcode
        else:
            transaction_input = f"/o{tcode}"

        # Track page count before transaction
        context = self._page.context
        pages_before = len(context.pages)

        await self._page.bring_to_front()
        await self._page.wait_for_timeout(500)

        logger.info("Entering transaction", extra={"tcode": transaction_input})

        await okcode_field.click()
        await self._page.wait_for_timeout(200)

        await self._page.evaluate(
            load_js("set_okcode_field.js"),
            {"transactionInput": transaction_input},
        )

        await self._page.wait_for_timeout(300)
        await self._page.keyboard.press("Enter")
        await self._page.wait_for_load_state("networkidle", timeout=15000)
        await self._page.wait_for_timeout(200)

        return await self._register_new_window_session(pages_before, tcode=tcode)

    # pylint: disable-next=too-many-return-statements
    async def get_session_status(self, session_id: str | None = None) -> SessionStatus:
        """Check session health for the given session.

        Args:
            session_id: Explicit registry session ID (e.g. ``"s2"``) to probe.
                If ``None``, defaults to the registry's primary session
                (``s1`` if present, else lowest active). Pass an explicit ID
                to probe a specific window from the registry — bypasses
                ``self._page``, which always points at the backend's primary.

        Fixes #640: previously this method only ever probed ``self._page``,
        so calls like ``sap_session_status(session="s2")`` silently reported
        on the primary session instead.
        """
        # Single try block for both registry resolution AND page probing.
        # Two terminal handlers below: ValueError covers the registry-not-found
        # case, the broader Exception handler covers page-probe failures and
        # browser-manager startup errors that ``_get_registry`` may surface.
        # Note: this means the catch-all surface is slightly wider than the
        # pre-#640 code, which only ever touched ``self._page``.
        try:
            page = await self._resolve_status_page(session_id)
            if page is None:
                return SessionStatus(
                    status="no_page",
                    message=f"Session '{session_id}' not found in registry.",
                )

            if page.is_closed():
                return SessionStatus(status="no_page", message="Browser page is closed.")

            okcode_field = await self._find_okcode_field(page=page)
            if okcode_field:
                return SessionStatus(status="active", message="SAP session is alive and responsive.")

            login_form = await page.query_selector('input[type="password"], input[id*="sap-user" i], #sap-user')
            if login_form:
                return SessionStatus(
                    status="logged_off",
                    message="Login page detected. Please use sap_login to log in again.",
                )

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
            logger.exception("Checking session status")
            return SessionStatus(status="unknown", message=f"Error checking status: {e}")

    async def _resolve_status_page(self, session_id: str | None) -> Any | None:
        """Resolve the page that ``get_session_status`` should probe.

        Lookup order:

        1. If ``session_id`` is given (non-empty string), look it up in the
           registry. ``None`` is returned if the registry doesn't have it —
           the caller should surface a "session not found" status. Empty
           string is treated the same as ``None`` (defensive — MCP clients
           shouldn't pass it but we don't want a falsy ``or`` to silently
           reroute to the primary).

        2. If ``session_id`` is ``None``/empty, prefer the registry's
           ``primary_session``.

        3. If the registry is empty (e.g. ``WebGuiBackend.__init__`` ran
           but ``_post_login_setup`` hasn't yet, so nothing is registered),
           fall back to ``self._page`` so a pre-login
           ``sap_session_status()`` call can still detect the login form
           and return ``logged_off`` — preserving the pre-#640 behaviour
           for that edge case.
        """
        try:
            registry = await self._get_registry()
        except Exception:  # pylint: disable=broad-exception-caught
            # Browser manager init failure — fall back to self._page if
            # possible so we don't lose pre-init probing entirely.
            return self._page if not session_id else None

        if session_id:
            try:
                return registry.get_page(session_id)
            except ValueError:
                return None

        # session_id is None or empty — pick the primary, with self._page
        # as a last-resort fallback for the pre-_post_login_setup state.
        try:
            return registry.get_page(registry.primary_session)
        except ValueError:
            return self._page

    async def wait_for_ready(self, timeout_ms: int = 15000) -> None:
        """Wait for SAP page to finish loading."""
        await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)

    async def wait_for_sap_ready(self, timeout_ms: int = 5000) -> None:
        """Wait for SAP toolbar buttons to appear (screen fully interactive)."""
        try:
            await self._page.wait_for_function(
                load_js("wait_for_sap_ready.js"),
                timeout=timeout_ms,
            )
        except Exception:  # pylint: disable=broad-exception-caught
            # Fallback: fixed delay if the check times out (e.g. screen
            # without toolbar buttons, like a direct-entry transaction).
            logger.debug("wait_for_sap_ready: toolbar check timed out, using fixed delay")
            await self._page.wait_for_timeout(1000)

    async def bring_to_front(self) -> None:
        """Bring the browser window to the foreground."""
        await self._page.bring_to_front()

    async def wait(self, timeout_ms: int = 200) -> None:
        """Wait for a fixed duration."""
        await self._page.wait_for_timeout(timeout_ms)

    # ===================================================================
    # SapUiPrimitives
    # ===================================================================

    async def fill_field(self, label: str, value: str) -> None:
        """Fill a labelled input field. Raises ``ValueError`` on failure."""
        result = await self._page.evaluate(
            load_js_with_field_utils("set_field.js"),
            {"label": label, "value": value},
        )

        # Handle dropdown fields
        if result.get("isDropdown"):
            element_id = result.get("elementId")
            if not element_id:
                raise ValueError(f"Dropdown field '{label}' found but has no ID")
            dropdown_result = await self._page.evaluate(
                load_js("select_dropdown_option.js"),
                {"elementId": element_id, "optionText": value},
            )
            if not dropdown_result.get("success"):
                error = dropdown_result.get("error", "Failed to select dropdown option")
                exc = ValueError(f"Could not fill dropdown '{label}': {error}")
                exc.available_options = dropdown_result.get("available_options")  # type: ignore[attr-defined]
                raise exc
            await self._page.wait_for_timeout(300)
            return

        if not result.get("success"):
            raise ValueError(f"Could not fill field '{label}': {result.get('error', 'Unknown error')}")

    async def fill_main_input(self, value: str, labels: list[str]) -> bool:
        """Fill the main form input, skipping toolbar/combobox inputs.

        This is a safe alternative to ``discover_fields()[0]`` which may
        pick the transaction code combobox.  Tries title-attribute match
        first, then falls back to the first visible non-toolbar text input.

        Returns True if a field was filled, False otherwise.
        """
        try:
            result = await self._page.evaluate(
                load_js("find_main_input.js"),
                {"value": value, "labels": labels},
            )
            return bool(result and result.get("filled"))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("fill_main_input failed for labels=%s", labels, exc_info=True)
            return False

    async def fill_form(self, fields: dict[str, str]) -> FillFormResult:
        """Fill multiple SAP form fields in a single call."""
        if not fields:
            return FillFormResult.failure("fields cannot be empty")

        try:
            result = await self._page.evaluate(
                load_js_with_field_utils("fill_form_fields.js"),
                {"fields": fields},
            )

            filled = result.get("filled", [])
            not_found = result.get("notFound", [])
            errors = [FieldFillError(field=a["field"], error=a["error"]) for a in result.get("ambiguous", [])]
            errors.extend(FieldFillError(field=e["field"], error=e["error"]) for e in result.get("errors", []))

            return FillFormResult(filled=filled, not_found=not_found, errors=errors)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Filling form fields")
            return FillFormResult.failure(f"Error filling form fields: {e}")

    async def focus_and_type(self, accessible_name: str, text: str, delay_ms: int = 0) -> bool:
        """Find a textbox by accessible name, clear it, and type text with optional delay."""
        try:
            textbox = self._page.get_by_role("textbox", name=accessible_name).first
            if await textbox.count() > 0:
                await textbox.click()
                await textbox.fill("")
                await textbox.press_sequentially(text, delay=delay_ms)
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False

    async def fill_element_by_locator(self, locator: str, value: str, delay_ms: int = 30) -> bool:
        """Fill an element by CSS/attribute selector: click, clear, type slowly, Tab to blur."""
        try:
            element = self._page.locator(locator)
            if await element.count() == 0:
                return False
            await element.click()
            await self._page.wait_for_timeout(100)
            await element.fill("")
            await element.press_sequentially(value, delay=delay_ms)
            await self._page.keyboard.press("Tab")
            await self._page.wait_for_timeout(300)
            return True
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    async def click_element(self, selector: str) -> bool:
        """Click the first element matching a CSS/attribute selector (real click)."""
        try:
            loc = self._page.locator(selector).first
            if await loc.count() > 0:
                await loc.click()
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False

    async def evaluate_javascript(self, script: str, arg: Any = None) -> Any:
        """Evaluate a JavaScript expression in the browser and return the result."""
        if arg is not None:
            return await self._page.evaluate(script, arg)
        return await self._page.evaluate(script)

    async def click_button(self, label: str) -> None:
        """Click a button by label text."""
        # Try ARIA role-based selector first (most reliable for SAP)
        btn = self._page.get_by_role("button", name=label, exact=True)
        if await btn.count() > 0:
            await btn.click()
            await self._page.wait_for_timeout(300)
            return

        # Fallback: case-insensitive
        btn = self._page.get_by_role("button", name=re.compile(re.escape(label), re.IGNORECASE))
        if await btn.count() > 0:
            await btn.first.click()
            await self._page.wait_for_timeout(300)
            return

        raise ValueError(f"Button '{label}' not found")

    async def click_tab(self, label: str) -> None:
        """Click a tab by label text."""
        tab = self._page.get_by_role("tab", name=label, exact=True)
        if await tab.count() > 0:
            await tab.click()
            await self._page.wait_for_timeout(500)
            await self._page.wait_for_load_state("networkidle")
            return

        # Fallback: case-insensitive
        tab = self._page.get_by_role("tab", name=re.compile(re.escape(label), re.IGNORECASE))
        if await tab.count() > 0:
            await tab.first.click()
            await self._page.wait_for_timeout(500)
            await self._page.wait_for_load_state("networkidle")
            return

        raise ValueError(f"Tab '{label}' not found")

    async def press_key(self, key: str) -> KeyboardResult:
        """Send a keyboard shortcut to SAP."""
        try:
            await self._page.bring_to_front()
            await self._page.wait_for_timeout(100)
            await self._page.keyboard.press(key)
            await self._page.wait_for_load_state("networkidle", timeout=15000)

            title = await self._page.title()

            if is_sap_shortcut(key):
                try:
                    status_info = await self._page.evaluate(load_js("extract_status_bar.js"))
                    return KeyboardResult(
                        key=key,
                        page_title=title,
                        status_bar_read=True,
                        status_bar_type=status_info.get("type", "none"),
                        status_bar_message=status_info.get("message", ""),
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    return KeyboardResult(key=key, page_title=title, status_bar_read=False)

            return KeyboardResult(key=key, page_title=title)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Sending keyboard shortcut")
            return KeyboardResult.failure(f"Error sending keyboard shortcut {key}: {e}", key=key)

    async def type_text(self, text: str) -> None:
        """Type text character by character."""
        await self._page.keyboard.type(text)

    async def set_checkbox(self, label: str, checked: bool) -> None:
        """Set a checkbox by its ARIA label."""
        cb = self._page.get_by_role("checkbox", name=label, exact=True)
        if await cb.count() == 0:
            # Fallback: case-insensitive
            cb = self._page.get_by_role("checkbox", name=re.compile(re.escape(label), re.IGNORECASE))
            if await cb.count() == 0:
                raise ValueError(f"Checkbox '{label}' not found")
            cb = cb.first
        if checked:
            await cb.check()
        else:
            await cb.uncheck()
        await self._page.wait_for_timeout(200)

    async def set_radio_button(self, label: str) -> None:
        """Select a radio button by its ARIA label."""
        radio = self._page.get_by_role("radio", name=label, exact=True)
        if await radio.count() == 0:
            # Fallback: case-insensitive
            radio = self._page.get_by_role("radio", name=re.compile(re.escape(label), re.IGNORECASE))
            if await radio.count() == 0:
                raise ValueError(f"Radio button '{label}' not found")
            radio = radio.first
        await radio.check()
        await self._page.wait_for_timeout(200)

    async def select_dropdown(self, label: str, option: str) -> DropdownFillResult:
        """Select a dropdown option by label and option text."""
        # First check the field type to get the element ID
        field_check = await self._page.evaluate(load_js("check_field_type.js"), label)

        if not field_check.get("found"):
            return DropdownFillResult(
                success=False,
                error_message=f"Field '{label}' not found",
            )

        if not field_check.get("isDropdown"):
            return DropdownFillResult(
                success=False,
                error_message=f"Field '{label}' is not a dropdown",
            )

        element_id = field_check.get("elementId")
        if not element_id:
            return DropdownFillResult(
                success=False,
                error_message=f"Dropdown '{label}' has no element ID",
            )

        result = await self._page.evaluate(
            load_js("select_dropdown_option.js"),
            {"elementId": element_id, "optionText": option},
        )

        if result.get("success"):
            await self._page.wait_for_timeout(300)
            return DropdownFillResult(success=True)

        return DropdownFillResult(
            success=False,
            error_message=result.get("error", "Unknown dropdown error"),
            available_options=result.get("available_options"),
        )

    # ===================================================================
    # SapUiInspection
    # ===================================================================

    async def get_status_bar(self) -> StatusBarInfo:
        """Read the current message from SAP's status bar."""
        try:
            status_info = await self._page.evaluate(load_js("extract_status_bar.js"))
            return StatusBarInfo(
                type=status_info.get("type", "none"),
                message=status_info.get("message", ""),
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Reading status bar")
            return StatusBarInfo.failure(f"Error reading status bar: {e}", type="none")

    async def get_screen_info(self) -> ScreenInfo:
        """Get technical information about the current SAP screen."""
        try:
            screen_info = await self._page.evaluate(load_js("extract_screen_info.js"))
            return ScreenInfo(
                transaction=screen_info.get("transaction"),
                title=screen_info.get("title", ""),
                url=screen_info.get("url", ""),
                program=screen_info.get("program"),
                dynpro=screen_info.get("dynpro"),
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting screen info")
            return ScreenInfo.failure(f"Error getting screen info: {e}", title="", url="")

    async def get_screen_text(self, include_dropdown_options: bool = False) -> ScreenText:
        """Get all readable text from the current SAP screen."""
        try:
            result = await self._page.evaluate(load_js("extract_screen_text.js"))

            screen_text = ScreenText(
                title=result.get("title", ""),
                status_bar=result.get("statusBar") or None,
                tabs=result.get("tabs", []),
                labels=result.get("labels", []),
                buttons=result.get("buttons", []),
            )

            if include_dropdown_options:
                dropdowns = await self._fetch_dropdown_options()
                screen_text.dropdowns = dropdowns

            return screen_text

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Extracting screen text")
            return ScreenText.failure(f"Error extracting screen text: {e}")

    async def discover_fields(self) -> list[FieldInfo]:
        """Discover all input fields on the current SAP screen."""
        fields_data = await self._page.evaluate(load_js("discover_fields.js"))
        return [
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

    async def get_form_fields(self, *, include_dropdown_options: bool = False) -> FormFieldsResult:
        """Discover fillable form fields with type information."""
        try:
            raw_fields = await self._page.evaluate(load_js("detect_form_fields.js"))
            fields = []
            for raw in raw_fields:
                options: list[str] | None = None
                if include_dropdown_options and raw.get("field_type") == "dropdown":
                    label = raw.get("label", "")
                    if label:
                        options = await self.get_dropdown_options(label)
                fields.append(
                    FormField(
                        id=raw.get("id", ""),
                        label=raw.get("label", ""),
                        field_type=SapFieldType(raw.get("field_type", "text")),
                        current_value=raw.get("current_value"),
                        readonly=raw.get("readonly", False),
                        options=options,
                    )
                )
            return FormFieldsResult(fields=fields)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Getting form fields")
            return FormFieldsResult.failure(f"Error getting form fields: {e}")

    async def discover_buttons(self) -> list[ButtonInfo]:
        """Discover all clickable buttons on the current SAP screen."""
        buttons_data = await self._page.evaluate(load_js("discover_buttons.js"))
        return [
            ButtonInfo(
                label=b.get("label", ""),
                id=b.get("id"),
                selector=b.get("selector"),
                shortcut=b.get("shortcut"),
                accesskey=b.get("accesskey"),
            )
            for b in buttons_data
            if b.get("label")
        ]

    async def get_snapshot(self) -> AriaSnapshot:
        """Get the ARIA accessibility tree snapshot."""
        raw = await self._page.locator("body").aria_snapshot()
        return AriaSnapshot(raw)

    async def get_page_title(self) -> str:
        """Get the current page title."""
        return await self._page.title()

    async def take_screenshot(self) -> bytes:
        """Take a screenshot of the current page."""
        return await self._page.screenshot(full_page=True)

    async def read_table(
        self,
        start_row: int = 1,
        end_row: int | None = None,
        max_rows: int = 100,
    ) -> TableData:
        """Read rows from an ALV grid or table on the current screen."""
        try:
            table_data = await self._page.evaluate(
                load_js("extract_table_data.js"),
                {"startRow": start_row, "endRow": end_row, "maxRows": max_rows},
            )

            if "error" in table_data:
                return TableData.failure(str(table_data["error"]))

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
                start_row=table_data.get("startRow", 1),
                end_row=table_data.get("endRow"),
                alv=alv,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Reading table")
            return TableData.failure(f"Error reading table: {e}")

    async def click_table_cell(self, row: int, column: int | str, action: str = "click") -> TableCellClickResult:
        """Click a cell in the current ALV grid table."""
        try:
            result = await self._page.evaluate(
                load_js("click_table_cell.js"),
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

            if action == "dblclick":
                await self._page.dblclick(selector)
            else:
                await self._page.click(selector)

            await asyncio.sleep(0.5)
            await self._page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(0.3)

            title = await self._page.title()
            return TableCellClickResult(
                row=row,
                column=result.get("column", column),
                selector_used=selector,
                page_title=title,
                was_hotspot=result.get("wasHotspot", False),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Clicking table cell")
            return TableCellClickResult.failure(
                f"Error clicking table cell: {e}",
                row=row,
                column=column,
                selector_used="",
            )

    async def get_dropdown_options(self, label: str) -> list[str]:
        """Get available options for a dropdown field by label."""
        field_check = await self._page.evaluate(load_js("check_field_type.js"), label)
        if not field_check.get("found") or not field_check.get("isDropdown"):
            return []
        element_id = field_check.get("elementId")
        if not element_id:
            return []
        try:
            result = await self._page.evaluate(load_js("get_dropdown_options.js"), element_id)
            if result.get("success"):
                return list(result.get("options", []))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning("Getting dropdown options for %r", label)
        return []

    async def _fetch_dropdown_options(self) -> list[DropdownInfo]:
        """Fetch options for all dropdown fields on the current page."""
        raw_fields = await self._page.evaluate(load_js("detect_form_fields.js"))
        dropdown_fields = [f for f in raw_fields if f.get("field_type") == "dropdown"]

        dropdowns: list[DropdownInfo] = []
        for field in dropdown_fields:
            element_id, label = field.get("id"), field.get("label", "")
            if not element_id:
                continue
            try:
                result = await self._page.evaluate(load_js("get_dropdown_options.js"), element_id)
                if result.get("success"):
                    dropdowns.append(
                        DropdownInfo(
                            id=element_id,
                            label=label,
                            options=result.get("options", []),
                        )
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Getting dropdown options for %r", element_id)
        return dropdowns

    # ===================================================================
    # SapEditor
    # ===================================================================

    async def read_editor_source(self) -> str | None:
        """Read the current source code from the SAP editor textarea."""
        try:
            textarea = self._page.locator("textarea[id*='textedit']").first
            if not await textarea.is_visible(timeout=3000):
                return None
            return await textarea.input_value()
        except (PlaywrightError, OSError) as exc:
            logger.warning("Could not read editor content: %s", exc)
            return None

    async def replace_editor_source(self, code: str) -> bool:
        """Replace the entire editor content with new source code."""
        try:
            textarea = self._page.locator("textarea[id*='textedit']").first
            await textarea.click()
            await self._page.keyboard.press("Control+a")
            await self._page.wait_for_timeout(200)
            await self._page.keyboard.press("Delete")
            await self._page.wait_for_timeout(200)
            await textarea.fill(code)
            return True
        except (PlaywrightError, OSError) as exc:
            logger.warning("Failed to replace editor source: %s", exc)
            return False

    async def check_and_activate(self) -> CheckActivateResult:
        """Run syntax check (Ctrl+F2) and activation (Ctrl+F3)."""
        messages: list[str] = []

        await self._page.keyboard.press("Control+F2")
        await self._page.wait_for_timeout(2000)
        await self._page.wait_for_load_state("networkidle")

        snapshot = await self._page.locator("body").aria_snapshot()
        check_ok, check_msg = _parse_toolbar_note(snapshot)
        messages.append(f"Check: {check_msg}")

        if not check_ok:
            return CheckActivateResult(success=False, messages=messages, activated=False)

        await self._page.keyboard.press("Control+F3")
        await self._page.wait_for_timeout(2000)
        await self._page.wait_for_load_state("networkidle")

        snapshot = await self._page.locator("body").aria_snapshot()

        # Handle "Inaktive Objekte" / "Inactive Objects" popup
        if "Inaktive Objekte" in snapshot or "Inactive Objects" in snapshot:
            logger.info("Detected inactive objects popup, confirming with Enter")
            await self._page.keyboard.press("Enter")
            await self._page.wait_for_timeout(2000)
            await self._page.wait_for_load_state("networkidle")
            snapshot = await self._page.locator("body").aria_snapshot()

        activate_ok, activate_msg = _parse_toolbar_note(snapshot)
        messages.append(f"Activate: {activate_msg}")

        return CheckActivateResult(success=activate_ok, messages=messages, activated=activate_ok)

    # ===================================================================
    # SapPopup
    # ===================================================================

    async def check_popup(self) -> PopupInfo | None:
        """Fast check for blocking popup dialog."""
        result = await self._page.evaluate(load_js("check_popup.js"))
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

    async def dismiss_popup(  # pylint: disable=too-many-branches
        self,
        button_label: str | None = None,
        use_close_button: bool = False,
    ) -> ClosePopupResult:
        """Dismiss an active popup dialog."""
        try:
            popup = await self.check_popup()
            if popup is None:
                return ClosePopupResult.failure("No popup to close")

            clicked_label: str
            if use_close_button:
                if not popup.has_close_button:
                    return ClosePopupResult.failure("No close button available")
                await self._page.click(escape_css_selector(f"#{popup.close_button_id}"))
                clicked_label = "[X]"
            elif not button_label:
                return ClosePopupResult.failure("Specify button_label or use_close_button=True")
            else:
                button_lower = button_label.lower()
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
                    return ClosePopupResult.failure(f"Button '{button_label}' not found. Available: {available}")

                if matched_button.id:
                    await self._page.click(escape_css_selector(f"#{matched_button.id}"))
                elif matched_button.accesskey:
                    await self._page.keyboard.press(f"Alt+{matched_button.accesskey}")
                else:
                    await self._page.get_by_role("button", name=matched_button.label).click()
                clicked_label = matched_button.label

            await self._page.wait_for_timeout(500)
            popup_after = await self.check_popup()

            status_info = await self._page.evaluate(load_js("extract_status_bar.js"))

            return ClosePopupResult(
                button_clicked=clicked_label,
                popup_closed=popup_after is None,
                status_bar_type=status_info.get("type", "none"),
                status_bar_message=status_info.get("message", ""),
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Dismissing popup")
            return ClosePopupResult.failure(f"Error dismissing popup: {e}")

    # ===================================================================
    # Session management (SapNavigation)
    # TODO: move to a session manager protocol when adding second backend
    # ===================================================================

    @staticmethod
    async def _get_registry() -> SessionRegistry:
        """Get the shared session registry (lazy import to avoid circular deps)."""
        manager = await get_browser_manager()
        return manager.registry

    async def list_sessions(self) -> list[SessionInfo]:
        """List active sessions with their metadata."""
        registry = await self._get_registry()
        result: list[SessionInfo] = []
        for sid in registry.list_sessions():
            try:
                page = registry.get_page(sid)
                title = await page.title()
                result.append(
                    SessionInfo(
                        session_id=sid,
                        title=title,
                        is_primary=(sid == registry.primary_session),
                        agent_id=registry.get_bound_agent(sid),
                    )
                )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning("Skipping session %s in listing (page error)", sid)
                continue
        return result

    async def close_session(self, session_id: str) -> bool:
        """Close a session by ID. Returns True if closed, False if not found."""
        registry = await self._get_registry()
        if not registry.has_session(session_id):
            return False
        page = registry.get_page(session_id)
        try:
            ok_field = await page.query_selector("#ToolbarOkCode")
            if ok_field:
                await ok_field.fill("/nex")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        if not page.is_closed():
            await page.close()
        registry.unregister(session_id)
        return True

    async def bind_session(self, session_id: str, agent_id: str, *, force: bool = False) -> str | None:
        """Bind an agent to a session. Returns previous agent_id or None.

        Strict by default (#643): raises ``SessionBindConflictError`` if the
        session is bound to a different agent. Pass ``force=True`` to take
        over.
        """
        registry = await self._get_registry()
        old = registry.get_bound_agent(session_id)
        registry.bind(session_id, agent_id, force=force)
        return old

    async def release_session(self, session_id: str) -> str | None:
        """Release agent binding from a session. Returns released agent_id or None."""
        registry = await self._get_registry()
        old = registry.get_bound_agent(session_id)
        registry.release(session_id)
        return old

    async def has_session(self, session_id: str) -> bool:
        """Check whether a session exists."""
        registry = await self._get_registry()
        return registry.has_session(session_id)

    async def reset_to_primary(self) -> dict[str, list[str]]:
        """Close every session except the primary one.

        WebGUI parity for the desktop backend's reset (issue #637). The
        WebGUI registry already drops sessions on page close, so we just
        iterate the non-primary IDs and call ``close_session`` on each.

        Returns ``{"closed": [...], "remaining": [...], "killed_agents":
        [...], "errors": [...]}`` to match the desktop backend's shape.
        """
        registry = await self._get_registry()
        primary = registry.primary_session
        victims = [sid for sid in registry.list_sessions() if sid != primary]
        closed: list[str] = []
        errors: list[str] = []
        killed_agents: list[str] = []
        for sid in victims:
            bound = registry.get_bound_agent(sid)
            try:
                ok = await self.close_session(sid)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                errors.append(f"{sid}: {exc}")
                continue
            if ok:
                closed.append(sid)
                if bound:
                    killed_agents.append(bound)
            else:
                errors.append(f"{sid}: close returned False")
        remaining = registry.list_sessions()
        logger.info(
            "reset_to_primary",
            extra={
                "primary": primary,
                "closed": closed,
                "remaining": remaining,
                "killed_agents": killed_agents,
                "errors": errors,
            },
        )
        return {
            "closed": closed,
            "remaining": remaining,
            "killed_agents": killed_agents,
            "errors": errors,
        }
