"""Unit tests for session management tools."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from sapguimcp.models.sap_results import SessionInfo


def _make_backend(**overrides: Any) -> AsyncMock:
    """Create a mock backend with default protocol method stubs."""
    backend = AsyncMock()
    backend.list_sessions.return_value = overrides.get("list_sessions", [])
    backend.com_engine_state.return_value = overrides.get("com_engine_state")  # None: the COM engine is idle
    backend.has_session.return_value = overrides.get("has_session", False)
    backend.close_session.return_value = overrides.get("close_session", True)
    backend.bind_session.return_value = overrides.get("bind_session", None)
    backend.release_session.return_value = overrides.get("release_session", None)
    if "reset_to_primary" in overrides:
        backend.reset_to_primary.return_value = overrides["reset_to_primary"]
    return backend


_PATCH_GET_BACKEND = "sapguimcp.tools.session_tools.get_backend"


class TestSessionList:
    """Tests for sap_session_list_impl."""

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        """No sessions returns success with count 0."""
        from sapguimcp.tools.session_tools import sap_session_list_impl

        backend = _make_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 0

    @pytest.mark.anyio
    async def test_with_sessions(self) -> None:
        """Returns all sessions from the backend."""
        from sapguimcp.tools.session_tools import sap_session_list_impl

        sessions = [
            SessionInfo(session_id="s1", title="SAP Easy Access", is_primary=True),
            SessionInfo(session_id="s2", title="Create Sales Order"),
        ]
        backend = _make_backend(list_sessions=sessions)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 2
        assert result.sessions[0].session_id == "s1"
        assert result.sessions[0].is_primary is True
        assert result.sessions[1].session_id == "s2"

    @pytest.mark.anyio
    async def test_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapguimcp.tools.session_tools import sap_session_list_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("no connection"))):
            result = await sap_session_list_impl()

        assert result.success is False
        assert "no connection" in result.error


class TestSessionClose:
    """Tests for sap_session_close_impl."""

    @pytest.mark.anyio
    async def test_can_close_primary(self) -> None:
        """Closing s1 is allowed (#671): the LLM may legitimately want to close
        the primary session when multiple parallel sessions are active. The
        old paternalistic protection was tied to the single-session-only
        contract that #671 lifted.
        """
        from sapguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=True, close_session=True)
        # After close, no sessions remain.
        backend.list_sessions.return_value = []

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s1")

        assert result.success is True
        assert result.session_id == "s1"
        assert result.remaining_sessions == 0
        backend.close_session.assert_awaited_once_with("s1")

    @pytest.mark.anyio
    async def test_unknown_session(self) -> None:
        """Closing a non-existent session returns not found."""
        from sapguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=False, list_sessions=[])
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s99")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_success(self) -> None:
        """Successful close returns session_id and remaining count."""
        from sapguimcp.tools.session_tools import sap_session_close_impl

        remaining = [SessionInfo(session_id="s1", is_primary=True)]
        backend = _make_backend(has_session=True, close_session=True)
        # After close, list_sessions returns just s1
        backend.list_sessions.return_value = remaining

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s2")

        assert result.success is True
        assert result.session_id == "s2"
        assert result.remaining_sessions == 1

    @pytest.mark.anyio
    async def test_close_fails(self) -> None:
        """Backend returns False for close -> failure result."""
        from sapguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=True, close_session=False)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s2")

        assert result.success is False
        assert "s2" in result.error

    @pytest.mark.anyio
    async def test_close_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapguimcp.tools.session_tools import sap_session_close_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_close_impl("s2")

        assert result.success is False
        assert "connection lost" in result.error


class TestSessionBind:
    """Tests for sap_session_bind_impl."""

    @pytest.mark.anyio
    async def test_bind_success(self) -> None:
        """Binding an agent to a session returns the binding."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_backend(has_session=True, bind_session=None)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s2", "agent-1")

        assert result.success is True
        assert result.session_id == "s2"
        assert result.agent_id == "agent-1"
        assert result.previous_agent is None

    @pytest.mark.anyio
    async def test_bind_replaces_previous(self) -> None:
        """Rebinding returns the previous agent_id."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_backend(has_session=True, bind_session="old-agent")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s2", "new-agent")

        assert result.success is True
        assert result.previous_agent == "old-agent"

    @pytest.mark.anyio
    async def test_bind_unknown_session(self) -> None:
        """Binding to a non-existent session returns failure."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_backend(has_session=False, list_sessions=[])
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s99", "agent-1")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_bind_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapguimcp.tools.session_tools import sap_session_bind_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_bind_impl("s2", "agent-1")

        assert result.success is False
        assert "connection lost" in result.error


