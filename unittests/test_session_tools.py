"""Unit tests for session management tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapwebguimcp.models.session_registry import SessionRegistry


class TestSessionToolsUnit:
    """Unit tests for session tools with mocked browser."""

    @pytest.mark.anyio
    async def test_sap_session_list_empty(self) -> None:
        """Test sap_session_list with no sessions."""
        from sapwebguimcp.tools.session_tools import sap_session_list_impl

        registry = SessionRegistry()

        with patch("sapwebguimcp.tools.session_tools.get_browser_manager") as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 0

    @pytest.mark.anyio
    async def test_sap_session_list_with_sessions(self) -> None:
        """Test sap_session_list with active sessions."""
        from sapwebguimcp.tools.session_tools import sap_session_list_impl

        registry = SessionRegistry()

        # Mock pages
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()
        page1.title = AsyncMock(return_value="SAP Easy Access")

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()
        page2.title = AsyncMock(return_value="Create Sales Order")

        registry.register(page1)
        registry.register(page2)

        with patch("sapwebguimcp.tools.session_tools.get_browser_manager") as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_list_impl()

        assert result.success is True
        assert result.session_count == 2

    @pytest.mark.anyio
    async def test_sap_session_close_rejects_primary(self) -> None:
        """Test that sap_session_close rejects closing s1."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        result = await sap_session_close_impl("s1")

        assert result.success is False
        assert "primary" in result.error.lower() or "s1" in result.error

    @pytest.mark.anyio
    async def test_sap_session_close_unknown_session(self) -> None:
        """Test sap_session_close with unknown session."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        registry = SessionRegistry()

        with patch("sapwebguimcp.tools.session_tools.get_browser_manager") as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_close_impl("s99")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.anyio
    async def test_sap_session_close_success(self) -> None:
        """Test successful session close."""
        from sapwebguimcp.tools.session_tools import sap_session_close_impl

        registry = SessionRegistry()

        # Register primary session s1
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()
        registry.register(page1)

        # Register secondary session s2 to close
        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()
        page2.query_selector = AsyncMock(return_value=None)
        page2.keyboard = MagicMock()
        page2.keyboard.press = AsyncMock()
        page2.wait_for_timeout = AsyncMock()
        page2.close = AsyncMock()
        registry.register(page2)

        with patch("sapwebguimcp.tools.session_tools.get_browser_manager") as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_close_impl("s2")

        assert result.success is True
        assert result.session_id == "s2"
        assert result.remaining_sessions == 1

    @pytest.mark.anyio
    async def test_sap_session_open_no_primary_session(self) -> None:
        """Test sap_session_open fails when no primary session exists."""
        from sapwebguimcp.tools.session_tools import sap_session_open_impl

        registry = SessionRegistry()

        with patch("sapwebguimcp.tools.session_tools.get_browser_manager") as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_open_impl()

        assert result.success is False
        assert "primary" in result.error.lower() or "sap_login" in result.error.lower()

    @pytest.mark.anyio
    async def test_sap_session_list_session_info_fields(self) -> None:
        """Test that session_list returns proper SessionInfo fields."""
        from sapwebguimcp.tools.session_tools import sap_session_list_impl

        registry = SessionRegistry()

        # Mock primary session page
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()
        page1.title = AsyncMock(return_value="SAP Easy Access - Main Menu")

        registry.register(page1)

        with patch("sapwebguimcp.tools.session_tools.get_browser_manager") as mock_get_bm:
            mock_manager = MagicMock()
            mock_manager.registry = registry
            mock_get_bm.return_value = mock_manager

            result = await sap_session_list_impl()

        assert result.success is True
        assert len(result.sessions) == 1
        session = result.sessions[0]
        assert session.session_id == "s1"
        assert session.is_primary is True
        assert session.title == "SAP Easy Access - Main Menu"


class TestRegisterNewWindowSession:
    """Unit tests for _register_new_window_session helper function."""

    @pytest.mark.anyio
    async def test_registers_new_page_when_count_increases(self) -> None:
        """Test that new page is registered when page count increases."""
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
        from sapwebguimcp.tools.sap_tools import _register_new_window_session

        mock_manager = MagicMock()
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

        from sapwebguimcp.tools.sap_tools import _register_new_window_session

        mock_manager = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [MagicMock()]  # Still 1 page

        with caplog.at_level(logging.WARNING):
            # Use short timeout and provide tcode for context
            await _register_new_window_session(
                mock_manager, mock_context, pages_before=1, tcode="VA01", wait_timeout_ms=100
            )

        assert "no new page detected" in caplog.text
        assert "tcode=VA01" in caplog.text
        assert "/o prefix" in caplog.text
        assert "pages: 1 -> 1" in caplog.text
