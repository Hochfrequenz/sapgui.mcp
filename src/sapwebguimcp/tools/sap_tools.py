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

import json
import logging
import re
from importlib import resources
from typing import Any, Optional

from fastmcp import Context, FastMCP

from sapwebguimcp.backend.manager import get_backend
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
from sapwebguimcp.tools._backend_utils import _is_desktop_backend
from sapwebguimcp.tools.sap_discover_clients_impl import DiscoverClientsResult, sap_discover_clients_impl
from sapwebguimcp.tools.sap_list_connections_impl import ConnectionListResult, sap_list_connections_impl
from sapwebguimcp.tools.sap_login_impl import sap_login_impl
from sapwebguimcp.tools.session_tools import (
    sap_session_bind_impl,
    sap_session_close_impl,
    sap_session_list_impl,
    sap_session_release_impl,
)

__all__ = ["register_sap_tools", "SELECTORS", "parse_shortcut_from_title"]

logger = logging.getLogger(__name__)


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
    if not title:
        return None
    match = _SHORTCUT_PATTERN.match(title.strip())
    if not match:
        return None

    action = match.group(1).strip()
    shortcut = match.group(2).strip()

    if not _is_keyboard_shortcut(shortcut):
        return None

    return ShortcutInfo(action=action, shortcut=shortcut)


# =============================================================================
# SAP Selectors (kept for backward-compatible test imports)
# =============================================================================

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
}


# =============================================================================
# Tool Registration
# =============================================================================


