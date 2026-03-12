"""Session management tools for parallel sub-agent support."""

import logging

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models import (
    SessionBindResult,
    SessionCloseResult,
    SessionListResult,
    SessionReleaseResult,
)

__all__ = [
    "sap_session_list_impl",
    "sap_session_close_impl",
    "sap_session_bind_impl",
    "sap_session_release_impl",
]

logger = logging.getLogger(__name__)


async def sap_session_list_impl() -> SessionListResult:
    """List all active SAP sessions.

    Returns:
        SessionListResult with all sessions and their state
    """
    try:
        backend = await get_backend()
        sessions = await backend.list_sessions()
        return SessionListResult(sessions=sessions)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Listing sessions")
        return SessionListResult.failure(f"Error listing sessions: {e}")


async def sap_session_close_impl(session_id: str) -> SessionCloseResult:
    """Close a SAP session.

    Args:
        session_id: Session to close (cannot be 's1')

    Returns:
        SessionCloseResult
    """
    # Protect primary session (tool-level policy)
    if session_id == "s1":
        return SessionCloseResult.failure("Cannot close primary session 's1'. Use sap_login() to start fresh.")

    try:
        backend = await get_backend()

        if not await backend.has_session(session_id):
            sessions = await backend.list_sessions()
            available = ", ".join(s.session_id for s in sessions) or "(none)"
            return SessionCloseResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        closed = await backend.close_session(session_id)
        if not closed:
            return SessionCloseResult.failure(f"Failed to close session '{session_id}'.")

        remaining = await backend.list_sessions()
        return SessionCloseResult(
            session_id=session_id,
            remaining_sessions=len(remaining),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Closing session", extra={"session_id": session_id})
        return SessionCloseResult.failure(f"Error closing session: {e}")


async def sap_session_bind_impl(session_id: str, agent_id: str) -> SessionBindResult:
    """Bind a session to an agent.

    Args:
        session_id: Session to bind (e.g., "s2")
        agent_id: Agent identifier

    Returns:
        SessionBindResult
    """
    try:
        backend = await get_backend()

        if not await backend.has_session(session_id):
            sessions = await backend.list_sessions()
            available = ", ".join(s.session_id for s in sessions) or "(none)"
            return SessionBindResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        old_agent = await backend.bind_session(session_id, agent_id)

        return SessionBindResult(
            session_id=session_id,
            agent_id=agent_id,
            previous_agent=old_agent,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Binding session", extra={"session_id": session_id, "agent_id": agent_id})
        return SessionBindResult.failure(f"Error binding session: {e}")


async def sap_session_release_impl(session_id: str) -> SessionReleaseResult:
    """Release agent binding from a session.

    Args:
        session_id: Session to release

    Returns:
        SessionReleaseResult
    """
    try:
        backend = await get_backend()

        if not await backend.has_session(session_id):
            sessions = await backend.list_sessions()
            available = ", ".join(s.session_id for s in sessions) or "(none)"
            return SessionReleaseResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        old_agent = await backend.release_session(session_id)

        return SessionReleaseResult(
            session_id=session_id,
            released_agent=old_agent,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Releasing session", extra={"session_id": session_id})
        return SessionReleaseResult.failure(f"Error releasing session: {e}")
