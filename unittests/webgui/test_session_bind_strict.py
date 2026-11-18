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

from unittest.mock import MagicMock

import pytest

from sapguimcp.backend.webgui.models.session_registry import SessionRegistry
from sapguimcp.models.base import SessionBindConflictError


def _make_mock_page() -> MagicMock:
    """Mock Playwright Page for the webgui registry."""
    page = MagicMock()
    page.is_closed.return_value = False
    page.on = MagicMock()
    return page


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
