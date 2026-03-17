"""Session registry for desktop (COM) backend.

Mirrors WebGUI's SessionRegistry but stores pysapgui GuiSession objects
instead of Playwright Pages. Stale sessions are detected on access via
a COM probe (no close-event mechanism exists for SAP GUI COM).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sapwebguimcp.sapgui.components.session import GuiSession

logger = logging.getLogger(__name__)

#: Seconds to cache the "session is alive" probe result.
#: Set high enough that normal tool call sequences don't trigger repeated probes.
_PROBE_TTL_SECONDS = 30.0


class DesktopSessionRegistry:
    """Tracks SAP GUI desktop sessions with sequential IDs (s1, s2, ...).

    Provides the same interface as WebGUI's ``SessionRegistry`` for
    consistent session management across both backends.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, GuiSession] = {}
        self._bindings: dict[str, str] = {}  # session_id -> agent_id
        self._counter: int = 0
        self._last_probe: dict[str, float] = {}  # session_id -> monotonic timestamp

    def register(self, session: GuiSession) -> str:
        """Register a session and return its ID (s1, s2, ...)."""
        self._counter += 1
        session_id = f"s{self._counter}"
        self._sessions[session_id] = session
        self._last_probe[session_id] = time.monotonic()
        logger.info("Registered desktop session", extra={"session": session_id})
        return session_id

    def get_session(self, session_id: str | None) -> GuiSession:
        """Get the GuiSession for a session ID.  ``None`` defaults to ``'s1'``.

        Probes the COM session to verify it is still alive (with TTL cache).
        Raises ``ValueError`` if the session is not found or has expired.
        """
        sid = session_id or "s1"
        if sid not in self._sessions:
            available = ", ".join(sorted(self._sessions.keys())) or "(none)"
            raise ValueError(f"Session '{sid}' not found. Active: {available}.")
        session = self._sessions[sid]
        # Probe with TTL cache — avoid a COM roundtrip on every tool call
        now = time.monotonic()
        last = self._last_probe.get(sid, 0.0)
        if now - last > _PROBE_TTL_SECONDS:
            try:
                _ = session.com.Info.Transaction  # Quick COM liveness probe
            except Exception as exc:
                self._sessions.pop(sid, None)
                self._bindings.pop(sid, None)
                self._last_probe.pop(sid, None)
                raise ValueError(f"Session '{sid}' expired (SAP session closed).") from exc
            self._last_probe[sid] = now
        return session

    def unregister(self, session_id: str) -> None:
        """Remove a session from the registry."""
        self._sessions.pop(session_id, None)
        self._bindings.pop(session_id, None)
        self._last_probe.pop(session_id, None)
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
