"""Unit tests for ``get_session_status(session_id=...)`` on both backends.

Regression tests for issue #640: previously the desktop and webgui
``get_session_status`` methods only ever probed the *primary* session
(``self._session`` / ``self._page``), so calls like
``sap_session_status(session="s2")`` silently reported on s1 even though
the MCP tool wrapper accepted the parameter.

These tests verify the per-id path on both backends without needing a
real SAP system.
"""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry


def _make_desktop_backend() -> DesktopBackend:
    """Build a DesktopBackend with a fresh registry, mocked ComThread."""
    backend = DesktopBackend.__new__(DesktopBackend)
    backend.registry = DesktopSessionRegistry()
    backend.com = MagicMock()
    backend._mutation_lock = asyncio.Lock()
    return backend


def _make_mock_gui_session(user: str = "TESTUSER") -> MagicMock:
    """Create a mock GuiSession that resolves ``info.user`` to ``user``."""
    session = MagicMock()
    session.info.user = user
    return session


class TestDesktopGetSessionStatusPerID:
    """``DesktopBackend.get_session_status(session_id=...)`` probes the requested session."""

    @pytest.mark.anyio
    async def test_explicit_session_id_probes_that_session(self) -> None:
        """Issue #640: passing session_id="s2" must probe s2, not s1."""
        backend = _make_desktop_backend()
        s1 = _make_mock_gui_session(user="USER_S1")
        s2 = _make_mock_gui_session(user="USER_S2")
        backend.registry.register(s1)
        backend.registry.register(s2)

        # Pass-through com.run that just calls the lambda.
        async def passthrough(fn: Any, **kwargs: Any) -> Any:
            return fn()

        backend.com.run = passthrough

        result = await backend.get_session_status(session_id="s2")

        assert result.status == "active"
        assert "USER_S2" in result.message

    @pytest.mark.anyio
    async def test_explicit_session_id_does_not_probe_primary(self) -> None:
        """Negative: probing s2 must NOT touch s1 even if it would also be alive."""
        backend = _make_desktop_backend()
        s1 = _make_mock_gui_session(user="PRIMARY")
        s2 = _make_mock_gui_session(user="SECOND")
        backend.registry.register(s1)
        backend.registry.register(s2)

        async def passthrough(fn: Any, **kwargs: Any) -> Any:
            return fn()

        backend.com.run = passthrough

        result = await backend.get_session_status(session_id="s2")
        assert "PRIMARY" not in result.message
        assert "SECOND" in result.message

    @pytest.mark.anyio
    async def test_none_falls_back_to_require_session(self) -> None:
        """``session_id=None`` keeps the existing ContextVar routing behaviour."""
        backend = _make_desktop_backend()
        s1 = _make_mock_gui_session(user="DEFAULT")
        backend.registry.register(s1)

        async def passthrough(fn: Any, **kwargs: Any) -> Any:
            return fn()

        backend.com.run = passthrough

        result = await backend.get_session_status()  # no session_id
        assert result.status == "active"
        assert "DEFAULT" in result.message

    @pytest.mark.anyio
    async def test_none_with_contextvar_routes_to_correct_session(self) -> None:
        """ContextVar fallback path actually routes to the per-call session.

        Without this test, ``test_none_falls_back_to_require_session`` only
        proves the no-session-id path works against a single registered
        session — it doesn't prove the ContextVar is being read at all.
        Here we register two sessions and set the ContextVar to s2, then
        assert the probe ran against s2's user, not s1's.
        """
        from sapguimcp.backend.desktop import _current_session_id

        backend = _make_desktop_backend()
        s1 = _make_mock_gui_session(user="USER_S1")
        s2 = _make_mock_gui_session(user="USER_S2")
        backend.registry.register(s1)
        backend.registry.register(s2)

        async def passthrough(fn: Any, **kwargs: Any) -> Any:
            return fn()

        backend.com.run = passthrough

        token = _current_session_id.set("s2")
        try:
            result = await backend.get_session_status()  # no explicit id
        finally:
            _current_session_id.reset(token)

        assert result.status == "active"
        assert "USER_S2" in result.message
        assert "USER_S1" not in result.message

    @pytest.mark.anyio
    async def test_empty_registry_returns_logged_off(self) -> None:
        """No sessions at all → logged_off, regardless of session_id arg."""
        backend = _make_desktop_backend()

        result = await backend.get_session_status()
        assert result.status == "logged_off"

    @pytest.mark.anyio
    async def test_unknown_session_id_returns_logged_off(self) -> None:
        """Asking for a session that doesn't exist surfaces as logged_off."""
        backend = _make_desktop_backend()
        backend.registry.register(_make_mock_gui_session())

        result = await backend.get_session_status(session_id="s99")
        assert result.status == "logged_off"

    @pytest.mark.anyio
    async def test_com_failure_returns_unknown(self) -> None:
        """A live registry entry whose probe raises → unknown."""
        backend = _make_desktop_backend()
        backend.registry.register(_make_mock_gui_session())

        async def failing_run(fn: Any, **kwargs: Any) -> Any:
            raise RuntimeError("COM dead")

        backend.com.run = failing_run

        result = await backend.get_session_status(session_id="s1")
        assert result.status == "unknown"


