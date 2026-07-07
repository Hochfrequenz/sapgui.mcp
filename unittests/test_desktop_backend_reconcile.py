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

import sapguimcp.backend.desktop as desktop_module
from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.backend.desktop._session_registry import DesktopSessionRegistry


def _make_backend() -> DesktopBackend:
    """Build a DesktopBackend with a fresh registry, mocked ComThread, and a real lock."""
    backend = DesktopBackend.__new__(DesktopBackend)
    backend.registry = DesktopSessionRegistry()
    backend.com = MagicMock()
    backend._mutation_lock = asyncio.Lock()
    return backend


# COM error codes — mirrors sapguimcp.backend.desktop._com_thread's private constants.
_RPC_E_CALL_REJECTED = -2147418111  # "server busy", e.g. a modal dialog blocking the message loop
_RPC_S_UNKNOWN_IF = -2147023179  # stale interface — the window is actually gone


def _com_error(code: int, message: str = "boom") -> Exception:
    """Build an exception carrying a COM ``hresult``, as pywin32's com_error does."""
    exc = RuntimeError(message)
    exc.hresult = code  # type: ignore[attr-defined]
    return exc


def _make_mock_session(label: str = "ses", *, alive: bool = True, error: Exception | None = None) -> MagicMock:
    """Create a mock GuiSession.

    The reconcile probe calls ``s.com.FindById("wnd[0]").Type``. By default
    we configure that chain to return a non-empty string (alive). When
    ``alive=False`` we make ``FindById`` raise so the probe fails — this
    drives the test via the mock's *behaviour*, not by introspecting the
    lambda's source, which would be brittle to refactors. Pass ``error`` to
    control exactly which exception the probe raises (e.g. a COM error with
    a specific ``hresult``, via :func:`_com_error`) instead of the generic
    ``RuntimeError`` used for a plain "dead" session.
    """
    session = MagicMock()
    session.com = MagicMock()
    session.label = label  # for human-readable assertions
    if alive:
        session.com.FindById.return_value.Type = "GuiMainWindow"
    else:
        session.com.FindById.side_effect = error or RuntimeError(f"{label} dead")
    return session


def _make_busy_session(label: str = "ses") -> MagicMock:
    """A session whose probe always raises a 'server busy' COM error.

    Simulates a modal dialog (e.g. the ABAP debugger, issue #791) blocking
    the SAP GUI process's message loop: the process is alive, it just
    rejects the incoming COM call.
    """
    return _make_mock_session(label, alive=False, error=_com_error(_RPC_E_CALL_REJECTED, f"{label} busy"))


