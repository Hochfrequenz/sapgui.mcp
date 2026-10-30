"""Integration test for issue #789 against a live SAP system.

`get_session_status` now forces a real COM round-trip (`FindById` on wnd[0])
instead of reading only the cached `session.info`, so it reports "active" only
when a real action would actually succeed. This test guards the happy path: a
genuinely logged-in session must still report "active" via the stronger probe.

The dead-handle path (stale interface -> friendly remediation message) is
covered by mocked unit tests in ``unittests/test_get_session_status_per_id.py``
and ``unittests/desktop/test_com_thread.py``; reproducing a truly wedged COM
handle live requires corrupting the connection and is intentionally not done
against the shared system.
"""

from __future__ import annotations

import sys

import pytest
from dotenv import load_dotenv
from sapsucker.components.application import GuiApplication

from sapguimcp.models.config import get_sap_config
from unittests.desktop.conftest import skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_live_session_reports_active(backend):
    """A logged-in session passes the real-COM-round-trip health check."""
    result = await backend.get_session_status()

    assert result.success is True
    assert result.status == "active"
    assert "Logged in as" in result.message


class _FakeComError(Exception):
    """Stand-in for pywintypes.com_error: the HRESULT is ``args[0]``."""


async def _login_with_injected_open_connection_failure(backend, monkeypatch, error):
    """Run the real ``sap_login`` path with ``GuiApplication.open_connection`` raising *error*.

    Non-destructive: the patched method raises before any COM call, so no connection is opened
    and SAP Logon and the sessions already open are untouched.
    """

    def _raise(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(GuiApplication, "open_connection", _raise)
    load_dotenv()
    system = get_sap_config().get_default()
    return await backend.login(
        "x",
        system.user,
        system.password.get_secret_value(),
        system.client,
        system.language,
        connection_name=system.connection_name,
    )


@skip_no_sap
@pytest.mark.anyio
async def test_login_engine_lost_reports_hint_and_keeps_sessions(backend, monkeypatch):
    """Engine-lost cause: hint plus HRESULT, and the live session survives (no false prune)."""
    sessions_before = backend.registry.list_sessions()
    error = RuntimeError("Could not open connection '<name>'. Verify the name matches an entry in SAP Logon.")
    error.__cause__ = _FakeComError(-2147023174, "The RPC server is unavailable.", None, None)

    result = await _login_with_injected_open_connection_failure(backend, monkeypatch, error)

    assert result.success is False
    assert "SAP Logon not reachable or connection lost" in result.error
    assert "0x800706BA" in result.error
    assert backend.registry.list_sessions() == sessions_before


@skip_no_sap
@pytest.mark.anyio
async def test_login_unknown_entry_keeps_name_hint(backend, monkeypatch):
    """No COM cause: the text is unchanged and carries no engine-lost hint."""
    text = "Could not open connection '<name>'. Verify the name matches an entry in SAP Logon."
    sessions_before = backend.registry.list_sessions()

    result = await _login_with_injected_open_connection_failure(backend, monkeypatch, RuntimeError(text))

    assert result.success is False
    assert result.error == text
    assert backend.registry.list_sessions() == sessions_before
