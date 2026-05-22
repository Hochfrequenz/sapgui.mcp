"""Integration tests for agent-session binding."""

import logging
from unittest.mock import MagicMock

import pytest


class TestAgentBindingIntegration:
    """Integration tests for cross-agent detection."""

    def test_cross_agent_access_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that cross-agent access logs warning."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()

        # Create mock pages
        page1 = MagicMock()
        page1.is_closed.return_value = False
        page1.on = MagicMock()

        page2 = MagicMock()
        page2.is_closed.return_value = False
        page2.on = MagicMock()

        # Register with bindings
        manager.registry.register(page1)  # s1, unbound
        manager.registry.register(page2, agent_id="agent-A")  # s2, bound to A

        # Agent B tries to access Agent A's session
        with caplog.at_level(logging.WARNING):
            page = manager.get_session_page_checked("s2", "agent-B", "test_tool")

        # Operation should succeed
        assert page is page2

        # But warning should be logged with structured extra fields
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.getMessage() == "Cross-agent session access"
        assert record.bound_to == "agent-A"  # type: ignore[attr-defined]
        assert record.accessed_by == "agent-B"  # type: ignore[attr-defined]

    def test_unbound_session_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that unbound session doesn't warn."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        manager.registry.register(page)  # s1, unbound

        with caplog.at_level(logging.WARNING):
            manager.get_session_page_checked("s1", "any-agent", "test_tool")

        # No warning for unbound session
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    def test_matching_agent_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that matching agent doesn't warn."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        manager.registry.register(page, agent_id="agent-A")  # s1, bound to A

        with caplog.at_level(logging.WARNING):
            manager.get_session_page_checked("s1", "agent-A", "test_tool")

        # No warning when agent matches
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    def test_none_agent_on_bound_session_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that None agent on bound session logs warning."""
        from sapguimcp.backend.webgui.browser import BrowserManager

        manager = BrowserManager()

        page = MagicMock()
        page.is_closed.return_value = False
        page.on = MagicMock()

        manager.registry.register(page, agent_id="agent-A")  # s1, bound to A

        with caplog.at_level(logging.WARNING):
            manager.get_session_page_checked("s1", None, "test_tool")

        # Warning for accessing bound session without agent_id
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 1
        record = warning_records[0]
        assert record.getMessage() == "Bound session accessed without agent_id"
        assert record.bound_to == "agent-A"  # type: ignore[attr-defined]
