"""Low-level COM helpers for connecting to SAP GUI."""

# pylint: disable=import-outside-toplevel,invalid-name

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from sapwebguimcp.sapgui._errors import SapConnectionError, SapGuiTimeoutError, ScriptingDisabledError

try:
    import pythoncom  # type: ignore[import-untyped]
    import win32com.client  # type: ignore[import-untyped]
except ImportError:
    pythoncom = None
    win32com = None

if TYPE_CHECKING:
    from sapwebguimcp.sapgui.components.application import GuiApplication


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

    from sapwebguimcp.sapgui.components.application import GuiApplication

    return GuiApplication(engine)


def _check_scripting_not_disabled(engine: Any) -> None:
    """Raise ScriptingDisabledError if every connection has scripting disabled.

    When sapgui/user_scripting=FALSE on the SAP server, the COM connection
    exists but DisabledByServer=True on each GuiConnection. The Children
    collection appears empty and all FindById calls fail silently.
    """
    try:
        connections = engine.Children
        count = connections.Count
        if count == 0:
            return  # No connections yet — nothing to check
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
