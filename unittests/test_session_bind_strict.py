"""Unit tests for strict session-bind semantics (issue #643).

PR #638 added visibility/recovery for parallel-agent drift. PR #645 fixed
``sap_session_status`` per-id routing. This change tightens session
*reservation*: ``bind()`` is now strict by default — a second agent
trying to claim the same session is rejected with
``SessionBindConflictError`` instead of silently overwriting the
previous binding.

Tests cover both registries (desktop and webgui), the backend
``bind_session`` wrappers, and the ``sap_session_bind_impl`` tool entry
point — both happy paths and the new strict-conflict failure paths.
"""

# pylint: disable=protected-access

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry
from sapguimcp.backend.webgui.models.session_registry import SessionRegistry
from sapguimcp.models.base import SessionBindConflictError


def _make_mock_gui_session() -> MagicMock:
    """Mock GuiSession for the desktop registry."""
    session = MagicMock()
    session.com.Info.Transaction = "SE00"
    return session


def test_session_bind_conflict_error_is_single_class() -> None:
    """Both backends must raise the *same* exception class, not look-alike duplicates.

    A single ``except SessionBindConflictError`` clause should catch a raise
    from either backend's registry. If a future refactor accidentally defines
    a separate copy in the desktop module, this test fails immediately.
    """
    from sapguimcp.backend.desktop._session_registry import SessionBindConflictError as Desktop
    from sapguimcp.models.base import SessionBindConflictError as Base

    assert Desktop is Base


def _make_mock_page() -> MagicMock:
    """Mock Playwright Page for the webgui registry."""
    page = MagicMock()
    page.is_closed.return_value = False
    page.on = MagicMock()
    return page


# ---------------------------------------------------------------------------
# DesktopSessionRegistry — strict bind
# ---------------------------------------------------------------------------