class _FakeComError(Exception):
    """Stand-in for pywintypes.com_error (HRESULT in args[0])."""


class TestDesktopGetSessionStatusHealthCheck:
    """Issue #789: status must reflect a real COM round-trip, not cached info.

    ``session.info`` returns cached values even for a dead window, so probing
    ``info.user`` alone reports a stale handle as "active". The probe must
    force a real COM call (FindById on wnd[0]) so a dead handle is detected,
    and a known fatal COM error must surface an actionable message.
    """

    @staticmethod
    def _register(backend: DesktopBackend, session: Any) -> None:
        backend.registry.register(session)

        async def passthrough(fn: Any, **kwargs: Any) -> Any:
            return fn()

        backend.com.run = passthrough

    @pytest.mark.anyio
    async def test_stale_handle_not_reported_active(self) -> None:
        backend = _make_desktop_backend()
        session = MagicMock()
        session.info.user = "GHOST"  # cached value survives on a dead handle
        session.com.FindById.side_effect = _FakeComError(-2147023179, "Die Schnittstelle ist unbekannt.", None, None)
        self._register(backend, session)

        result = await backend.get_session_status(session_id="s1")

        assert result.status != "active"
        assert result.status == "dead"  # #789: reported dead, not unknown
        assert "GHOST" not in result.message
        assert "sap_login" in result.message.lower()

    @pytest.mark.anyio
    async def test_disconnected_handle_reported_dead_and_kept_registered(self) -> None:
        backend = _make_desktop_backend()
        session = MagicMock()
        session.com.FindById.side_effect = _FakeComError(-2147417848, "disconnected", None, None)
        self._register(backend, session)

        result = await backend.get_session_status(session_id="s1")

        assert result.status == "dead"
        assert backend.registry.has_session("s1")  # the next call deregisters it

    @pytest.mark.anyio
    async def test_live_handle_reported_active(self) -> None:
        backend = _make_desktop_backend()
        session = MagicMock()
        session.info.user = "TESTUSER"
        session.com.FindById.return_value = MagicMock()  # round-trip succeeds
        self._register(backend, session)

        result = await backend.get_session_status(session_id="s1")

        assert result.status == "active"
        assert "TESTUSER" in result.message

    @pytest.mark.anyio
    async def test_busy_handle_reported_not_dead(self) -> None:
        backend = _make_desktop_backend()
        session = MagicMock()
        session.info.user = "BUSY"
        session.com.FindById.side_effect = _FakeComError(
            -2147417846,
            "server call retry later",
            None,
            None,  # RPC_E_SERVERCALL_RETRYLATER (0x8001010A)
        )
        self._register(backend, session)

        result = await backend.get_session_status(session_id="s1")

        assert result.status != "active"
        assert "busy" in result.message.lower()

    @pytest.mark.anyio
    async def test_server_fault_handle_reported_unknown_not_busy_not_dead(self) -> None:
        backend = _make_desktop_backend()
        session = MagicMock()
        session.com.FindById.side_effect = _FakeComError(-2147417851, "server threw", None, None)  # SERVERFAULT
        self._register(backend, session)

        result = await backend.get_session_status(session_id="s1")

        assert result.status == "unknown"
        assert "server fault" in result.message.lower()
        assert "busy" not in result.message.lower()

    @pytest.mark.anyio
    async def test_probe_disables_retries(self) -> None:
        """The liveness probe must fail fast — com.run is called with
        max_retries=0 so a dead RPC_S_UNKNOWN_IF interface is not retried."""
        backend = _make_desktop_backend()
        session = MagicMock()
        session.info.user = "X"
        session.com.FindById.return_value = MagicMock()
        backend.registry.register(session)

        captured: dict[str, Any] = {}

        async def capturing(fn: Any, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return fn()

        backend.com.run = capturing

        await backend.get_session_status(session_id="s1")

        assert captured.get("max_retries") == 0

    @pytest.mark.anyio
    async def test_wedged_probe_times_out_to_unknown(self) -> None:
        """A COM thread that never returns must not hang get_session_status."""
        backend = _make_desktop_backend()
        session = MagicMock()
        session.info.user = "X"
        backend.registry.register(session)

        async def hang(fn: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(10)
            return fn()

        backend.com.run = hang
        backend._STATUS_PROBE_TIMEOUT_S = 0.05  # shrink so the test is fast

        result = await backend.get_session_status(session_id="s1")

        assert result.status == "unknown"
        assert "did not respond" in result.message.lower()
