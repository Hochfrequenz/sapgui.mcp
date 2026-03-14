"""SAP GUI desktop login/logoff helpers."""

# pylint: disable=import-outside-toplevel,broad-exception-caught

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from sapwebguimcp.sapgui._errors import SapConnectionError, SapGuiTimeoutError

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
    from sapwebguimcp.sapgui import SapGui

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

    sbar = cast(Any, session.find_by_id("wnd[0]/sbar"))
    if sbar.message_type == "E":
        raise SapConnectionError(f"Login failed: {sbar.text}")

    return session


def logoff(session: GuiSession) -> None:
    """Cleanly log off from SAP GUI using /nEX."""
    try:
        session.send_command("/nEX")
    except Exception:
        pass  # Session may already be closed

    # Handle "unsaved data" popup if it appears
    try:
        popup = session.find_by_id("wnd[1]", raise_error=False)
        if popup is not None:
            cast(Any, popup).send_v_key(0)  # Confirm
    except Exception:
        pass  # Session closed after /nEX


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
    opt2 = session.find_by_id("wnd[1]/usr/radMULTI_LOGON_OPT2", raise_error=False)
    if opt2 is not None:
        cast(Any, opt2).selected = True
        cast(Any, session.find_by_id("wnd[1]")).send_v_key(0)  # Enter
        time.sleep(1)  # Wait for server to process
