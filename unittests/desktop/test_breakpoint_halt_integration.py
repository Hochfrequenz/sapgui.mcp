"""Integration test: a hit ABAP breakpoint must not freeze the desktop backend.

Running ABAP that stops at an external breakpoint used to block the single COM worker
until a human finished in the ABAP debugger — every later tool call hung, and the
session registry collapsed to empty. Requires SAP GUI with the desktop backend.
"""

import asyncio
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

pytestmark = [skip_no_sap, pytest.mark.integration]


def _continue_debugger_like_a_human() -> None:
    """Press F8 (continue) in the ABAP debugger via raw COM, as the human at SAP GUI would."""
    import pythoncom  # noqa: PLC0415  # pylint: disable=import-outside-toplevel  # Windows-only
    import win32com.client  # noqa: PLC0415  # pylint: disable=import-outside-toplevel  # Windows-only

    pythoncom.CoInitialize()
    app = win32com.client.GetObject("SAPGUI").GetScriptingEngine
    for connection_index in range(app.Children.Count):
        connection = app.Children(connection_index)
        for session_index in range(connection.Children.Count):
            session = connection.Children(session_index)
            if not session.Busy and session.Info.Program == "RSTPDAMAIN":
                session.FindById("wnd[0]").SendVKey(8)  # may block until the program ends
                return


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
        threading.Thread(target=_continue_debugger_like_a_human, daemon=True).start()
        deadline = time.monotonic() + 60
        while True:
            await asyncio.sleep(2)
            screen = await asyncio.wait_for(backend.get_screen_info(), timeout=30)
            if screen.success or time.monotonic() > deadline:
                break
        assert screen.success, f"session did not recover: {screen.error}"
    finally:
        assert await _toggle_breakpoint(backend, line) == "deleted"
        await go_home(backend)
