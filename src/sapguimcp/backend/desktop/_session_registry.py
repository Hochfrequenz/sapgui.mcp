"""Session registry for desktop (COM) backend.

Mirrors WebGUI's SessionRegistry but stores sapsucker GuiSession objects
instead of Playwright Pages. Stale sessions are detected on access via
a COM probe (no close-event mechanism exists for SAP GUI COM).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable

# Reuse the conflict error from the webgui registry so callers can catch
# a single class regardless of which backend produced it.
from sapguimcp.models.base import SessionBindConflictError

if TYPE_CHECKING:
    from sapsucker.components.session import GuiSession

logger = logging.getLogger(__name__)


class DesktopSessionRegistry:
    """Tracks SAP GUI desktop sessions with sequential IDs (s1, s2, ...).

    Provides the same interface as WebGUI's ``SessionRegistry`` for
    consistent session management across both backends.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, GuiSession] = {}
        self._bindings: dict[str, str] = {}  # session_id -> agent_id
        self._counter: int = 0
        # session_id -> monotonic timestamp of when it was first observed
        # "busy" (a modal dialog blocking the SAP GUI message loop — see
        # ``DesktopBackend._reconcile_locked`` / issue #791). A busy session
        # is NOT dead, but default-session resolution should still prefer a
        # responsive session over one that's currently blocked.
        self._busy_since: dict[str, float] = {}

    @property
    def primary_session(self) -> str:
        """Best session to route a new call to: 's1' if present and responsive,
        else the lowest-numbered responsive session, else 's1'/lowest if all
        are busy.

        Deliberately busy-aware (issue #791) so call routing (``get_session(None)``,
        ``BackendManager`` default-session resolution) doesn't keep hammering a
        session stuck behind a modal dialog. Do NOT use this to decide which
        session a cleanup sweep should *keep* — see ``canonical_primary_session``.
        """
        return self._default_session_id()

    def canonical_primary_session(self) -> str:
        """The session that defines "primary" for cleanup purposes: 's1' if
        present, else the lowest-numbered session — ignoring busy status.

        ``reset_to_primary()`` uses this (not ``primary_session``) to decide
        which session survives a sweep. A session being busy (e.g. a human
        mid-breakpoint-debug, issue #791) does not make it less "primary" —
        conflating this with the busy-aware call-routing default would make
        reset_to_primary try to close the very session a human is actively
        using while leaving an idle stray session untouched.
        """
        candidates = sorted(self._sessions.keys(), key=lambda k: int(k[1:]))
        if not candidates:
            return "s1"  # will raise in caller
        return "s1" if "s1" in candidates else candidates[0]

    def mark_busy(self, session_id: str, now: float) -> float:
        """Record *session_id* as busy, returning when it was first seen busy.

        Idempotent: the first call for a still-busy session stores ``now``
        and returns it; later calls (while it remains busy) keep returning
        that original timestamp so the caller can measure how long it has
        been stuck.
        """
        return self._busy_since.setdefault(session_id, now)

    def mark_alive(self, session_id: str) -> None:
        """Clear busy tracking for *session_id* — the probe succeeded again."""
        self._busy_since.pop(session_id, None)

    def is_busy(self, session_id: str) -> bool:
        """Whether *session_id* is currently flagged busy (not dead)."""
        return session_id in self._busy_since

    def busy_since(self, session_id: str) -> float | None:
        """Monotonic timestamp *session_id* was first observed busy, or None."""
        return self._busy_since.get(session_id)

    def register(self, session: GuiSession) -> str:
        """Register a session and return its ID (s1, s2, ...)."""
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = session
        logger.info("Registered desktop session", extra={"session": session_id})
        return session_id

    def get_session(self, session_id: str | None) -> GuiSession:
        """Get the GuiSession for a session ID.

        When *session_id* is ``None`` the registry picks the best default:
        ``"s1"`` if it exists, otherwise the lowest numbered active session.
        This avoids hard-coding ``"s1"`` which breaks after sessions are
        created and closed (counter keeps incrementing).

        Raises ``ValueError`` if the session is not found in the registry.

        Note: does NOT probe COM liveness here because ``get_session`` is
        called on the async thread, not the COM thread.  Accessing COM
        objects outside the COM thread causes ``CoInitialize`` errors.
        Stale sessions are detected when actual COM calls fail.
        """
        sid = session_id or self._default_session_id()
        if sid not in self._sessions:
            available = ", ".join(sorted(self._sessions.keys())) or "(none)"
            raise ValueError(f"Session '{sid}' not found. Active: {available}.")
        return self._sessions[sid]

    def _default_session_id(self) -> str:
        """Return the best default session: 's1' if present, else lowest available.

        Prefers a responsive (non-busy) session over one currently blocked by
        a modal dialog (issue #791) — otherwise a fresh login would silently
        keep resolving to a stuck ``s1`` instead of the newly opened session.
        Falls back to the busy candidate if it's the only one, since
        returning *something* beats raising for an operator who explicitly
        wants to poke the busy session.
        """
        candidates = sorted(self._sessions.keys(), key=lambda k: int(k[1:]))
        if not candidates:
            return "s1"  # will raise in caller
        responsive = [sid for sid in candidates if not self.is_busy(sid)]
        pool = responsive or candidates
        return "s1" if "s1" in pool else pool[0]

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry."""
        self._sessions.pop(session_id, None)
        self._bindings.pop(session_id, None)
        self._busy_since.pop(session_id, None)
        logger.info("Unregistered desktop session", extra={"session": session_id})

    def prune(self, dead_ids: Iterable[str]) -> list[str]:
        """Remove a set of session IDs from the registry in one pass.

        Used by ``DesktopBackend.reconcile()`` after a batch of liveness
        probes has identified which sessions are no longer alive on the SAP
        side. Returns the IDs that were actually removed (i.e. were present
        in ``_sessions`` before the call) so the caller can log/report them.

        **Auto-clears bindings.** Any agent bindings on the pruned sessions
        are dropped as a side effect — the binding contract from #643 says
        a binding has the same lifetime as its underlying session. Agents
        whose sessions were pruned will appear in the
        ``reset_to_primary``-style ``killed_agents`` reports and must
        re-bind to a different session before continuing.

        This is intentionally synchronous and COM-free — the registry has
        no COM access (see the class-level docstring) and the actual probes
        are performed by ``DesktopBackend`` on the COM thread.
        """
        removed: list[str] = []
        for sid in dead_ids:
            agent = self._bindings.get(sid)
            if self._sessions.pop(sid, None) is not None:
                removed.append(sid)
                self._bindings.pop(sid, None)
                self._busy_since.pop(sid, None)
                logger.info(
                    "Pruned dead desktop session",
                    extra={"session": sid, "bound_to": agent},
                )
        return removed

    def clear(self) -> None:
        """Drop every session and binding, and reset the ID counter to 0.

        **Not used by ``DesktopBackend.login()`` anymore** — issue #671
        replaced the production "drop everything on re-login" path with
        ``DesktopBackend._reconcile_locked()``, which probes every tracked
        session and prunes only the dead ones. That preserves issue #633's
        dead-session recovery contract while leaving live sessions intact
        for the parallel-multi-mandant topology.

        ``clear()`` is still here as a test-only utility (and as the
        backward-compat path for the ``DesktopBackend._session = None``
        setter, which a few legacy tests use to reset state). Production
        code should call :meth:`prune` via ``_reconcile_locked()`` instead.
        """
        had_sessions = bool(self._sessions)
        self._sessions.clear()
        self._bindings.clear()
        self._busy_since.clear()
        self._counter = 0
        if had_sessions:
            logger.info("Cleared desktop session registry")

    def bind(self, session_id: str, agent_id: str, *, force: bool = False) -> None:
        """Bind a session to an agent.

        Strict by default (issue #643): raises
        :class:`SessionBindConflictError` if the session is already bound
        to a different agent. Re-binding the same agent is idempotent.
        Pass ``force=True`` to take over.
        """
        current = self._bindings.get(session_id)
        if current is not None and current != agent_id and not force:
            raise SessionBindConflictError(
                session_id=session_id,
                current_agent=current,
                requested_agent=agent_id,
            )
        self._bindings[session_id] = agent_id
        if current is not None and current != agent_id:
            logger.info(
                "Replaced desktop session binding (force=True)",
                extra={
                    "session": session_id,
                    "previous_agent": current,
                    "agent_id": agent_id,
                },
            )
        else:
            logger.info("Bound session", extra={"session": session_id, "agent_id": agent_id})

    def release(self, session_id: str) -> None:
        """Release agent binding from a session."""
        old = self._bindings.pop(session_id, None)
        if old:
            logger.info("Released session", extra={"session": session_id, "agent_id": old})

    def check_binding(self, session_id: str, agent_id: str | None, tool_name: str) -> None:
        """Check if agent is authorized to access session (warn-only, never blocks)."""
        bound = self._bindings.get(session_id)
        if bound is None:
            return
        if agent_id is None:
            logger.warning(
                "Bound session accessed without agent_id",
                extra={"session": session_id, "bound_to": bound, "tool": tool_name},
            )
        elif agent_id != bound:
            logger.warning(
                "Cross-agent session access",
                extra={"session": session_id, "bound_to": bound, "accessed_by": agent_id, "tool": tool_name},
            )

    def get_bound_agent(self, session_id: str) -> str | None:
        """Get the agent bound to a session (or None)."""
        return self._bindings.get(session_id)

    def list_sessions(self) -> list[str]:
        """List all registered session IDs."""
        return list(self._sessions.keys())

    def has_session(self, session_id: str) -> bool:
        """Check whether a session exists in the registry."""
        return session_id in self._sessions
