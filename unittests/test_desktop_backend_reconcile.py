"""Unit tests for DesktopBackend reconciliation and bulk cleanup (issue #637).

These tests construct a DesktopBackend via ``__new__`` (bypassing the real
``__init__`` so we don't spawn a ComThread), wire in fake registry sessions,
and stub ``com.run`` to control probe outcomes. The goal is to verify the
session-drift recovery logic on Linux/CI without needing a real SAP GUI.
"""

# pylint: disable=protected-access

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry


def _make_backend() -> DesktopBackend:
    """Build a DesktopBackend with a fresh registry, mocked ComThread, and a real lock."""
    backend = DesktopBackend.__new__(DesktopBackend)
    backend.registry = DesktopSessionRegistry()
    backend.com = MagicMock()
    backend._mutation_lock = asyncio.Lock()
    return backend


def _make_mock_session(label: str = "ses", *, alive: bool = True) -> MagicMock:
    """Create a mock GuiSession.

    The reconcile probe calls ``s.com.FindById("wnd[0]").Type``. By default
    we configure that chain to return a non-empty string (alive). When
    ``alive=False`` we make ``FindById`` raise so the probe fails — this
    drives the test via the mock's *behaviour*, not by introspecting the
    lambda's source, which would be brittle to refactors.
    """
    session = MagicMock()
    session.com = MagicMock()
    session.label = label  # for human-readable assertions
    if alive:
        session.com.FindById.return_value.Type = "GuiMainWindow"
    else:
        session.com.FindById.side_effect = RuntimeError(f"{label} dead")
    return session


async def _passthrough_run(fn: Any, *, max_retries: int | None = None) -> Any:  # pylint: disable=unused-argument
    """Stub for ``backend.com.run`` that just calls the lambda directly.

    Lets the mock session's configured side-effects (raise vs return)
    drive the test outcome — no source introspection needed.
    """
    return fn()


# ---------------------------------------------------------------------------
# reconcile()
# ---------------------------------------------------------------------------


class TestReconcile:
    """``DesktopBackend.reconcile()`` removes dead sessions, keeps alive ones."""

    @pytest.mark.anyio
    async def test_all_alive_keeps_everything(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_mock_session("s2", alive=True))
        backend.com.run = _passthrough_run

        report = await backend.reconcile()

        assert sorted(report["alive"]) == ["s1", "s2"]
        assert report["removed"] == []
        assert sorted(backend.registry.list_sessions()) == ["s1", "s2"]

    @pytest.mark.anyio
    async def test_dead_session_is_removed(self) -> None:
        """A probe that raises (any reason) marks the session as gone."""
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_mock_session("s2", alive=False))
        backend.com.run = _passthrough_run

        report = await backend.reconcile()

        assert report["alive"] == ["s1"]
        assert report["removed"] == ["s2"]
        assert backend.registry.list_sessions() == ["s1"]

    @pytest.mark.anyio
    async def test_probe_uses_max_retries_zero(self) -> None:
        """The probe call MUST pass max_retries=0 to fail fast on RPC_S_UNKNOWN_IF.

        Without this, ComThread retries the stale-interface error, and the
        probe never raises — meaning a dead session would be kept in the
        registry forever. This is the privacy/correctness guard from the
        plan-review for issue #637.
        """
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        captured: list[int | None] = []

        async def capturing_run(fn: Any, *, max_retries: int | None = None) -> Any:
            captured.append(max_retries)
            return fn()

        backend.com.run = capturing_run

        await backend.reconcile()
        assert captured == [0], f"expected probe to use max_retries=0, got {captured}"

    @pytest.mark.anyio
    async def test_dead_session_clears_binding(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_mock_session("s2", alive=False))
        backend.registry.bind("s2", "agent-x")
        backend.com.run = _passthrough_run

        await backend.reconcile()

        assert backend.registry.get_bound_agent("s2") is None
        assert backend.registry.list_sessions() == ["s1"]

    @pytest.mark.anyio
    async def test_empty_registry_is_noop(self) -> None:
        backend = _make_backend()
        # com.run must NOT be called — but provide a stub anyway.
        backend.com.run = AsyncMock(return_value="ignored")

        report = await backend.reconcile()

        assert report == {"alive": [], "removed": []}
        backend.com.run.assert_not_called()

    @pytest.mark.anyio
    async def test_all_dead_clears_registry(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=False))
        backend.registry.register(_make_mock_session("s2", alive=False))
        backend.com.run = _passthrough_run

        report = await backend.reconcile()

        assert report["alive"] == []
        assert sorted(report["removed"]) == ["s1", "s2"]
        assert backend.registry.list_sessions() == []

    @pytest.mark.anyio
    async def test_probe_timeout_treated_as_dead(self) -> None:
        """A wedged COM thread must NOT deadlock recovery (issue #637).

        The probe is wrapped in ``asyncio.wait_for`` with a short timeout.
        On timeout we treat the session as dead so reset_to_primary can
        proceed even when the COM worker is stuck on a prior call.
        """
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))

        # Force the timeout deterministically by lowering it AND making
        # com.run hang forever. Without ``wait_for`` the test would deadlock.
        backend._RECONCILE_PROBE_TIMEOUT_S = 0.05  # type: ignore[misc]

        wedge = asyncio.Event()  # never set

        async def hung_run(fn: Any, *, max_retries: int | None = None) -> Any:  # pylint: disable=unused-argument
            await wedge.wait()
            return fn()

        backend.com.run = hung_run

        report = await backend.reconcile()

        assert report["alive"] == []
        assert report["removed"] == ["s1"]
        assert backend.registry.list_sessions() == []