class TestDesktopRegistryBindStrict:
    """Strict-by-default bind on DesktopSessionRegistry."""

    def test_bind_unbound_session_succeeds(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a")
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_rebind_same_agent_is_idempotent(self) -> None:
        """Binding the same agent twice must succeed (idempotent), no exception."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a")
        reg.bind("s1", "agent_a")  # second bind, same agent — must NOT raise
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_bind_conflict_raises(self) -> None:
        """Strict default: second agent gets SessionBindConflictError."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a")
        with pytest.raises(SessionBindConflictError) as exc_info:
            reg.bind("s1", "agent_b")
        assert exc_info.value.session_id == "s1"
        assert exc_info.value.current_agent == "agent_a"
        assert exc_info.value.requested_agent == "agent_b"
        # Original binding must NOT have been clobbered.
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_bind_conflict_force_takes_over(self) -> None:
        """force=True bypasses the strict check and replaces the binding."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a")
        reg.bind("s1", "agent_b", force=True)
        assert reg.get_bound_agent("s1") == "agent_b"

    def test_force_on_unbound_is_a_no_op_extra(self) -> None:
        """force=True on an unbound session is just a regular bind."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a", force=True)
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_release_then_rebind_different_agent(self) -> None:
        """After release, a different agent can bind without force."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a")
        reg.release("s1")
        reg.bind("s1", "agent_b")  # no conflict, should succeed
        assert reg.get_bound_agent("s1") == "agent_b"

    def test_prune_clears_binding_implicitly(self) -> None:
        """#643 contract: pruning a session also drops its binding.

        Documented in ``DesktopSessionRegistry.prune`` docstring; this test
        locks in the contract so a future refactor doesn't break it.
        """
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_gui_session())
        reg.bind("s1", "agent_a")
        reg.prune(["s1"])
        assert reg.get_bound_agent("s1") is None


# ---------------------------------------------------------------------------
# SessionRegistry (webgui) — strict bind
# ---------------------------------------------------------------------------


class TestWebGuiRegistryBindStrict:
    """Strict-by-default bind on the webgui SessionRegistry — parity with desktop."""

    def test_bind_unbound_session_succeeds(self) -> None:
        reg = SessionRegistry()
        page = _make_mock_page()
        reg.register(page)
        reg.bind("s1", "agent_a")
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_rebind_same_agent_is_idempotent(self) -> None:
        reg = SessionRegistry()
        reg.register(_make_mock_page())
        reg.bind("s1", "agent_a")
        reg.bind("s1", "agent_a")
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_bind_conflict_raises(self) -> None:
        reg = SessionRegistry()
        reg.register(_make_mock_page())
        reg.bind("s1", "agent_a")
        with pytest.raises(SessionBindConflictError) as exc_info:
            reg.bind("s1", "agent_b")
        assert exc_info.value.current_agent == "agent_a"
        assert reg.get_bound_agent("s1") == "agent_a"  # not clobbered

    def test_bind_conflict_force_takes_over(self) -> None:
        reg = SessionRegistry()
        reg.register(_make_mock_page())
        reg.bind("s1", "agent_a")
        reg.bind("s1", "agent_b", force=True)
        assert reg.get_bound_agent("s1") == "agent_b"

    def test_force_on_unbound_is_a_no_op_extra(self) -> None:
        """force=True on an unbound session is just a regular bind.

        Parity test for ``TestDesktopRegistryBindStrict.test_force_on_unbound_is_a_no_op_extra``.
        Without this, a future bug in the webgui registry's bind() that
        mishandled the ``current is None`` branch could go unnoticed.
        """
        reg = SessionRegistry()
        reg.register(_make_mock_page())
        reg.bind("s1", "agent_a", force=True)
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_release_then_rebind_different_agent(self) -> None:
        """After release, a different agent can bind without force.

        Parity test for the desktop equivalent. Verifies ``release`` is a
        real release (not a soft-mark that still trips the strict check).
        """
        reg = SessionRegistry()
        reg.register(_make_mock_page())
        reg.bind("s1", "agent_a")
        reg.release("s1")
        reg.bind("s1", "agent_b")  # no conflict, should succeed
        assert reg.get_bound_agent("s1") == "agent_b"

    def test_unregister_clears_binding_implicitly(self) -> None:
        """Webgui contract: unregister() clears the binding as a side effect.

        Parallel to ``DesktopSessionRegistry.prune()``'s auto-clear contract
        (the desktop registry uses ``prune`` for batch removal; the webgui
        registry uses ``unregister`` directly via the page-close listener).
        Both must drop bindings on session removal so future re-registers
        of the same SID start clean. Verified at
        ``models/session_registry.py:82`` (``self._bindings.pop(session_id, None)``
        inside the unregister body).
        """
        reg = SessionRegistry()
        reg.register(_make_mock_page())
        reg.bind("s1", "agent_a")
        reg.unregister("s1")
        assert reg.get_bound_agent("s1") is None


# ---------------------------------------------------------------------------
# Backend bind_session wrappers
# ---------------------------------------------------------------------------


class TestDesktopBackendBindSessionStrict:
    """``DesktopBackend.bind_session`` propagates the conflict from the registry."""

    @staticmethod
    def _make_backend() -> Any:
        from sapguimcp.backend.desktop import DesktopBackend

        backend = DesktopBackend.__new__(DesktopBackend)
        backend.registry = DesktopSessionRegistry()
        backend.com = MagicMock()
        return backend

    @pytest.mark.anyio
    async def test_conflict_raises_through_backend(self) -> None:
        backend = self._make_backend()
        backend.registry.register(_make_mock_gui_session())
        await backend.bind_session("s1", "agent_a")
        with pytest.raises(SessionBindConflictError):
            await backend.bind_session("s1", "agent_b")

    @pytest.mark.anyio
    async def test_force_overrides_through_backend(self) -> None:
        backend = self._make_backend()
        backend.registry.register(_make_mock_gui_session())
        await backend.bind_session("s1", "agent_a")
        prev = await backend.bind_session("s1", "agent_b", force=True)
        assert prev == "agent_a"
        assert backend.registry.get_bound_agent("s1") == "agent_b"


# ---------------------------------------------------------------------------
# Tool wrapper — sap_session_bind_impl
# ---------------------------------------------------------------------------


_PATCH_GET_BACKEND = "sapguimcp.tools.session_tools.get_backend"


def _make_tool_backend(*, has: bool = True, conflict: SessionBindConflictError | None = None) -> AsyncMock:
    """Mock backend for tool-wrapper tests.

    If ``conflict`` is provided, ``bind_session`` raises it instead of
    returning. Otherwise it returns ``None`` (no previous agent).
    """
    backend = AsyncMock()
    backend.has_session.return_value = has
    backend.list_sessions.return_value = []
    if conflict is not None:
        backend.bind_session.side_effect = conflict
    else:
        backend.bind_session.return_value = None
    return backend


class TestSapSessionBindImplStrict:
    """The MCP tool wrapper surfaces SessionBindConflictError as a clean failure."""

    @pytest.mark.anyio
    async def test_happy_path_default(self) -> None:
        """Strict bind on an unbound session returns success."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_tool_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s2", "agent_a")

        assert result.success is True
        assert result.session_id == "s2"
        assert result.agent_id == "agent_a"
        backend.bind_session.assert_awaited_once_with("s2", "agent_a", force=False)

    @pytest.mark.anyio
    async def test_conflict_returns_failure_with_helpful_message(self) -> None:
        """Strict-conflict case returns failure with both recovery options spelled out."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        conflict = SessionBindConflictError(
            session_id="s2",
            current_agent="agent_a",
            requested_agent="agent_b",
        )
        backend = _make_tool_backend(conflict=conflict)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s2", "agent_b")

        assert result.success is False
        # The error message must contain both recovery hints so the LLM
        # can adapt its strategy without needing to read source.
        assert "agent_a" in result.error
        assert "force=true" in result.error.lower()
        assert "sap_session_list" in result.error.lower()

    @pytest.mark.anyio
    async def test_force_true_propagates(self) -> None:
        """force=True is passed through to backend.bind_session."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_tool_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s2", "agent_b", force=True)

        assert result.success is True
        backend.bind_session.assert_awaited_once_with("s2", "agent_b", force=True)

    @pytest.mark.anyio
    async def test_unknown_session_returns_not_found(self) -> None:
        """Pre-existing not-found behaviour is preserved."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_tool_backend(has=False)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s99", "agent_a")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_other_exceptions_still_caught(self) -> None:
        """Generic exceptions are still caught by the broad handler (regression guard)."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_bind_impl("s2", "agent_a")

        assert result.success is False
        assert "connection lost" in result.error
