"""MCP resource for retrieving intent logs."""

import json

from fastmcp import FastMCP

from sapguimcp.tools.intent_tools import get_session_intents

__all__ = ["register_intent_resources"]


def register_intent_resources(mcp: FastMCP) -> None:
    """Register intent log resources with the MCP server."""

    @mcp.resource("intent://session/{session_id}")
    def get_intent_log(session_id: str) -> str:
        """
        Get all intent log entries for a session.

        Returns a list of intent entries with timestamp, intent text,
        and optional context.

        Args:
            session_id: The session ID to retrieve logs for

        Returns:
            JSON string of intent entries
        """
        entries = get_session_intents(session_id)
        return json.dumps([e.model_dump(mode="json") for e in entries])
