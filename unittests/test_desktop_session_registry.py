"""Unit tests for DesktopSessionRegistry."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, PropertyMock

import pytest

from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry


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

    def test_no_com_probe_on_get(self) -> None:
        """get_session does NOT probe COM — avoids CoInitialize errors on async thread."""
        reg = DesktopSessionRegistry()
        mock = _make_mock_session()
        reg.register(mock)
        # Make COM probe fail — but get_session should NOT access it
        type(mock.com.Info).Transaction = PropertyMock(side_effect=OSError("COM dead"))
        # Should still succeed because no probe
        result = reg.get_session("s1")
        assert result is mock


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
# clear (issue #633)
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empty_registry_is_noop(self) -> None:
        reg = DesktopSessionRegistry()
        reg.clear()
        assert reg.list_sessions() == []

    def test_clear_drops_all_sessions(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.clear()
        assert reg.list_sessions() == []
        assert not reg.has_session("s1")
        assert not reg.has_session("s2")
        assert not reg.has_session("s3")

    def test_clear_drops_all_bindings(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        reg.bind("s2", "agent_b")
        reg.clear()
        assert reg.get_bound_agent("s1") is None
        assert reg.get_bound_agent("s2") is None

    def test_clear_resets_counter_so_next_register_is_s1(self) -> None:
        """Regression for #633: re-login must produce a clean s1.

        Without resetting the counter, ``register`` after ``clear`` would
        produce ``s4`` (or whatever the high-water mark was), and
        ``primary_session`` would still resolve to ``s1`` if anything tried
        to look it up. Resetting the counter keeps the registry's contract
        that the first session after a reset is always ``s1``.
        """
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.clear()
        assert reg.register(_make_mock_session()) == "s1"

    def test_clear_then_register_makes_primary_session_resolve_to_new(self) -> None:
        """The full #633 scenario at the registry level.

        Before the fix: registry has dead s1, login adds fresh s2, but
        primary_session returns "s1" → callers get the dead session.
        After the fix: registry.clear() drops the dead s1 first, then
        register() adds the fresh session as s1, and primary_session
        correctly resolves to the new session.
        """
        reg = DesktopSessionRegistry()
        dead = _make_mock_session(transaction="DEAD")
        reg.register(dead)
        # Simulate a re-login: clear, then register the fresh one.
        fresh = _make_mock_session(transaction="FRESH")
        reg.clear()
        reg.register(fresh)
        assert reg.primary_session == "s1"
        assert reg.get_session(reg.primary_session) is fresh
        assert reg.get_session(None) is fresh  # default also resolves to fresh


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


# ---------------------------------------------------------------------------
# prune (issue #637)
# ---------------------------------------------------------------------------


class TestPrune:
    """Sync ``prune()`` removes a batch of dead session IDs in one pass.

    Used by ``DesktopBackend.reconcile()`` after a round of liveness probes.
    No COM access — that's the backend's job, see the class-level docstring.
    """

    def test_prune_removes_listed_sessions(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        removed = reg.prune(["s1", "s3"])
        assert sorted(removed) == ["s1", "s3"]
        assert reg.list_sessions() == ["s2"]

    def test_prune_returns_only_actually_removed(self) -> None:
        """IDs that weren't in the registry must not appear in the return."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        removed = reg.prune(["s1", "s99", "snever"])
        assert removed == ["s1"]

    def test_prune_clears_bindings_for_removed_sessions(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        reg.bind("s2", "agent_b")
        reg.prune(["s1"])
        assert reg.get_bound_agent("s1") is None
        # s2 binding must be untouched
        assert reg.get_bound_agent("s2") == "agent_b"

    def test_prune_empty_iterable_is_noop(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        assert reg.prune([]) == []
        assert reg.list_sessions() == ["s1"]

    def test_prune_logs_bound_agent_for_removed(self, caplog: pytest.LogCaptureFixture) -> None:
        """Removing a bound session should log the agent for orphan correlation."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.bind("s1", "agent_a")
        with caplog.at_level(logging.INFO):
            reg.prune(["s1"])
        # Find the prune log entry and check the agent is captured.
        records = [r for r in caplog.records if "Pruned" in r.message]
        assert records, "expected a Pruned log entry"
        assert getattr(records[0], "bound_to", None) == "agent_a"


# ---------------------------------------------------------------------------
# busy state (issue #791 follow-up)
# ---------------------------------------------------------------------------


class TestBusyState:
    """A session flagged 'busy' (e.g. modal ABAP debugger) is not dead.

    ``DesktopBackend._reconcile_locked`` uses ``mark_busy``/``mark_alive`` to
    record this; the registry itself uses it to steer default-session
    resolution away from a currently-blocked session.
    """

    def test_mark_busy_then_is_busy(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.mark_busy("s1", 100.0)
        assert reg.is_busy("s1")
        assert reg.busy_since("s1") == 100.0

    def test_mark_busy_is_idempotent_keeps_first_timestamp(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.mark_busy("s1", 100.0)
        reg.mark_busy("s1", 200.0)
        assert reg.busy_since("s1") == 100.0

    def test_mark_alive_clears_busy_state(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.mark_busy("s1", 100.0)
        reg.mark_alive("s1")
        assert not reg.is_busy("s1")
        assert reg.busy_since("s1") is None

    def test_unregister_clears_busy_state(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.mark_busy("s1", 100.0)
        reg.unregister("s1")
        assert not reg.is_busy("s1")

    def test_prune_clears_busy_state(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.mark_busy("s1", 100.0)
        reg.prune(["s1"])
        assert not reg.is_busy("s1")

    def test_clear_clears_busy_state(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())
        reg.mark_busy("s1", 100.0)
        reg.clear()
        assert not reg.is_busy("s1")

    def test_default_session_prefers_non_busy_over_s1(self) -> None:
        """A busy s1 must not shadow a healthy s2 as the default target.

        Regression test: before this, a fresh login's session could be
        unreachable via the default (session=None) path because a stuck,
        busy s1 always won as 'primary' — see issue #791 follow-up.
        """
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())  # s1
        reg.register(_make_mock_session())  # s2
        reg.mark_busy("s1", 100.0)
        assert reg.primary_session == "s2"

    def test_default_session_falls_back_to_busy_when_all_busy(self) -> None:
        """Returning the busy session beats raising when there's no alternative."""
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())  # s1
        reg.mark_busy("s1", 100.0)
        assert reg.primary_session == "s1"

    def test_default_session_prefers_s1_when_neither_busy(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())  # s1
        reg.register(_make_mock_session())  # s2
        assert reg.primary_session == "s1"

    def test_canonical_primary_ignores_busy_status(self) -> None:
        """canonical_primary_session() must NOT hand the 'primary' title to a
        responsive s2 just because s1 is busy — unlike primary_session, which
        deliberately does exactly that for call-routing purposes.

        Regression test for the reset_to_primary() inversion: reset_to_primary
        uses this method to decide which session to keep, and a busy s1 (e.g.
        mid-breakpoint-debug) is still the canonical primary, not a victim.
        """
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())  # s1
        reg.register(_make_mock_session())  # s2
        reg.mark_busy("s1", 100.0)
        assert reg.canonical_primary_session() == "s1"
        assert reg.primary_session == "s2"  # the busy-aware default still differs

    def test_canonical_primary_falls_back_to_lowest_when_no_s1(self) -> None:
        reg = DesktopSessionRegistry()
        reg.register(_make_mock_session())  # s1
        reg.register(_make_mock_session())  # s2
        reg.unregister("s1")  # only s2 left
        reg.mark_busy("s2", 100.0)
        assert reg.canonical_primary_session() == "s2"
