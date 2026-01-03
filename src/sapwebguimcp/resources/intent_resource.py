"""MCP resource for retrieving intent logs."""

from fastmcp import FastMCP

from sapwebguimcp.models import IntentEntry
from sapwebguimcp.tools.intent_tools import get_session_intents

__all__ = ["register_intent_resources"]


def register_intent_resources(mcp: FastMCP) -> None:
    """Register intent log resources with the MCP server."""

    @mcp.resource("intent://session/{session_id}")
    def get_intent_log(session_id: str) -> list[IntentEntry]:
        """
        Get all intent log entries for a session.

        Returns a list of intent entries with timestamp, intent text,
        and optional context.

        Args:
            session_id: The session ID to retrieve logs for

        Returns:
            List of intent entries
        """
        return get_session_intents(session_id)