class TestSessionRelease:
    """Tests for sap_session_release_impl."""

    @pytest.mark.anyio
    async def test_release_success(self) -> None:
        """Releasing an agent returns the released agent_id."""
        from sapguimcp.tools.session_tools import sap_session_release_impl

        backend = _make_backend(has_session=True, release_session="agent-1")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_release_impl("s2")

        assert result.success is True
        assert result.session_id == "s2"
        assert result.released_agent == "agent-1"

    @pytest.mark.anyio
    async def test_release_no_binding(self) -> None:
        """Releasing when no agent was bound returns None."""
        from sapguimcp.tools.session_tools import sap_session_release_impl

        backend = _make_backend(has_session=True, release_session=None)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_release_impl("s2")

        assert result.success is True
        assert result.released_agent is None

    @pytest.mark.anyio
    async def test_release_unknown_session(self) -> None:
        """Releasing a non-existent session returns failure."""
        from sapguimcp.tools.session_tools import sap_session_release_impl

        backend = _make_backend(has_session=False, list_sessions=[])
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_release_impl("s99")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_release_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapguimcp.tools.session_tools import sap_session_release_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_release_impl("s2")

        assert result.success is False
        assert "connection lost" in result.error


class TestSessionResetToPrimary:
    """Tests for sap_session_reset_to_primary_impl (issue #637)."""

    @pytest.mark.anyio
    async def test_success_with_killed_agents(self) -> None:
        """Backend report flows through to the result, including killed agents."""
        from sapguimcp.tools.session_tools import sap_session_reset_to_primary_impl

        backend = _make_backend(
            reset_to_primary={
                "closed": ["s2", "s3", "s4"],
                "remaining": ["s1"],
                "killed_agents": ["agent-b", "agent-c"],
                "errors": [],
            },
        )
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_reset_to_primary_impl()

        assert result.success is True
        assert result.closed_sessions == ["s2", "s3", "s4"]
        assert result.remaining_sessions == ["s1"]
        assert result.killed_agents == ["agent-b", "agent-c"]
        assert result.errors == []

    @pytest.mark.anyio
    async def test_partial_failure_returns_errors_in_result(self) -> None:
        """Per-session close errors are surfaced via the errors list."""
        from sapguimcp.tools.session_tools import sap_session_reset_to_primary_impl

        backend = _make_backend(
            reset_to_primary={
                "closed": ["s2"],
                "remaining": ["s1", "s3"],
                "killed_agents": [],
                "errors": ["s3: COM busy"],
            },
        )
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_reset_to_primary_impl()

        # Partial failure is still success=True at the tool level — the
        # errors field carries the per-session detail. The agent decides
        # whether to retry.
        assert result.success is True
        assert result.closed_sessions == ["s2"]
        assert "s3: COM busy" in result.errors

    @pytest.mark.anyio
    async def test_already_at_primary_is_noop(self) -> None:
        """Empty victim list returns an empty closed list, not an error."""
        from sapguimcp.tools.session_tools import sap_session_reset_to_primary_impl

        backend = _make_backend(
            reset_to_primary={
                "closed": [],
                "remaining": ["s1"],
                "killed_agents": [],
                "errors": [],
            },
        )
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_reset_to_primary_impl()

        assert result.success is True
        assert result.closed_sessions == []
        assert result.remaining_sessions == ["s1"]

    @pytest.mark.anyio
    async def test_backend_exception(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapguimcp.tools.session_tools import sap_session_reset_to_primary_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await sap_session_reset_to_primary_impl()

        assert result.success is False
        assert "boom" in result.error


class TestSessionOwnership:
    """Ownership-aware close / detach tools (issue #1009)."""

    @pytest.mark.anyio
    async def test_close_attached_points_to_detach(self) -> None:
        from sapguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=True)
        backend.session_origin.return_value = "attached"
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s2")

        assert result.success is False
        assert result.error is not None
        assert "sap_session_detach" in result.error
        backend.close_session.assert_not_called()

    @pytest.mark.anyio
    async def test_close_opened_unchanged(self) -> None:
        from sapguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=True)
        backend.session_origin.return_value = "opened"
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s2")

        assert result.success is True
        backend.close_session.assert_awaited_once_with("s2")

    @pytest.mark.anyio
    async def test_detach(self) -> None:
        from sapguimcp.tools.session_tools import sap_session_detach_impl

        backend = _make_backend(has_session=True)
        backend.detach_session.return_value = "agent-1"
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_detach_impl("s2")

        assert result.success is True
        assert result.released_agent == "agent-1"
        backend.close_session.assert_not_called()
        backend.list_sessions.assert_not_called()  # detach must stay COM-free (no reconcile)
        backend.list_sessions_fast.assert_awaited()

    @pytest.mark.anyio
    async def test_detach_unknown_session(self) -> None:
        from sapguimcp.tools.session_tools import sap_session_detach_impl

        backend = _make_backend(has_session=False)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_detach_impl("s9")

        assert result.success is False
        backend.detach_session.assert_not_called()

    @pytest.mark.anyio
    async def test_list_shows_origin(self) -> None:
        from sapguimcp.tools.session_tools import sap_session_list_impl

        sessions = [SessionInfo(session_id="s1"), SessionInfo(session_id="s2", origin="attached")]
        backend = _make_backend(list_sessions=sessions)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_list_impl()

        assert [s.origin for s in result.sessions] == ["opened", "attached"]

    @pytest.mark.anyio
    async def test_reset_reports_skipped_attached(self) -> None:
        from sapguimcp.tools.session_tools import sap_session_reset_to_primary_impl

        backend = _make_backend(
            reset_to_primary={"closed": ["s2"], "remaining": ["s1", "s3"], "skipped_attached": ["s3"]}
        )
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_reset_to_primary_impl()

        assert result.skipped_attached == ["s3"]
