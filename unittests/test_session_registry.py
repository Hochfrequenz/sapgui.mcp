"""Unit tests for SessionRegistry with mocked Page objects."""

import logging
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.webgui.models.session_registry import SessionRegistry


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

    def test_primary_session_defaults_to_s1(self) -> None:
        """Test that primary_session returns s1 when empty or s1 exists."""
        registry = SessionRegistry()
        # Empty registry defaults to s1 (sentinel)
        assert registry.primary_session == "s1"

        # After registering, s1 is the primary
        page1 = MagicMock()
        page1.is_closed.return_value = False
        registry.register(page1)
        assert registry.primary_session == "s1"

    def test_primary_session_falls_back_to_lowest(self) -> None:
        """Test that primary_session returns lowest available when s1 is gone."""
        registry = SessionRegistry()
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page2 = MagicMock()
        page2.is_closed.return_value = False
        page3 = MagicMock()
        page3.is_closed.return_value = False

        registry.register(page1)  # s1
        registry.register(page2)  # s2
        registry.register(page3)  # s3

        # Remove s1 — primary should fall back to s2
        registry.unregister("s1")
        assert registry.primary_session == "s2"

        # Remove s2 — primary should fall back to s3
        registry.unregister("s2")
        assert registry.primary_session == "s3"

    def test_has_session(self) -> None:
        """Test has_session check."""
        registry = SessionRegistry()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        registry.register(page)

        assert registry.has_session("s1") is True
        assert registry.has_session("s2") is False


class TestBrowserManagerSessionIntegration:
    """Tests for BrowserManager + SessionRegistry integration."""

    def test_browser_manager_has_registry(self) -> None:
        """Test that BrowserManager exposes session registry."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()
        assert hasattr(manager, "registry")
        assert manager.registry is not None

    def test_browser_manager_get_session_page(self) -> None:
        """Test BrowserManager.get_session_page() method."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        manager.registry.register(page)

        retrieved = manager.get_session_page("s1")
        assert retrieved is page

        retrieved_default = manager.get_session_page(None)
        assert retrieved_default is page


class TestSessionRegistryBindings:
    """Tests for agent-session binding functionality."""

    def test_bind_and_get_bound_agent(self) -> None:
        """Test binding an agent to a session."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        registry.bind(sid, "agent-1")

        assert registry.get_bound_agent(sid) == "agent-1"

    def test_get_bound_agent_unbound_returns_none(self) -> None:
        """Test unbound session returns None."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        assert registry.get_bound_agent(sid) is None

    def test_release_clears_binding(self) -> None:
        """Test release removes agent binding."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        registry.bind(sid, "agent-1")
        registry.release(sid)

        assert registry.get_bound_agent(sid) is None

    def test_release_nonexistent_binding_is_noop(self) -> None:
        """Test releasing unbound session doesn't raise."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        registry.release(sid)  # Should not raise
        assert registry.get_bound_agent(sid) is None

    def test_register_with_agent_id_binds(self) -> None:
        """Test register() with agent_id binds immediately."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        assert registry.get_bound_agent(sid) == "agent-1"

    def test_unregister_clears_binding(self) -> None:
        """Test unregister() also removes binding."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        registry.unregister(sid)
        assert registry.get_bound_agent(sid) is None


class TestSessionRegistryBindingChecks:
    """Tests for check_binding warning logic."""

    def test_check_binding_unbound_session_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test unbound session doesn't warn."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page)
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, "any-agent", "test_tool")

        assert "WARNING" not in caplog.text

    def test_check_binding_matching_agent_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test matching agent doesn't warn."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, "agent-1", "test_tool")

        assert "WARNING" not in caplog.text

    def test_check_binding_mismatched_agent_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test mismatched agent logs warning."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, "agent-2", "test_tool")

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.getMessage() == "Cross-agent session access"
        assert record.bound_to == "agent-1"  # type: ignore[attr-defined]
        assert record.accessed_by == "agent-2"  # type: ignore[attr-defined]
        assert record.tool == "test_tool"  # type: ignore[attr-defined]

    def test_check_binding_none_agent_on_bound_session_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test None agent on bound session logs warning."""
        registry = SessionRegistry()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = registry.register(page, agent_id="agent-1")
        with caplog.at_level(logging.WARNING):
            registry.check_binding(sid, None, "test_tool")

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.getMessage() == "Bound session accessed without agent_id"
        assert record.bound_to == "agent-1"  # type: ignore[attr-defined]


class TestBrowserManagerBindingCheck:
    """Tests for BrowserManager binding check integration."""

    def test_get_session_page_with_binding_check(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test get_session_page_checked calls check_binding."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()
        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        sid = manager.registry.register(page, agent_id="agent-1")

        with caplog.at_level(logging.WARNING):
            result = manager.get_session_page_checked(sid, "agent-2", "test_tool")

        assert result is page
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.bound_to == "agent-1"  # type: ignore[attr-defined]
        assert record.accessed_by == "agent-2"  # type: ignore[attr-defined]