def _make_stale_interface_session(label: str = "ses") -> MagicMock:
    """A session whose probe raises the stale-interface COM error (genuinely dead)."""
    return _make_mock_session(label, alive=False, error=_com_error(_RPC_S_UNKNOWN_IF, f"{label} stale"))


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
    async def test_busy_session_is_kept_not_pruned(self) -> None:
        """A 'server busy' COM error (e.g. modal debugger open) must NOT prune the session.

        Regression test for issue #791: an external ABAP breakpoint firing
        opens a modal debugger, the SAP GUI process rejects the liveness
        probe with RPC_E_CALL_REJECTED/RETRYLATER, and the old code treated
        every probe exception as proof of death — collapsing the whole
        session registry even though the session was still there, just busy.
        """
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_busy_session("s2"))
        backend.com.run = _passthrough_run

        report = await backend.reconcile()

        assert sorted(report["alive"]) == ["s1", "s2"]
        assert report["removed"] == []
        assert sorted(backend.registry.list_sessions()) == ["s1", "s2"]

    @pytest.mark.anyio
    async def test_busy_session_binding_survives(self) -> None:
        backend = _make_backend()
        backend.registry.register(_make_busy_session("s1"))
        backend.registry.bind("s1", "agent-x")
        backend.com.run = _passthrough_run

        await backend.reconcile()

        assert backend.registry.get_bound_agent("s1") == "agent-x"
        assert backend.registry.list_sessions() == ["s1"]

    @pytest.mark.anyio
    async def test_stale_interface_session_is_still_pruned(self) -> None:
        """RPC_S_UNKNOWN_IF (stale interface) is a genuinely dead session, not busy.

        Guards the original #637 intent: this specific error code must keep
        failing fast and pruning immediately, unaffected by the #791 busy-
        error carve-out above.
        """
        backend = _make_backend()
        backend.registry.register(_make_mock_session("s1", alive=True))
        backend.registry.register(_make_stale_interface_session("s2"))
        backend.com.run = _passthrough_run

        report = await backend.reconcile()

        assert report["alive"] == ["s1"]
        assert report["removed"] == ["s2"]
        assert backend.registry.list_sessions() == ["s1"]

    @pytest.mark.anyio
    async def test_busy_session_pruned_after_exceeding_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A session stuck 'busy' forever must eventually be reclaimable.

        Keeping every busy probe alive indefinitely (the fix above) would
        turn a genuinely wedged/corrupted COM proxy that happens to raise a
        busy-flavoured error into an unrecoverable zombie: never pruned, its
        binding never freed. ``_RECONCILE_BUSY_DEAD_TIMEOUT_S`` bounds how
        long "busy" is given the benefit of the doubt before it's treated
        as dead like any other unresponsive session.
        """
        backend = _make_backend()
        backend.registry.register(_make_busy_session("s1"))
        backend.registry.bind("s1", "agent-x")
        backend.com.run = _passthrough_run
        backend._RECONCILE_BUSY_DEAD_TIMEOUT_S = 60.0

        clock = {"t": 1_000.0}
        monkeypatch.setattr(desktop_module.time, "monotonic", lambda: clock["t"])

        first = await backend.reconcile()
        assert first["alive"] == ["s1"]  # just went busy, still within budget

        clock["t"] += 61.0  # exceed the busy timeout while still busy
        second = await backend.reconcile()

        assert second["removed"] == ["s1"]
        assert backend.registry.list_sessions() == []
        assert backend.registry.get_bound_agent("s1") is None

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
    async def test_busy_non_primary_session_is_not_orphaned(self) -> None:
        """A busy session must not be silently unregistered by reset_to_primary.

        Regression test for issue #791 follow-up: reconcile now keeps a busy
        session in the registry (it's not dead), so reset_to_primary's
        victims loop can reach it. Closing it hits the same process-wide
        busy COM error that made it busy in the first place — the old
        unconditional-unregister behavior would still have dropped it from
        the registry and reported 'closed', orphaning a live, in-use session
        (e.g. a human mid-breakpoint) from the MCP's bookkeeping.
        """
        backend = _make_backend()
        s1 = _make_mock_session("s1", alive=True)
        # The busy condition is process-wide: any COM call through this
        # process — including CloseSession issued via the primary's parent —
        # gets rejected the same way while a modal dialog blocks it.
        s1.com.Parent.CloseSession.side_effect = _com_error(_RPC_E_CALL_REJECTED, "busy")
        backend.registry.register(s1)
        backend.registry.register(_make_busy_session("s2"))
        backend.registry.bind("s2", "agent-debugging")
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        assert "s2" not in report["closed"]
        assert "agent-debugging" not in report["killed_agents"]
        assert any("s2" in e for e in report["errors"])
        assert "s2" in backend.registry.list_sessions()
        assert backend.registry.get_bound_agent("s2") == "agent-debugging"

    @pytest.mark.anyio
    async def test_busy_primary_session_is_kept_not_treated_as_victim(self) -> None:
        """A busy PRIMARY session must stay the keeper, not become a victim.

        Regression test for a reset_to_primary() inversion found by review:
        it used to resolve "primary" via the busy-aware `registry.primary_session`
        (correct for call routing, wrong here). With a busy s1 (e.g. a human
        mid-breakpoint-debug) and an idle stray s2, that made s2 look
        "primary" and put the actively-used s1 in the victims list — trying
        to close the session a human is using while leaving the real stray
        session (s2) untouched. `canonical_primary_session` fixes this: s1
        stays primary regardless of busy status, so s2 (the real stray) is
        the only victim, and closing it never even touches s1's busy COM.
        """
        backend = _make_backend()
        backend.registry.register(_make_busy_session("s1"))
        backend.registry.bind("s1", "agent-debugging")
        backend.registry.register(_make_mock_session("s2", alive=True))
        backend.com.run = _passthrough_run

        report = await backend.reset_to_primary()

        assert report["closed"] == ["s2"]
        assert report["errors"] == []
        assert report["killed_agents"] == []
        assert "s1" in backend.registry.list_sessions()
        assert backend.registry.get_bound_agent("s1") == "agent-debugging"

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
