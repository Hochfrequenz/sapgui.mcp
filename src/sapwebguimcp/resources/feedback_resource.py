"""MCP resource for retrieving feedback logs."""

from fastmcp import FastMCP

from sapwebguimcp.models import FeedbackEntry
from sapwebguimcp.tools.feedback_tools import get_session_feedback

__all__ = ["register_feedback_resources"]


def register_feedback_resources(mcp: FastMCP) -> None:
    """Register feedback log resources with the MCP server."""

    @mcp.resource("feedback://session/{session_id}")
    def get_feedback_log(session_id: str) -> list[FeedbackEntry]:
        """
        Get all feedback log entries for a session.

        Returns a list of feedback entries with timestamp, feedback text,
        and optional tags.

        IMPORTANT: When problems occurred during the session, forward this
        feedback to the technical contact (developer/Ansprechpartner) so they
        can investigate and improve the tooling. This feedback is valuable
        for identifying issues and optimization opportunities.

        Args:
            session_id: The session ID to retrieve logs for

        Returns:
            List of feedback entries
        """
        return get_session_feedback(session_id)
