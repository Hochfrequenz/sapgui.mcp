"""Unit tests for SessionRegistry with mocked Page objects."""

from unittest.mock import MagicMock

import pytest

from sapwebguimcp.models.session_registry import SessionRegistry


class TestSessionRegistryUnit:
    """Unit tests for SessionRegistry without real browser."""

    def test_register_assigns_sequential_ids(self) -> None:
        """Test that register() assigns s1, s2, s3 sequentially."""
        registry = SessionRegistry()

        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()

        sid1 = registry.register(page1)
        sid2 = registry.register(page2)

        assert sid1 == "s1"
        assert sid2 == "s2"

    def test_get_page_returns_correct_page(self) -> None:
        """Test that get_page returns the registered page."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        retrieved = registry.get_page(sid)

        assert retrieved is page

    def test_get_page_none_returns_primary(self) -> None:
        """Test that get_page(None) returns s1 (primary session)."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        registry.register(page)  # s1
        retrieved = registry.get_page(None)

        assert retrieved is page

    def test_get_page_unknown_session_raises(self) -> None:
        """Test that get_page with unknown session raises ValueError."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()
        registry.register(page)  # s1

        with pytest.raises(ValueError, match="Session 's99' not found"):
            registry.get_page("s99")

    def test_get_page_closed_page_raises_and_cleans_up(self) -> None:
        """Test that accessing closed page raises and removes from registry."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)

        # Simulate page being closed
        page.is_closed.return_value = True

        with pytest.raises(ValueError, match="expired"):
            registry.get_page(sid)

        # Should be cleaned up
        assert sid not in registry._sessions

    def test_unregister_removes_session(self) -> None:
        """Test that unregister removes session from registry."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        assert sid in registry._sessions

        registry.unregister(sid)
        assert sid not in registry._sessions

    def test_list_sessions_returns_all_active(self) -> None:
        """Test list_sessions returns all registered sessions."""
        registry = SessionRegistry()

        for _ in range(3):
            page = MagicMock()
            page.is_closed.return_value = False
            page.on = MagicMock()
            registry.register(page)

        sessions = registry.list_sessions()
        assert len(sessions) == 3
        assert set(sessions) == {"s1", "s2", "s3"}

    def test_primary_session_is_always_s1(self) -> None:
        """Test that primary_session property returns s1."""
        registry = SessionRegistry()
        assert registry.primary_session == "s1"

    def test_has_session(self) -> None:
        """Test has_session check."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        registry.register(page)

        assert registry.has_session("s1") is True
        assert registry.has_session("s2") is False