async def _get_button_tooltips_desktop(backend: Any) -> list[str]:
    """Read Tooltip property from all buttons on the current screen (Desktop backend)."""
    from typing import cast  # pylint: disable=import-outside-toplevel

    from sapwebguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel
    from sapwebguimcp.backend.desktop._element_finder import _flatten  # pylint: disable=import-outside-toplevel

    if not isinstance(backend, DesktopBackend):
        return []
    session = backend._require_session()  # pylint: disable=protected-access

    def _read_tooltips() -> list[str]:
        wnd = session.find_by_id("wnd[0]")
        tree = cast(Any, wnd).dump_tree(max_depth=3)
        tooltips: list[str] = []
        for elem in _flatten(tree):
            if elem.type_as_number == 40:  # GuiButton
                try:
                    btn = session.find_by_id(elem.id)
                    if btn is None:
                        continue
                    raw = btn.com
                    tooltip = str(getattr(raw, "Tooltip", ""))
                    if tooltip:
                        tooltips.append(tooltip)
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.debug("tooltip_read_failed", extra={"element_id": elem.id})
        return tooltips

    return await backend._com.run(_read_tooltips)  # pylint: disable=protected-access


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
        backend = await get_backend(tool_name="sap_keepalive_start")
        await backend.start_keepalive(interval_seconds)
        return KeepaliveResult(running=True, interval_seconds=interval_seconds)

    @mcp.tool(description="Stop the background keepalive task")
    async def sap_keepalive_stop() -> KeepaliveResult:
        """
        Stop the background keepalive task.

        Call this when you're done with SAP or want to allow the session to timeout naturally.

        Returns:
            KeepaliveResult indicating the keepalive is stopped.
        """
        backend = await get_backend(tool_name="sap_keepalive_stop")
        await backend.stop_keepalive()
        return KeepaliveResult(running=False)

    @mcp.tool(
        description=(
            "Log into SAP. "
            "On WebGUI: requires SAP_URL, Chrome with --remote-debugging-port=9222, "
            "and VPN (if internal SAP). "
            "On Desktop: requires SAP_CONNECTION_NAME (SAP Logon entry) "
            "and SAP GUI for Windows with scripting enabled. "
            "Both backends use SAP_USER, SAP_PASSWORD, SAP_MANDANT from environment. "
            "Use client to override SAP_MANDANT and connection_name to override SAP_CONNECTION_NAME."
        )
    )
    async def sap_login(
        url: Optional[str] = None,
        client: Optional[str] = None,
        connection_name: Optional[str] = None,
        ctx: Context | None = None,
    ) -> LoginResult:
        """
        Log into SAP.

        On WebGUI, opens the SAP Web GUI URL and automatically logs in.
        On Desktop, connects via SAP Logon and opens a new connection.
        Both backends use credentials from environment variables
        (SAP_USER, SAP_PASSWORD, SAP_MANDANT, SAP_LANGUAGE).

        Args:
            url: SAP Web GUI URL (WebGUI only). If not provided, uses SAP_URL from environment.
            client: SAP client/mandant (3-digit string, e.g. '200'). Overrides SAP_MANDANT if provided.
            connection_name: SAP Logon entry name (Desktop only, e.g. 'S4U'). Overrides SAP_CONNECTION_NAME.

        Returns:
            LoginResult indicating login success or what action is needed.
        """
        session_id = getattr(ctx, "session_id", None) if ctx else None
        return await sap_login_impl(url=url, client=client, connection_name=connection_name, session_id=session_id)

    @mcp.tool(
        description=(
            "List available SAP systems from SAP Logon (SAPUILandscape.xml). "
            "Returns connection names that can be passed to sap_login as connection_name. "
            "Desktop backend only."
        )
    )
    async def sap_list_connections() -> ConnectionListResult:
        """List available SAP Logon connections."""
        return await sap_list_connections_impl()

    @mcp.tool(
        description=(
            "Open an SAP connection and return the available clients (Mandanten) "
            "from the login screen. Returns the pre-filled default client and a list "
            "of available clients parsed from the Information section. "
            "The session is left open — pass the returned session_id to sap_login "
            "to reuse it. Desktop backend only. "
            "Use this before sap_login when the client is not yet known."
        )
    )
    async def sap_discover_clients(connection_name: str | None = None) -> DiscoverClientsResult:
        """Discover available SAP clients (Mandanten) from the login screen."""
        return await sap_discover_clients_impl(connection_name)

    @mcp.tool(
        description=(
            "Enter and execute an SAP transaction code. "
            "IMPORTANT: Do NOT use this for SE11, SE16, SE24, SE37, or SE93 - "
            "use the dedicated sap_se11_lookup, sap_se16_query, sap_se24_lookup, "
            "sap_se37_lookup, or sap_se93_lookup tools instead, which are faster and return structured data.\n\n"
            "**Multi-Session Support (for parallel agents):**\n"
            "- `new_window=True`: Opens transaction in a NEW SAP session (separate window)\n"
            "- Returns `session_count` showing total open sessions\n"
            "- Use `session` parameter on subsequent tool calls to target that session\n\n"
            "Example workflow for 5 parallel agents:\n"
            '1. `sap_transaction("BP", new_window=True)` → Creates session s2\n'
            "2. `sap_session_list()` → See all sessions with IDs\n"
            '3. `sap_fill_form({...}, session="s2")` → Target specific session\n'
            '4. `sap_session_close(session="s2")` → **ALWAYS close when done!**\n\n'
            "⚠️ **CRITICAL: Always close sessions you opened!** When you opened a session with "
            "`new_window=True`, you MUST close it with `sap_session_close` when your work is done. "
            "SAP has a limited number of sessions per user — orphaned sessions accumulate and will "
            "eventually block all further work.\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2", "s3", etc.: Targets specific session'
        )
    )
    async def sap_transaction(  # pylint: disable=too-many-return-statements,too-many-locals,too-many-branches
        tcode: str,
        new_window: bool = False,
        reset_first: bool = False,
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
            reset_first: If True, navigate to SAP Easy Access (/n) before entering
                        the transaction. Use this when inputs seem stuck, fields aren't
                        updating, or the previous transaction left the session in a bad
                        state.  Ignored when new_window=True.
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            TransactionResult indicating success or describing any issues.
            When new_window=True, includes session_id of the new session.
        """
        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_transaction")
        except ValueError as e:
            return TransactionResult.failure(str(e), tcode=tcode)

        # Reset to SAP Easy Access first if requested (clears all residual state).
        if reset_first and not new_window:
            await backend.enter_transaction("/n")
            await backend.wait_for_ready()

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
                await backend.wait(200)

                # Check if a popup appeared after navigation
                popup = await backend.check_popup()
                if popup:
                    return TransactionResult.failure(
                        f"Popup blocking: {popup.message or 'confirmation required'}",
                        tcode=tcode,
                        popup=popup,
                    )

                return result

            # new_window=True: delegate to backend
            new_session_id, session_count, new_title = await backend.open_new_session(tcode)

            # Check if a popup appeared after navigation
            popup = await backend.check_popup()
            if popup:
                return TransactionResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    tcode=tcode,
                    popup=popup,
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
                page_title=new_title,
                new_window=True,
                session_id=new_session_id,
                session_count=session_count,
            )

        except ValueError as e:
            return TransactionResult.failure(str(e), tcode=tcode)
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
            "Send a keyboard shortcut to SAP\n\n"
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
        Send a keyboard shortcut to SAP.

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
            await backend.wait(300)

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

    @mcp.tool(
        description=(
            "Look up known field CSS selectors for an SAP transaction (WebGUI only). "
            "Returns pre-discovered selectors from a static registry. "
            "On Desktop, use sap_discover_fields instead — it discovers fields dynamically."
        )
    )
    async def sap_lookup_fields(transaction: str) -> FieldLookupResult:  # pylint: disable=too-many-return-statements
        """
        Look up known field CSS selectors for an SAP transaction.

        This tool returns pre-discovered CSS selectors for WebGUI only.
        On the Desktop backend, use sap_discover_fields instead.

        Args:
            transaction: Transaction code (e.g., SE16, VA01, BP)

        Returns:
            FieldLookupResult with known CSS selectors (WebGUI only).
        """
        tcode_upper = transaction.upper().strip()

        if get_settings().backend_type == "desktop":
            return FieldLookupResult.failure(
                "sap_lookup_fields returns WebGUI CSS selectors which don't work on Desktop. "
                "Use sap_discover_fields to find fields dynamically.",
                transaction=tcode_upper,
            )

        if get_settings().backend_type == "desktop":
            return FieldLookupResult.failure(
                "sap_lookup_fields returns WebGUI CSS selectors which don't work on Desktop. "
                "Use sap_discover_fields to find fields dynamically.",
                transaction=tcode_upper,
            )

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
            "Returns fields with label, name, value, and a selector/ID for targeting the field. "
            "Use the label with sap_fill_form to fill fields (works on all backends). "
            "On WebGUI, the 'selector' field is a CSS selector. "
            "On Desktop, it's a SAP GUI element ID. "
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

        Returns information about all visible input fields. Use the 'label'
        field with sap_fill_form to fill fields reliably on any backend.

        Args:
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            DiscoveredFields with list of fields including:
            - field_id: SAP field ID (e.g., 'NAME_FIRST', 'STREET')
            - label: Associated label text (for sap_fill_form)
            - selector: CSS selector (WebGUI) or element ID (Desktop)
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
            "Returns buttons with label, selector, shortcut (e.g. F3), and accesskey. "
            "Prefer keyboard shortcuts (sap_keyboard) when available — they're faster and work on all backends. "
            "On WebGUI, use the 'selector' field with browser_click. "
            "On Desktop, use sap_com_evaluate to press buttons by element ID. "
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
            if _is_desktop_backend(backend):
                # Desktop: read Tooltip property from all buttons via COM
                titles = await _get_button_tooltips_desktop(backend)
            else:
                # WebGUI: get all title attributes via JavaScript
                titles = await backend.evaluate_javascript("""() => {
                        const elements = document.querySelectorAll('[title]');
                        return Array.from(elements).map(el => el.title).filter(Boolean);
                    }""")

            # Parse titles/tooltips for shortcuts (same format on both backends)
            shortcuts: list[ShortcutInfo] = []
            seen: set[tuple[str, str]] = set()

            for title in titles:
                shortcut_info: ShortcutInfo | None = parse_shortcut_from_title(title)
                if shortcut_info is None:
                    continue

                # Skip duplicates
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
            "Use this when filling 2+ fields on the SAME screen without UI navigation between them.\n\n"
            "Keys can be:\n"
            "- Visible label text (e.g., 'First Name', 'Straße') — works on all backends\n"
            "- CSS selectors starting with '#' (WebGUI only, e.g., '#M0:46:1:1::0:21')\n"
            "- SAP GUI element names (Desktop only, e.g., 'BUT000-NAME_LAST')\n\n"
            "When to use:\n"
            "- Filling a form with multiple input fields\n"
            "- All fields visible on current screen\n"
            "- No button clicks or navigation needed between fields\n\n"
            "When NOT to use:\n"
            "- Single field only (use sap_set_field)\n"
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
            "Set a single SAP form field by label, CSS selector, or element name. "
            "Finds the field dynamically and fills it with the given value.\n\n"
            "The label parameter can be:\n"
            "- Visible label text (e.g., 'Last Name', 'Nachname') — works on all backends\n"
            "- CSS selector (WebGUI only, e.g., '#M0:46:1:1::0:21')\n"
            "- SAP GUI element name (Desktop only, e.g., 'BUT000-NAME_LAST')\n\n"
            "This is simpler than sap_fill_form for single fields.\n\n"
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
        Set a single SAP form field by label, CSS selector, or element name.

        Finds the field dynamically and fills it. Supports both regular
        text inputs and dropdown/combobox fields.

        For dropdown fields, the tool automatically detects the field type and
        uses the appropriate selection mechanism. If the requested value is not
        in the dropdown options, returns available_options listing valid choices.

        Args:
            label: Field label text (e.g., 'Last Name'), CSS selector (WebGUI),
                   or SAP GUI element name (Desktop)
            value: Value to set in the field (for dropdowns: exact option text)
            session: Session ID (e.g., "s1", "s2"). None uses primary session.
            agent_id: Agent identifier for binding check. Optional.

        Returns:
            SetFieldResult with label, value, and the selector/ID that was used.
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
            available = getattr(ve, "available_options", None)
            return SetFieldResult.failure(str(ve), label=label, value=value, available_options=available)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Setting field", extra={"label": label})
            return SetFieldResult.failure(f"Error setting field: {e}", label=label, value=value)

    @mcp.tool(
        description=(
            "Set a SAP checkbox to checked or unchecked by its label text.\n\n"
            "Use sap_get_form_fields first to see available checkboxes and their current state.\n\n"
            "Args:\n"
            "- label: Checkbox label text (e.g., 'Workbench-Aufträge', 'Freigegeben')\n"
            "- checked: True to check, False to uncheck\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session'
        ),
    )
    async def sap_set_checkbox(
        label: str,
        checked: bool,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SetFieldResult:
        """Set a SAP checkbox to checked or unchecked."""
        if not label:
            return SetFieldResult.failure("label cannot be empty", label="", value=str(checked))

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_set_checkbox")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value=str(checked))

        try:
            popup = await backend.check_popup()
            if popup:
                return SetFieldResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    label=label,
                    value=str(checked),
                    popup=popup,
                )
            await backend.set_checkbox(label, checked)
            await backend.wait_for_ready()
            return SetFieldResult(label=label, value=str(checked))
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value=str(checked))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Setting checkbox")
            return SetFieldResult.failure(f"Error setting checkbox: {e}", label=label, value=str(checked))

    @mcp.tool(
        description=(
            "Select a SAP radio button by its label text.\n\n"
            "Use sap_get_form_fields first to see available radio buttons and which is selected.\n\n"
            "Args:\n"
            "- label: Radio button label text (e.g., 'Datenbanktabelle', 'Database table')\n\n"
            "**Session parameter:**\n"
            '- session=None (default): Uses primary session ("s1")\n'
            '- session="s2": Targets specific session'
        ),
    )
    async def sap_set_radio_button(
        label: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SetFieldResult:
        """Select a SAP radio button."""
        if not label:
            return SetFieldResult.failure("label cannot be empty", label="", value="")

        try:
            backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_set_radio_button")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value="selected")

        try:
            popup = await backend.check_popup()
            if popup:
                return SetFieldResult.failure(
                    f"Popup blocking: {popup.message or 'confirmation required'}",
                    label=label,
                    value="selected",
                    popup=popup,
                )
            await backend.set_radio_button(label)
            await backend.wait_for_ready()
            return SetFieldResult(label=label, value="selected")
        except ValueError as e:
            return SetFieldResult.failure(str(e), label=label, value="selected")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Setting radio button")
            return SetFieldResult.failure(f"Error setting radio button: {e}", label=label, value="selected")

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
