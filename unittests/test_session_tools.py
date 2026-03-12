"""Unit tests for session management tools."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from sapwebguimcp.models.sap_results import SessionInfo


def _make_backend(**overrides: Any) -> AsyncMock:
    """Create a mock backend with default protocol method stubs."""
    backend = AsyncMock()
    backend.list_sessions.return_value = overrides.get("list_sessions", [])
    backend.has_session.return_value = overrides.get("has_session", False)
    backend.close_session.return_value = overrides.get("close_session", True)
    backend.bind_session.return_value = overrides.get("bind_session", None)
    backend.release_session.return_value = overrides.get("release_session", None)
    return backend


_PATCH_GET_BACKEND = "sapwebguimcp.tools.session_tools.get_backend"


class TestSessionList:
    """Tests for sap_session_list_impl."""

    @pytest.mark.anyio
    async def test_empty(self) -> None:
        """No sessions returns success with count 0."""
        from sapwebguimcp.tools.session_tools import sap_session_list_impl

        backend = _make_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 0

    @pytest.mark.anyio
    async def test_with_sessions(self) -> None:
        """Returns all sessions from the backend."""
        from sapwebguimcp.tools.session_tools import sap_session_list_impl

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
        from sapwebguimcp.tools.session_tools import sap_session_list_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("no connection"))):
            result = await sap_session_list_impl()

        assert result.success is False
        assert "no connection" in result.error


class TestSessionClose:
    """Tests for sap_session_close_impl."""

    @pytest.mark.anyio
    async def test_rejects_primary(self) -> None:
        """Closing s1 is rejected without calling the backend."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=AssertionError("should not be called"))):
            result = await sap_session_close_impl("s1")

        assert result.success is False
        assert "s1" in result.error

    @pytest.mark.anyio
    async def test_unknown_session(self) -> None:
        """Closing a non-existent session returns not found."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=False, list_sessions=[])
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s99")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_success(self) -> None:
        """Successful close returns session_id and remaining count."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

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
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        backend = _make_backend(has_session=True, close_session=False)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_close_impl("s2")

        assert result.success is False
        assert "s2" in result.error

    @pytest.mark.anyio
    async def test_close_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_close_impl("s2")

        assert result.success is False
        assert "connection lost" in result.error


class TestSessionBind:
    """Tests for sap_session_bind_impl."""

    @pytest.mark.anyio
    async def test_bind_success(self) -> None:
        """Binding an agent to a session returns the binding."""
        from sapwebguimcp.tools.session_tools import sap_session_bind_impl

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
        from sapwebguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_backend(has_session=True, bind_session="old-agent")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s2", "new-agent")

        assert result.success is True
        assert result.previous_agent == "old-agent"

    @pytest.mark.anyio
    async def test_bind_unknown_session(self) -> None:
        """Binding to a non-existent session returns failure."""
        from sapwebguimcp.tools.session_tools import sap_session_bind_impl

        backend = _make_backend(has_session=False, list_sessions=[])
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_bind_impl("s99", "agent-1")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_bind_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapwebguimcp.tools.session_tools import sap_session_bind_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_bind_impl("s2", "agent-1")

        assert result.success is False
        assert "connection lost" in result.error


class TestSessionRelease:
    """Tests for sap_session_release_impl."""

    @pytest.mark.anyio
    async def test_release_success(self) -> None:
        """Releasing an agent returns the released agent_id."""
        from sapwebguimcp.tools.session_tools import sap_session_release_impl

        backend = _make_backend(has_session=True, release_session="agent-1")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_release_impl("s2")

        assert result.success is True
        assert result.session_id == "s2"
        assert result.released_agent == "agent-1"

    @pytest.mark.anyio
    async def test_release_no_binding(self) -> None:
        """Releasing when no agent was bound returns None."""
        from sapwebguimcp.tools.session_tools import sap_session_release_impl

        backend = _make_backend(has_session=True, release_session=None)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_release_impl("s2")

        assert result.success is True
        assert result.released_agent is None

    @pytest.mark.anyio
    async def test_release_unknown_session(self) -> None:
        """Releasing a non-existent session returns failure."""
        from sapwebguimcp.tools.session_tools import sap_session_release_impl

        backend = _make_backend(has_session=False, list_sessions=[])
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_session_release_impl("s99")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_release_backend_error(self) -> None:
        """Backend exception is caught and returned as failure."""
        from sapwebguimcp.tools.session_tools import sap_session_release_impl

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=RuntimeError("connection lost"))):
            result = await sap_session_release_impl("s2")

        assert result.success is False
        assert "connection lost" in result.error


