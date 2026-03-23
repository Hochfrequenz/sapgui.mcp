"""Low-level COM helpers for connecting to SAP GUI.

Thread Safety
-------------
COM objects use the Single-Threaded Apartment (STA) model.  All calls to a
given SAP GUI session **must** happen from the same thread that called
``pythoncom.CoInitialize()``.  Creating COM objects on one thread and using
them on another will raise ``pywintypes.com_error`` or cause silent
corruption.

If you use sapsucker from async code, run all COM calls in a dedicated thread
via ``asyncio.to_thread()`` or a ``concurrent.futures.ThreadPoolExecutor``.
Each worker thread must call ``pythoncom.CoInitialize()`` before its first
COM operation and ``pythoncom.CoUninitialize()`` when done.

Example::

    import asyncio, pythoncom
    from sapsucker import SapGui

    def _read_status_bar() -> str:
        pythoncom.CoInitialize()
        try:
            app = SapGui.connect()
            session = app.connections[0].sessions[0]
            return session.find_by_id("wnd[0]/sbar").text
        finally:
            pythoncom.CoUninitialize()

    text = asyncio.run(asyncio.to_thread(_read_status_bar))
"""

# pylint: disable=import-outside-toplevel,invalid-name

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sapsucker._errors import SapConnectionError, SapGuiTimeoutError, ScriptingDisabledError

try:
    import pythoncom  # type: ignore[import-untyped]
    import win32com.client  # type: ignore[import-untyped]
except ImportError:
    pythoncom = None
    win32com = None

if TYPE_CHECKING:
    from sapsucker.components.application import GuiApplication


def _connect_to_running_sap_gui() -> GuiApplication:
    """Connect to an already-running SAP GUI instance via the ROT entry.

    Returns:
        A GuiApplication wrapping the SAP GUI Scripting engine.

    Raises:
        SapConnectionError: If SAP GUI is not running.
        ScriptingDisabledError: If the scripting engine is not available.
    """
    if pythoncom is not None:
        pythoncom.CoInitialize()  # pylint: disable=no-member
    try:
        rot_entry = win32com.client.GetObject("SAPGUI")
    except Exception as e:
        raise SapConnectionError("SAP GUI is not running or scripting is disabled") from e
    engine = rot_entry.GetScriptingEngine
    if engine is None:
        raise ScriptingDisabledError("Scripting engine not available — check server parameter sapgui/user_scripting")

    # Check if all connections have scripting disabled by the server
    _check_scripting_not_disabled(engine)

    from sapsucker.components.application import GuiApplication

    return GuiApplication(engine)


def _check_scripting_not_disabled(engine: Any) -> None:
    """Raise ScriptingDisabledError if every connection has scripting disabled.

    When sapgui/user_scripting=FALSE on the SAP server, the COM connection
    exists but DisabledByServer=True on each GuiConnection. The Children
    collection appears empty and all FindById calls fail silently.

    Ghost connections (0 sessions) are cleaned up first — they are stale
    leftovers from server restarts or failed connections and should not
    block new login attempts.
    """
    try:
        connections = engine.Children
        count = connections.Count
        if count == 0:
            return  # No connections yet — nothing to check

        # Clean up ghost connections (0 sessions) before checking
        for i in range(count - 1, -1, -1):
            conn = connections(i)
            if conn.Children.Count == 0:
                try:
                    conn.CloseConnection()
                except Exception:
                    pass

        # Re-read after cleanup
        count = connections.Count
        if count == 0:
            return  # Only ghosts were present — all cleaned up

        disabled_count = sum(1 for i in range(count) if connections(i).DisabledByServer)
        if disabled_count == count:
            raise ScriptingDisabledError(
                f"SAP GUI Scripting is disabled on the server (all {count} connection(s) have "
                f"DisabledByServer=True). Fix: run transaction RZ11, change parameter "
                f"'sapgui/user_scripting' to TRUE, then re-login."
            )
    except ScriptingDisabledError:
        raise
    except Exception:  # pylint: disable=broad-exception-caught
        pass  # COM access failed — don't block connection for a diagnostic check


def _wait_for_sap_gui(timeout: int = 30) -> GuiApplication:
    """Poll until SAP GUI is reachable or *timeout* seconds elapse.

    Returns:
        A GuiApplication wrapping the SAP GUI Scripting engine.

    Raises:
        SapGuiTimeoutError: If SAP GUI is still not available after *timeout* seconds.
    """
    deadline = time.monotonic() + timeout
    last_err: SapConnectionError | None = None
    while time.monotonic() < deadline:
        try:
            return _connect_to_running_sap_gui()
        except SapConnectionError as e:
            last_err = e
            time.sleep(1)
    raise SapGuiTimeoutError(f"SAP GUI not available after {timeout}s") from last_err
