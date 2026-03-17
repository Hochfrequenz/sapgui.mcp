"""Unit tests for DesktopSessionRegistry."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, PropertyMock

import pytest

from sapwebguimcp.backend.desktop._session_registry import DesktopSessionRegistry


def _make_mock_session(transaction: str = "SE00") -> MagicMock:
    """Create a mock GuiSession with a working COM info probe."""
    session = MagicMock()
    session.com.Info.Transaction = transaction
    session.id = "/app/con[0]/ses[0]"
    return session


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_first_session_is_s1(self) -> None:
        reg = DesktopSessionRegistry()
        assert reg.register(_make_mock_session()) == "s1"

    def test_second_session_is_s2(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        assert reg.register(_make_mock_session()) == "s2"

    def test_counter_increments(self) -> None:
        reg = DesktopSessionRegistry()
        ids = [reg.register(_make_mock_session()) for _ in range(5)]
        assert ids == ["s1", "s2", "s3", "s4", "s5"]


# ---------------------------------------------------------------------------
# get_session
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_returns_registered_session(self) -> None:
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)
        assert reg.get_session("s1") is mock

    def test_none_defaults_to_s1(self) -> None:
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)
        assert reg.get_session(None) is mock

    def test_unknown_session_raises(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        with pytest.raises(ValueError, match="not found"):
            reg.get_session("s99")

    def test_empty_registry_none_raises(self) -> None:
        """get_session(None) on empty registry raises (None → 's1' → not found)."""
        reg = DesktopSessionRegistry()
        with pytest.raises(ValueError, match="not found"):
            reg.get_session(None)

    def test_stale_session_auto_unregisters(self) -> None:
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)
        # Force probe past TTL cache
        reg._last_probe["s1"] = 0
        # Make COM probe fail
        type(mock.com.Info).Transaction = PropertyMock(side_effect=OSError("COM dead"))
        with pytest.raises(ValueError, match="expired"):
            reg.get_session("s1")
        assert not reg.has_session("s1")


# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------


class TestTTLCache:
    def test_probe_skipped_within_ttl(self) -> None:
        """Session returned without probe if accessed within TTL window."""
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)  # sets probe timestamp to now
        # Make COM probe fail — but it should NOT be called (within TTL)
        type(mock.com.Info).Transaction = PropertyMock(side_effect=OSError("COM dead"))
        # Should succeed because TTL hasn't expired
        result = reg.get_session("s1")
        assert result is mock

    def test_probe_runs_after_ttl_expires(self) -> None:
        """Session probed after TTL expires."""
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)
        # Force TTL expiry
        reg._last_probe["s1"] = 0
        # COM probe succeeds — session returned
        result = reg.get_session("s1")
        assert result is mock

    def test_stale_detected_after_ttl(self) -> None:
        """Stale session detected only after TTL expires."""
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)
        # Within TTL — works even though COM would fail
        type(mock.com.Info).Transaction = PropertyMock(side_effect=OSError("dead"))
        assert reg.get_session("s1") is mock
        # After TTL — now raises
        reg._last_probe["s1"] = 0
        with pytest.raises(ValueError, match="expired"):
            reg.get_session("s1")


# ---------------------------------------------------------------------------
# unregister
# ---------------------------------------------------------------------------


class TestUnregister:
    def test_removes_session(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.unregister("s1")
        assert not reg.has_session("s1")

    def test_clears_binding(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        reg.unregister("s1")
        assert reg.get_bound_agent("s1") is None

    def test_unregister_s1_while_s2_exists(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        mock2 = _make_mock_session()
        reg.register(mock2)
        reg.unregister("s1")
        assert not reg.has_session("s1")
        assert reg.get_session("s2") is mock2
        with pytest.raises(ValueError, match="not found"):
            reg.get_session("s1")


# ---------------------------------------------------------------------------
# binding
# ---------------------------------------------------------------------------


class TestBinding:
    def test_bind_and_get(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        assert reg.get_bound_agent("s1") == "agent_a"

    def test_release(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        reg.release("s1")
        assert reg.get_bound_agent("s1") is None

    def test_check_binding_logs_warning_on_mismatch(self, caplog: pytest.LogCaptureFixture) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        with caplog.at_level(logging.WARNING):
            reg.check_binding("s1", "agent_b", "sap_transaction")
        assert "Cross-agent" in caplog.text

    def test_check_binding_no_warning_when_matching(self, caplog: pytest.LogCaptureFixture) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        with caplog.at_level(logging.WARNING):
            reg.check_binding("s1", "agent_a", "sap_transaction")
        assert "Cross-agent" not in caplog.text

    def test_check_binding_warns_without_agent_id(self, caplog: pytest.LogCaptureFixture) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        with caplog.at_level(logging.WARNING):
            reg.check_binding("s1", None, "sap_transaction")
        assert "without agent_id" in caplog.text


# ---------------------------------------------------------------------------
# list + has
# ---------------------------------------------------------------------------


class TestListAndHas:
    def test_list_sessions(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        assert sorted(reg.list_sessions()) == ["s1", "s2"]

    def test_has_session(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        assert reg.has_session("s1")
        assert not reg.has_session("s2")
