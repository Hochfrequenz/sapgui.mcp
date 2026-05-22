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
from unittest.mock import AsyncMock, MagicMock

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
        async def passthrough(fn: Any) -> Any:
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

        async def passthrough(fn: Any) -> Any:
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

        async def passthrough(fn: Any) -> Any:
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

        async def passthrough(fn: Any) -> Any:
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

        async def failing_run(fn: Any) -> Any:
            raise RuntimeError("COM dead")

        backend.com.run = failing_run

        result = await backend.get_session_status(session_id="s1")
        assert result.status == "unknown"


class TestWebGuiGetSessionStatusPerID:
    """``WebGuiBackend.get_session_status(session_id=...)`` resolves the page from the registry.

    These tests build a WebGuiBackend via ``__new__`` and mock both
    ``_get_registry`` and ``_find_okcode_field`` so the test runs without a
    real Playwright browser.
    """

    @staticmethod
    def _make_backend() -> Any:
        from sapguimcp.backend.webgui.backend import WebGuiBackend

        backend = WebGuiBackend.__new__(WebGuiBackend)
        backend._page = MagicMock()
        backend._keepalive_task = None
        return backend

    @staticmethod
    def _make_mock_page(*, closed: bool = False) -> MagicMock:
        page = MagicMock()
        page.is_closed.return_value = closed
        return page

    @pytest.mark.anyio
    async def test_explicit_session_id_probes_that_session(self) -> None:
        """Issue #640: passing session_id="s2" must resolve s2's page from the registry."""
        from unittest.mock import patch

        backend = self._make_backend()

        # Two distinct page mocks; the registry returns the right one for each ID.
        primary_page = self._make_mock_page()
        s2_page = self._make_mock_page()

        registry = MagicMock()
        registry.primary_session = "s1"

        def _get_page(sid: str) -> Any:
            return {"s1": primary_page, "s2": s2_page}[sid]

        registry.get_page.side_effect = _get_page

        # Mock _find_okcode_field to return truthy iff called with s2_page.
        # Patching on the class means Python passes ``self`` positionally
        # before our kwargs, so the fake must accept it.
        async def fake_find(_self: Any, page: Any = None) -> Any:
            return "okcode-handle" if page is s2_page else None

        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_find_okcode_field", new=fake_find),
        ):
            result = await backend.get_session_status(session_id="s2")

        assert result.status == "active"
        registry.get_page.assert_called_with("s2")

    @pytest.mark.anyio
    async def test_none_uses_primary_session(self) -> None:
        """``session_id=None`` resolves to ``registry.primary_session``."""
        from unittest.mock import patch

        backend = self._make_backend()
        primary_page = self._make_mock_page()

        registry = MagicMock()
        registry.primary_session = "s1"
        registry.get_page.return_value = primary_page

        async def fake_find(_self: Any, page: Any = None) -> Any:  # noqa: ARG001
            return "okcode-handle"

        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)),
            patch.object(type(backend), "_find_okcode_field", new=fake_find),
        ):
            result = await backend.get_session_status()

        assert result.status == "active"
        registry.get_page.assert_called_with("s1")

    @pytest.mark.anyio
    async def test_unknown_session_id_returns_no_page(self) -> None:
        """Asking for a session not in the registry → no_page (graceful)."""
        from unittest.mock import patch

        backend = self._make_backend()
        registry = MagicMock()
        registry.primary_session = "s1"
        registry.get_page.side_effect = ValueError("Session 's99' not found")

        with patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)):
            result = await backend.get_session_status(session_id="s99")

        assert result.status == "no_page"
        assert "s99" in result.message or "not found" in result.message

    @pytest.mark.anyio
    async def test_closed_page_returns_no_page(self) -> None:
        """A registry-resolved page that is already closed → no_page."""
        from unittest.mock import patch

        backend = self._make_backend()
        closed_page = self._make_mock_page(closed=True)

        registry = MagicMock()
        registry.primary_session = "s1"
        registry.get_page.return_value = closed_page

        with patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=registry)):
            result = await backend.get_session_status(session_id="s1")

        assert result.status == "no_page"

    @pytest.mark.anyio
    async def test_get_registry_failure_returns_unknown(self) -> None:
        """Browser-manager init failure surfaces as ``unknown``, not a crash.

        Locks in the merged-try semantics: ``_get_registry`` errors are now
        caught by the broad-exception handler and converted to a
        ``SessionStatus(status="unknown", ...)`` rather than propagating to
        the tool wrapper. Without ``self._page`` available either, there's
        nothing to fall back to.
        """
        from unittest.mock import patch

        backend = self._make_backend()
        backend._page = None  # so _resolve_status_page can't fall back

        with patch.object(
            type(backend),
            "_get_registry",
            new=AsyncMock(side_effect=RuntimeError("browser manager dead")),
        ):
            result = await backend.get_session_status(session_id="s1")

        assert result.status in ("no_page", "unknown")
        # No crash — that's the contract.

    @pytest.mark.anyio
    async def test_pre_init_falls_back_to_self_page(self) -> None:
        """Pre-_post_login_setup state falls back to ``self._page``.

        Backwards-compat regression guard: a ``WebGuiBackend`` constructed
        with ``self._page`` set but with no entry in the registry yet
        (e.g. ``__init__`` ran but ``_post_login_setup`` hasn't, or the
        registry was just cleared) must still be able to probe ``self._page``
        directly. Without this fallback, a pre-login
        ``sap_session_status()`` call would return ``no_page`` instead of
        the more useful ``logged_off`` (login-form-detected) status.
        """
        from unittest.mock import patch

        backend = self._make_backend()
        # self._page is the pre-init page (set by __init__) — assume it
        # would detect a login form and return ``logged_off``.
        backend._page = self._make_mock_page()
        backend._page.query_selector = AsyncMock(return_value="login-form-handle")

        # Registry is empty: get_page raises ValueError on every lookup.
        empty_registry = MagicMock()
        empty_registry.primary_session = "s1"
        empty_registry.get_page.side_effect = ValueError("Session 's1' not found")

        async def fake_find(_self: Any, page: Any = None) -> Any:  # noqa: ARG001
            return None  # no okcode → fall through to login_form check

        with (
            patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=empty_registry)),
            patch.object(type(backend), "_find_okcode_field", new=fake_find),
        ):
            result = await backend.get_session_status()  # no session_id → fallback

        assert result.status == "logged_off"

    @pytest.mark.anyio
    async def test_pre_init_with_explicit_id_does_not_fall_back(self) -> None:
        """Negative: ``session_id="s2"`` must NOT silently fall back to ``self._page``.

        The fallback to ``self._page`` only kicks in when no explicit
        session was requested. An explicit ID that doesn't exist is a real
        not-found error and must surface as ``no_page``.
        """
        from unittest.mock import patch

        backend = self._make_backend()
        backend._page = self._make_mock_page()  # would be alive if probed

        empty_registry = MagicMock()
        empty_registry.primary_session = "s1"
        empty_registry.get_page.side_effect = ValueError("Session 's2' not found")

        with patch.object(type(backend), "_get_registry", new=AsyncMock(return_value=empty_registry)):
            result = await backend.get_session_status(session_id="s2")

        assert result.status == "no_page"
        assert "s2" in result.message or "not found" in result.message
