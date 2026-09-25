"""Integration test: a hit ABAP breakpoint must not freeze the desktop backend.

Running ABAP that stops at an external breakpoint used to block the single COM worker
until a human finished in the ABAP debugger — every later tool call hung, and the
session registry collapsed to empty. Requires SAP GUI with the desktop backend.
"""

import asyncio
import os
import threading
import time

import pytest

from sapguimcp.backend.desktop._com_thread import SapSessionHaltedError
from sapguimcp.tools.breakpoint_tools import (
    _classify_toggle_status,
    _navigate_prog,
    _resolve_line_number,
    _resolve_shell_path_com,
    _toggle_breakpoint_com,
)
from unittests.desktop.conftest import TEST_REPORT, go_home, skip_no_sap

# Opt-in: really halting ABAP in the debugger leaves SAP GUI degraded for the rest of the
# SAP Logon process (the continued debugger session stays busy), and later modules of a
# full run then lose their sessions to RPC errors. Run it on its own:
#   SAPGUIMCP_RUN_DEBUGGER_TESTS=1 pytest unittests/desktop/test_breakpoint_halt_integration.py
pytestmark = [
    skip_no_sap,
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("SAPGUIMCP_RUN_DEBUGGER_TESTS") != "1",
        reason="halts ABAP in the debugger; set SAPGUIMCP_RUN_DEBUGGER_TESTS=1 and run on its own",
    ),
]


class _HumanAtTheDebugger(threading.Thread):
    """Presses F8 (continue) in the ABAP debugger via raw COM, as the human at SAP GUI would.

    That SendVKey can stay pending inside SAP GUI long after the program has finished;
    a call left dangling for the rest of the test run degrades SAP GUI for later modules.
    So the thread enables COM call cancellation, and ``finish`` cancels whatever is
    still pending and joins it.
    """

    def __init__(self) -> None:
        super().__init__(daemon=True, name="human-at-the-debugger")
        self.native_id_ready = threading.Event()
        self.error: Exception | None = None

    def run(self) -> None:
        import ctypes  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        import pythoncom  # noqa: PLC0415  # pylint: disable=import-outside-toplevel  # Windows-only
        import win32com.client  # noqa: PLC0415  # pylint: disable=import-outside-toplevel  # Windows-only

        pythoncom.CoInitialize()
        ctypes.windll.ole32.CoEnableCallCancellation(None)
        self.native_id_ready.set()
        try:
            app = win32com.client.GetObject("SAPGUI").GetScriptingEngine
            for connection_index in range(app.Children.Count):
                connection = app.Children(connection_index)
                for session_index in range(connection.Children.Count):
                    session = connection.Children(session_index)
                    if not session.Busy and session.Info.Program == "RSTPDAMAIN":
                        session.FindById("wnd[0]").SendVKey(8)
                        return
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # cancelled by finish(), or the debugger was gone already
            self.error = exc
        finally:
            pythoncom.CoUninitialize()

    def finish(self) -> None:
        import ctypes  # noqa: PLC0415  # pylint: disable=import-outside-toplevel

        self.native_id_ready.wait(5)
        for _ in range(10):
            if not self.is_alive():
                return
            ctypes.windll.ole32.CoCancelCall(self.native_id, 0)
            self.join(1)


async def _toggle_breakpoint(backend, line: int) -> str | None:  # type: ignore[no-untyped-def]
    nav_error = await _navigate_prog(backend, TEST_REPORT)
    assert nav_error is None, f"Navigation failed: {nav_error}"
    session = backend.require_session()
    shell_path = await backend.com.run(lambda: _resolve_shell_path_com(session, "PROG"))
    assert shell_path is not None, "Editor shell not found"
    shell_found, status = await backend.com.run(lambda: _toggle_breakpoint_com(session, shell_path, line))
    assert shell_found, status
    return _classify_toggle_status(status)


@pytest.mark.anyio
async def test_hit_breakpoint_does_not_freeze_the_backend(backend):  # type: ignore[no-untyped-def]
    nav_error = await _navigate_prog(backend, TEST_REPORT)
    assert nav_error is None, f"Navigation failed: {nav_error}"
    line, resolve_error = await _resolve_line_number(backend, None, "WRITE")
    assert line is not None, resolve_error

    outcome = await _toggle_breakpoint(backend, line)
    if outcome == "deleted":  # was already set: toggle back on
        outcome = await _toggle_breakpoint(backend, line)
    assert outcome == "set"
    try:
        # Running the report from the editor hits the breakpoint.
        started = time.monotonic()
        result = await asyncio.wait_for(backend.press_key("F8"), timeout=30)
        assert time.monotonic() - started < 15, "the halted call must be cancelled within seconds"
        assert result.success is False
        assert "ABAP breakpoint" in (result.error or "")

        # The session stays registered and is reported as halted, not dropped (#791).
        sessions = await asyncio.wait_for(backend.list_sessions(), timeout=30)
        assert [s.session_id for s in sessions] == ["s1"]
        assert sessions[0].halted_at_breakpoint

        with pytest.raises(SapSessionHaltedError):
            await asyncio.wait_for(backend.com.run(lambda: backend.require_session().com.Info.Program), timeout=30)

        # Once the human continues the debugger, the same session works again — no re-login.
        human = _HumanAtTheDebugger()
        human.start()
        try:
            deadline = time.monotonic() + 60
            while True:
                await asyncio.sleep(2)
                screen = await asyncio.wait_for(backend.get_screen_info(), timeout=30)
                if screen.success or time.monotonic() > deadline:
                    break
        finally:
            human.finish()
        assert screen.success, f"session did not recover: {screen.error}"
        assert not human.is_alive(), "the debugger call must not be left pending in SAP GUI"
    finally:
        assert await _toggle_breakpoint(backend, line) == "deleted"
        await go_home(backend)
