"""Session management tools for parallel sub-agent support."""

import logging

from sapwebguimcp.models import (
    SessionBindResult,
    SessionCloseResult,
    SessionInfo,
    SessionListResult,
    SessionOpenResult,
    SessionReleaseResult,
    get_browser_manager,
)

__all__ = [
    "sap_session_open_impl",
    "sap_session_list_impl",
    "sap_session_close_impl",
    "sap_session_bind_impl",
    "sap_session_release_impl",
]

logger = logging.getLogger(__name__)


async def sap_session_open_impl(
    tcode: str | None = None,
    agent_id: str | None = None,
) -> SessionOpenResult:
    """Create a new SAP session via /o command.

    Args:
        tcode: Optional transaction to open in new session
        agent_id: Optional agent identifier for binding

    Returns:
        SessionOpenResult with new session_id
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        # Get primary session page to execute /o command
        if not registry.has_session("s1"):
            return SessionOpenResult.failure("No primary session. Call sap_login() first.")

        primary_page = registry.get_page("s1")
        context = primary_page.context

        # Count pages before
        pages_before = len(context.pages)

        # Execute /o or /o<tcode> to open new session
        ok_code_field = await primary_page.query_selector("#ToolbarOkCode")
        if not ok_code_field:
            return SessionOpenResult.failure("Could not find OK code field")

        command = f"/o{tcode}" if tcode else "/o"
        await ok_code_field.fill(command)
        await primary_page.keyboard.press("Enter")

        # Wait for new tab
        await primary_page.wait_for_timeout(2000)

        # Check for new page
        if len(context.pages) <= pages_before:
            return SessionOpenResult.failure(
                "SAP session limit reached (typically 6 per user). " + "Close unused sessions with sap_session_close()."
            )

        # Register new page (with optional binding)
        new_page = context.pages[-1]
        session_id = registry.register(new_page, agent_id=agent_id)

        return SessionOpenResult(
            session_id=session_id,
            tcode=tcode,
            agent_id=agent_id,
            session_count=len(registry.list_sessions()),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error opening new session")
        return SessionOpenResult.failure(f"Error opening session: {e}")


async def sap_session_list_impl() -> SessionListResult:
    """List all active SAP sessions.

    Returns:
        SessionListResult with all sessions and their state
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        sessions: list[SessionInfo] = []

        for session_id in registry.list_sessions():
            try:
                page = registry.get_page(session_id)
                title = await page.title()

                sessions.append(
                    SessionInfo(
                        session_id=session_id,
                        title=title,
                        is_primary=(session_id == "s1"),
                        agent_id=registry.get_bound_agent(session_id),
                    )
                )
            except ValueError:
                # Session expired, skip
                continue

        return SessionListResult(sessions=sessions)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error listing sessions")
        return SessionListResult.failure(f"Error listing sessions: {e}")


async def sap_session_close_impl(session_id: str) -> SessionCloseResult:
    """Close a SAP session.

    Args:
        session_id: Session to close (cannot be 's1')

    Returns:
        SessionCloseResult
    """
    # Protect primary session
    if session_id == "s1":
        return SessionCloseResult.failure("Cannot close primary session 's1'. Use sap_login() to start fresh.")

    try:
        manager = await get_browser_manager()
        registry = manager.registry

        if not registry.has_session(session_id):
            available = ", ".join(registry.list_sessions()) or "(none)"
            return SessionCloseResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        page = registry.get_page(session_id)

        # Close SAP session gracefully with /nex
        try:
            ok_code_field = await page.query_selector("#ToolbarOkCode")
            if ok_code_field:
                await ok_code_field.fill("/nex")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(500)
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # Page might already be closing

        # Close browser tab
        if not page.is_closed():
            await page.close()

        # Unregister (might already be done by close event)
        registry.unregister(session_id)

        return SessionCloseResult(
            session_id=session_id,
            remaining_sessions=len(registry.list_sessions()),
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error closing session")
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
        manager = await get_browser_manager()
        registry = manager.registry

        if not registry.has_session(session_id):
            available = ", ".join(registry.list_sessions()) or "(none)"
            return SessionBindResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        old_agent = registry.get_bound_agent(session_id)
        registry.bind(session_id, agent_id)

        return SessionBindResult(
            session_id=session_id,
            agent_id=agent_id,
            previous_agent=old_agent,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error binding session")
        return SessionBindResult.failure(f"Error binding session: {e}")


async def sap_session_release_impl(session_id: str) -> SessionReleaseResult:
    """Release agent binding from a session.

    Args:
        session_id: Session to release

    Returns:
        SessionReleaseResult
    """
    try:
        manager = await get_browser_manager()
        registry = manager.registry

        if not registry.has_session(session_id):
            available = ", ".join(registry.list_sessions()) or "(none)"
            return SessionReleaseResult.failure(f"Session '{session_id}' not found. Active: {available}.")

        old_agent = registry.get_bound_agent(session_id)
        registry.release(session_id)

        return SessionReleaseResult(
            session_id=session_id,
            released_agent=old_agent,
        )

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("Error releasing session")
        return SessionReleaseResult.failure(f"Error releasing session: {e}")