class TestRegisterNewWindowSession:
    """Unit tests for _register_new_window_session helper function."""

    @pytest.mark.anyio
    async def test_registers_new_page_when_count_increases(self) -> None:
        """Test that new page is registered when page count increases."""
        from unittest.mock import MagicMock

        from sapwebguimcp.models.session_registry import SessionRegistry
        from sapwebguimcp.tools.sap_tools import _register_new_window_session

        registry = SessionRegistry()

        # Mock browser manager
        mock_manager = MagicMock()
        mock_manager.registry = registry

        # Mock new page
        new_page = MagicMock()
        new_page.is_closed.return_value = False
        new_page.on = MagicMock()
        new_page.title = AsyncMock(return_value="New Transaction")

        # Mock context with new page
        mock_context = MagicMock()
        mock_context.pages = [MagicMock(), new_page]  # 2 pages now

        session_id, count, title = await _register_new_window_session(mock_manager, mock_context, pages_before=1)

        assert session_id == "s1"  # First registration
        assert count == 2
        assert title == "New Transaction"
        assert registry.has_session("s1")

    @pytest.mark.anyio
    async def test_returns_none_when_no_new_page(self) -> None:
        """Test that None is returned when page count doesn't increase."""
        from unittest.mock import MagicMock

        from sapwebguimcp.models.session_registry import SessionRegistry
        from sapwebguimcp.tools.sap_tools import _register_new_window_session

        # Fully mock browser manager with registry (even if not used in this path)
        mock_manager = MagicMock()
        mock_manager.registry = SessionRegistry()
        mock_context = MagicMock()
        mock_context.pages = [MagicMock()]  # Still 1 page

        # Use short timeout for faster test
        session_id, count, title = await _register_new_window_session(
            mock_manager, mock_context, pages_before=1, wait_timeout_ms=100
        )

        assert session_id is None
        assert count == 1
        assert title is None

    @pytest.mark.anyio
    async def test_logs_warning_with_context_when_no_new_page(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that warning is logged with tcode context when no new page is detected."""
        import logging
        from unittest.mock import MagicMock

        from sapwebguimcp.models.session_registry import SessionRegistry
        from sapwebguimcp.tools.sap_tools import _register_new_window_session

        # Fully mock browser manager with registry
        mock_manager = MagicMock()
        mock_manager.registry = SessionRegistry()
        mock_context = MagicMock()
        mock_context.pages = [MagicMock()]  # Still 1 page

        with caplog.at_level(logging.WARNING):
            # Use short timeout and provide tcode for context
            await _register_new_window_session(
                mock_manager, mock_context, pages_before=1, tcode="VA01", wait_timeout_ms=100
            )

        assert "No new page detected" in caplog.text
        assert "/o prefix" in caplog.text
        # Dynamic values are now in structured extra fields
        record = caplog.records[-1]
        assert record.tcode == "VA01"
        assert record.pages_before == 1
        assert record.pages_after == 1

    @pytest.mark.anyio
    async def test_registers_last_page_when_multiple_pages_created(self) -> None:
        """Test that the last page is registered when multiple pages are created simultaneously."""
        from unittest.mock import MagicMock

        from sapwebguimcp.models.session_registry import SessionRegistry
        from sapwebguimcp.tools.sap_tools import _register_new_window_session

        registry = SessionRegistry()
        mock_manager = MagicMock()
        mock_manager.registry = registry

        # Mock multiple new pages (edge case: 2 pages created at once)
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()
        page2.title = AsyncMock(return_value="Expected New Page")

        page3 = MagicMock()
        page3.is_closed.return_value = False
        page3.on = MagicMock()
        page3.title = AsyncMock(return_value="Last Page - Should Be Registered")

        # Context now has 3 pages (was 1 before)
        mock_context = MagicMock()
        mock_context.pages = [page1, page2, page3]

        session_id, count, title = await _register_new_window_session(
            mock_manager, mock_context, pages_before=1, wait_timeout_ms=100
        )

        # Should register the LAST page (pages[-1])
        assert session_id == "s1"
        assert count == 3
        assert title == "Last Page - Should Be Registered"
        assert registry.has_session("s1")
