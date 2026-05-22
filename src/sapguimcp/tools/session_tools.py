"""Session management tools for parallel sub-agent support."""

import logging

from sapguimcp.backend.manager import get_backend
from sapguimcp.models import (
    SessionBindResult,
    SessionCloseResult,
    SessionListResult,
    SessionReleaseResult,
    SessionResetResult,
)
from sapguimcp.models.base import SessionBindConflictError

__all__ = [
    "sap_session_list_impl",
    "sap_session_close_impl",
    "sap_session_bind_impl",
    "sap_session_release_impl",
    "sap_session_reset_to_primary_impl",
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

    Any session ID can be closed, including ``s1``. With the parallel-
    multi-mandant contract (#671), the registry can hold multiple
    concurrent logins, and the LLM may legitimately want to close any
    of them — including the lowest-numbered one. If the closed session
    was the only one in the registry, subsequent tool calls will fail
    with a clear "no session" error and the LLM should call
    ``sap_login`` again.

    Args:
        session_id: Session to close (e.g. "s1", "s2", ...)

    Returns:
        SessionCloseResult
    """
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


async def sap_session_bind_impl(
    session_id: str,
    agent_id: str,
    *,
    force: bool = False,
) -> SessionBindResult:
    """Bind a session to an agent.

    Strict by default (#643): if the session is already bound to a different
    agent, the bind fails with a clear error and the LLM can either pick a
    different session or retry with ``force=True``. Re-binding the same agent
    is idempotent (no-op success).

    Args:
        session_id: Session to bind (e.g., "s2")
        agent_id: Agent identifier
        force: Take over the binding even if another agent currently holds
            it. Use only for crash recovery — prefer the strict default
            otherwise so the conflict is surfaced to the LLM.

    Returns:
        SessionBindResult
    """
    try:
        backend = await get_backend()

        if not await backend.has_session(session_id):
            sessions = await backend.list_sessions()
            available = ", ".join(s.session_id for s in sessions) or "(none)"
            return SessionBindResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        old_agent = await backend.bind_session(session_id, agent_id, force=force)

        return SessionBindResult(
            session_id=session_id,
            agent_id=agent_id,
            previous_agent=old_agent,
        )

    except SessionBindConflictError as conflict:
        # Strict-bind conflict — surface a helpful message that points the
        # LLM at the two recovery paths (different session, or force=True).
        return SessionBindResult.failure(
            f"Session '{conflict.session_id}' is already bound to agent "
            f"'{conflict.current_agent}'. Pick a different session via "
            f"sap_session_list, or retry with force=true to take over the binding."
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


async def sap_session_reset_to_primary_impl() -> SessionResetResult:
    """Close every SAP session except the primary one (s1).

    Use this when parallel agents have left the session set drifted from the
    real GUI window state — typically after a batch of failed/retried tool
    calls. Behaviour:

    - Reconciles the registry first (drops dead sessions, see issue #637)
    - Iterates the surviving non-primary sessions and closes each one
    - Reports which sessions were closed, which remain, and which agent
      bindings were severed in the process

    Agents listed in ``killed_agents`` MUST rebind to a different session
    via ``sap_session_bind`` before their next call, otherwise their next
    tool call will fail with "session not found".

    Returns:
        SessionResetResult
    """
    try:
        backend = await get_backend()
        # Both WebGuiBackend and DesktopBackend implement reset_to_primary;
        # the BackendManager union type enforces this. No defensive guard.
        report = await backend.reset_to_primary()
        return SessionResetResult(
            closed_sessions=report.get("closed", []),
            remaining_sessions=report.get("remaining", []),
            killed_agents=report.get("killed_agents", []),
            errors=report.get("errors", []),
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Resetting sessions to primary")
        return SessionResetResult.failure(f"Error resetting sessions: {e}")
