"""SAP GUI desktop login/logoff helpers.

Lessons learned from live testing against HF S/4 (S4U, client 100):

- Each login() opens a NEW connection (con[N]) via app.open_connection().
  This is NOT the same as opening a new session/mode (/o) within an
  existing connection. Connections are independent; sessions share a login.

- The "multiple logon" popup (Lizenzinformation bei Mehrfachanmeldung)
  appears when the same user is already logged in on another connection.
  Its default radio button selection is NOT stable — it can be OPT1, OPT2,
  or OPT3 depending on server state. Always explicitly select OPT2.

- send_command("/nEX") can BLOCK indefinitely on COM when closing a session.
  Use connection.CloseConnection() instead — it returns immediately.

- SAP GUI leaves "ghost connections" (0 sessions) in the COM tree after
  closing sessions. These must be cleaned up via CloseConnection().

- The login screen is program SAPMSYST, screen 20 (standard on all systems).
  Field IDs: txtRSYST-MANDT (client), txtRSYST-BNAME (user),
  pwdRSYST-BCODE (password), txtRSYST-LANGU (language).
"""

# pylint: disable=import-outside-toplevel,broad-exception-caught,too-many-arguments,too-many-positional-arguments

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

from sapwebguimcp.sapgui._errors import SapConnectionError, SapGuiTimeoutError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sapwebguimcp.sapgui.components.session import GuiSession

_DEFAULT_SAPLOGON_PATH = r"C:\Program Files\SAP\FrontEnd\SAPGUI\saplogon.exe"


def login(
    connection_name: str,
    client: str,
    user: str,
    password: str,
    language: str = "EN",
    saplogon_exe_path: str | None = None,
    timeout: int = 30,
) -> GuiSession:
    """Connect to SAP GUI, open a connection, fill the login screen, return a session.

    Launches SAP Logon if not already running. Handles the "multiple logon" popup
    by selecting "continue without ending other sessions" (OPT2).

    Args:
        connection_name: SAP Logon entry name (e.g. "HF S/4").
        client: SAP client/mandant (e.g. "100").
        user: SAP username.
        password: SAP password.
        language: Login language (default "EN").
        saplogon_exe_path: Path to saplogon.exe (default: standard install path).
        timeout: Max seconds to wait for connection/session to become available.

    Returns:
        A logged-in GuiSession.

    Raises:
        SapGuiTimeoutError: If SAP GUI or session doesn't become available.
        ScriptingDisabledError: If scripting is disabled on the server.
        SapConnectionError: If login fails (wrong credentials, SAP error).
    """
    from sapwebguimcp.sapgui import SapGui  # pylint: disable=import-outside-toplevel

    logger.info(
        "Logging in to SAP via desktop GUI",
        extra={"connection_name": connection_name, "user": user},
    )

    # Step 1: Ensure SAP GUI is running
    try:
        app = SapGui.connect()
    except SapConnectionError:
        app = SapGui.launch(exe_path=saplogon_exe_path or _DEFAULT_SAPLOGON_PATH, timeout=timeout)

    # Step 2: Open connection
    conn = app.open_connection(connection_name, sync=True)
    session = _wait_for_session(conn, timeout=timeout)

    # Step 3: Fill login screen (if we're on the login dynpro)
    # find_by_id returns GuiComponent | None but the actual runtime objects
    # expose .text, .send_v_key, etc. via their concrete subclasses.
    if session.info.program == "SAPMSYST":
        cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-MANDT")).text = client
        cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-BNAME")).text = user
        cast(Any, session.find_by_id("wnd[0]/usr/pwdRSYST-BCODE")).text = password
        cast(Any, session.find_by_id("wnd[0]/usr/txtRSYST-LANGU")).text = language
        cast(Any, session.find_by_id("wnd[0]")).send_v_key(0)  # Enter

        # Brief wait for server response
        time.sleep(1)

        # Step 4: Handle "multiple logon" popup
        _handle_multiple_logon_popup(session)

    # Step 5: Verify login succeeded
    if session.info.program == "SAPMSYST":
        sbar = cast(Any, session.find_by_id("wnd[0]/sbar"))
        raise SapConnectionError(f"Login failed: {sbar.text}")

    sbar = session.find_by_id("wnd[0]/sbar", raise_error=False)
    if sbar is not None and cast(Any, sbar).message_type == "E":
        raise SapConnectionError(f"Login failed: {cast(Any, sbar).text}")

    logger.info(
        "Desktop login successful",
        extra={"system": connection_name, "user": user},
    )
    return session


def logoff(session: GuiSession) -> None:
    """Close the session's connection, then clean up ghost connections.

    Uses CloseConnection() on the parent connection rather than /nEX,
    because send_command("/nEX") can block indefinitely on COM.
    """
    logger.info("Logging off desktop session")
    try:
        parent_conn = session.com.Parent
        parent_conn.CloseConnection()
    except Exception:
        pass  # Connection is likely already dead

    # Clean up ghost connections (0 sessions) left behind
    cleanup_ghost_connections()


def cleanup_ghost_connections() -> None:
    """Close all connections that have 0 sessions (ghost connections).

    SAP GUI sometimes leaves dead connections in the COM tree after
    /nEX or failed connection attempts. These are harmless but clutter
    the connection list.
    """
    from sapwebguimcp.sapgui import SapGui

    try:
        app = SapGui.connect()
    except Exception:
        return  # SAP GUI not running, nothing to clean

    try:
        # Use raw COM to iterate connections — avoids type issues with wrapped collections
        raw_conns = app.com.Children
        closed = 0
        for i in range(raw_conns.Count - 1, -1, -1):
            raw_conn = raw_conns(i)
            if raw_conn.Children.Count == 0:
                try:
                    raw_conn.CloseConnection()
                    closed += 1
                except Exception:
                    pass  # Best effort
        if closed:
            logger.debug("Cleaned up %d ghost connections", closed)
    except Exception:
        pass  # Don't fail on cleanup


def _wait_for_session(conn: Any, timeout: int = 30) -> GuiSession:
    """Poll until the connection has at least one session, then return it wrapped."""
    from sapwebguimcp.sapgui.components.session import GuiSession as GuiSessionCls

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if len(conn.children) > 0:
                session = conn.children[0]
                if isinstance(session, GuiSessionCls):
                    return session
        except Exception:
            pass
        time.sleep(0.5)
    raise SapGuiTimeoutError(f"No session available on connection after {timeout}s")


def _handle_multiple_logon_popup(session: GuiSession) -> None:
    """Handle the 'Lizenzinformation bei Mehrfachanmeldung' popup.

    Always explicitly selects OPT2 ('continue without ending other sessions')
    because the default selection is not stable across SAP versions.
    """
    popup = session.find_by_id("wnd[1]", raise_error=False)
    if popup is None:
        return
    logger.info("Handling multiple logon popup (selecting OPT2)")
    opt2 = session.find_by_id("wnd[1]/usr/radMULTI_LOGON_OPT2", raise_error=False)
    if opt2 is not None:
        cast(Any, opt2).selected = True
        cast(Any, session.find_by_id("wnd[1]")).send_v_key(0)  # Enter
        time.sleep(1)  # Wait for server to process
