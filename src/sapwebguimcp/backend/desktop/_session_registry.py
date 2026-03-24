"""Session registry for desktop (COM) backend.

Mirrors WebGUI's SessionRegistry but stores sapsucker GuiSession objects
instead of Playwright Pages. Stale sessions are detected on access via
a COM probe (no close-event mechanism exists for SAP GUI COM).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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

    def register(self, session: GuiSession) -> str:
        """Register a session and return its ID (s1, s2, ...)."""
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = session
        logger.info("Registered desktop session", extra={"session": session_id})
        return session_id

    def get_session(self, session_id: str | None) -> GuiSession:
        """Get the GuiSession for a session ID.  ``None`` defaults to ``'s1'``.

        Raises ``ValueError`` if the session is not found in the registry.

        Note: does NOT probe COM liveness here because ``get_session`` is
        called on the async thread, not the COM thread.  Accessing COM
        objects outside the COM thread causes ``CoInitialize`` errors.
        Stale sessions are detected when actual COM calls fail.
        """
        sid = session_id or "s1"
        if sid not in self._sessions:
            available = ", ".join(sorted(self._sessions.keys())) or "(none)"
            raise ValueError(f"Session '{sid}' not found. Active: {available}.")
        return self._sessions[sid]

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry."""
        self._sessions.pop(session_id, None)
        self._bindings.pop(session_id, None)
        logger.info("Unregistered desktop session", extra={"session": session_id})

    def bind(self, session_id: str, agent_id: str) -> None:
        """Bind a session to an agent."""
        self._bindings[session_id] = agent_id
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
