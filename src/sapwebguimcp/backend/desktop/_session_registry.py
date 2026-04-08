"""Session registry for desktop (COM) backend.

Mirrors WebGUI's SessionRegistry but stores sapsucker GuiSession objects
instead of Playwright Pages. Stale sessions are detected on access via
a COM probe (no close-event mechanism exists for SAP GUI COM).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterable

# Reuse the conflict error from the webgui registry so callers can catch
# a single class regardless of which backend produced it. Cross-import is
# safe — ``models/session_registry.py`` only imports stdlib.
from sapwebguimcp.models.session_registry import SessionBindConflictError

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

    @property
    def primary_session(self) -> str:
        """Primary session ID: 's1' if present, else lowest available."""
        return self._default_session_id()

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
        """Return the best default session: 's1' if present, else lowest available."""
        if "s1" in self._sessions:
            return "s1"
        if self._sessions:
            return min(self._sessions.keys(), key=lambda k: int(k[1:]))
        return "s1"  # will raise in caller

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry."""
        self._sessions.pop(session_id, None)
        self._bindings.pop(session_id, None)
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