# ---------------------------------------------------------------------------
# reset_to_primary()
# ---------------------------------------------------------------------------


class TestResetToPrimary:
    """``DesktopBackend.reset_to_primary()`` closes every non-primary session."""

    @pytest.mark.anyio
    async def test_closes_non_primary(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_mock_session("s2", alive=True))
        backend.registry.register(_make_mock_session("s3", alive=True))
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        assert sorted(report["closed"]) == ["s2", "s3"]
        assert report["remaining"] == ["s1"]
        assert backend.registry.list_sessions() == ["s1"]
        assert report["killed_agents"] == []
        assert report["errors"] == []

    @pytest.mark.anyio
    async def test_tracks_killed_agents(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_mock_session("s2", alive=True))
        backend.registry.register(_make_mock_session("s3", alive=True))
        backend.registry.bind("s2", "agent-b")
        backend.registry.bind("s3", "agent-c")
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        assert sorted(report["killed_agents"]) == ["agent-b", "agent-c"]

    @pytest.mark.anyio
    async def test_already_at_primary_is_noop(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        assert report["closed"] == []
        assert report["remaining"] == ["s1"]
        assert report["killed_agents"] == []

    @pytest.mark.anyio
    async def test_close_com_warning_is_treated_as_closed(self) -> None:
        """Slot-freed-but-COM-complained must report `closed` AND record a warning.

        ``_close_session_locked`` catches CloseSession exceptions, returns
        False, but unregisters the session anyway. From the agent's point
        of view the session IS gone — so it belongs in ``closed``, not
        sitting in ``errors`` looking like the close didn't happen. The
        COM-level complaint is still surfaced via a soft warning string
        in ``errors`` so operators can correlate.

        Implementation note: ``_close_session_locked`` calls
        ``primary.com.Parent.CloseSession(target.com.Id)`` — the connection
        object is reached via the *primary* session's parent, not the target's.
        So to simulate a CloseSession failure we set the side_effect on the
        primary's parent.
        """
        backend = _make_backend()
        s1 = _make_mock_session("s1", alive=True)
        # Make primary's CloseSession raise when called.
        s1.com.Parent.CloseSession.side_effect = RuntimeError("CloseSession refused")
        backend.registry.register(s1)
        backend.registry.register(_make_mock_session("s2", alive=True))
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        # Slot freed → in closed.
        assert report["closed"] == ["s2"]
        assert "s2" not in backend.registry.list_sessions()
        # Soft warning recorded.
        assert any("s2" in e and "CloseSession" in e for e in report["errors"])
        # Remaining is just the primary.
        assert report["remaining"] == ["s1"]

    @pytest.mark.anyio
    async def test_reconciles_dead_session_before_closing(self) -> None:
        """Dead sessions in the registry are pruned by reconcile, not 'closed'.

        s2 is dead at probe time → reconcile drops it. The reset loop then
        only sees s1 (primary) and finds nothing to close. The result must
        not list s2 in either ``closed`` (we never called CloseSession on
        it) or ``remaining``.
        """
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_mock_session("s2", alive=False))
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        assert "s2" not in report["closed"]
        assert report["remaining"] == ["s1"]
        assert backend.registry.list_sessions() == ["s1"]
