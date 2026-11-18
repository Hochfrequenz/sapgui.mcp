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

from unittest.mock import AsyncMock, patch

import pytest

from sapguimcp.models.base import SessionBindConflictError

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
