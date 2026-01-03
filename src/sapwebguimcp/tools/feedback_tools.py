"""
Feedback logging tools for model observations.

This module provides the log_feedback tool for models to document
patterns, friction points, and optimization opportunities.
"""

import logging
from datetime import datetime, timezone

from fastmcp import Context, FastMCP

from sapwebguimcp.models import FeedbackEntry, FeedbackLogResult

__all__ = ["register_feedback_tools", "get_session_feedback", "clear_session_feedback"]

_logger = logging.getLogger(__name__)

# In-memory store for feedback entries per session
_session_feedback: dict[str, list[FeedbackEntry]] = {}


def get_session_feedback(session_id: str) -> list[FeedbackEntry]:
    """Get all feedback entries for a session."""
    return _session_feedback.get(session_id, [])


def clear_session_feedback(session_id: str) -> None:
    """Clear feedback entries for a session."""
    _session_feedback.pop(session_id, None)


def register_feedback_tools(mcp: FastMCP) -> None:
    """Register feedback logging tools with the MCP server."""

    @mcp.tool(
        description=(
            "Log technical feedback about tool usage patterns, friction points, "
            "or optimization opportunities. You are encouraged to use this "
            "whenever you notice something that could improve the tooling."
        )
    )
    async def log_feedback(
        feedback: str,
        tags: list[str] | None = None,
        ctx: Context | None = None,
    ) -> FeedbackLogResult:
        """
        Log technical feedback for tooling optimization.

        You are ENCOURAGED to use this tool whenever you notice patterns,
        friction, or improvement ideas during SAP operations. Your feedback
        is read by developers to optimize the MCP server tooling.

        FORMATTING: If GITHUB_PAT is configured, feedback is automatically
        posted as a GitHub issue. Use GitHub-flavored Markdown for formatting:
        - Use `backticks` for code, selectors, tool names
        - Use **bold** for emphasis
        - Use bullet lists for multiple points
        - Use code blocks for longer code snippets

        BE DETAILED AND TECHNICAL - include:
        - Specific tool names and parameters
        - Selector paths that were hard to find
        - Timing observations (e.g., "browser_wait took 5s")
        - What you tried before finding the solution
        - Error messages encountered

        SUGGESTED TAGS:
        - "tool-combination": Two+ tools always used together, could be merged
        - "repetition": Same tool called multiple times in sequence
        - "selector": Selector was hard to find or unreliable
        - "timing": Operation was slow or timeout occurred
        - "workflow": Multi-step process that could be simplified
        - "missing-tool": Functionality that should exist but doesn't
        - "error-handling": Error recovery was difficult
        - "deadlock": Got stuck in a loop or needed user intervention
        - "problem": Encountered an issue that blocked progress

        EXAMPLES - Optimization observations:
        - "`sap_transaction('VA01')` requires `browser_wait` for `#ToolbarOkCode`
          every time - these could be combined" ["tool-combination", "va01"]
        - "Pagination in **SM37** required 3 `browser_click` calls on the same
          selector `button[title=Next]`" ["repetition", "sm37"]
        - "Couldn't find save button until I tried selector
          `span:has-text(Sichern)` - EN selector didn't work" ["selector"]
        - "`browser_wait` timeout after 30s on SE16 table load with 10k rows,
          had to increase to 60s" ["timing", "se16"]

        EXAMPLES - Problems and deadlocks (important for developers!):
        - "Got stuck in a loop clicking **OK** on error popup that kept
          reappearing - needed user to manually dismiss it" ["deadlock"]
        - "Tried 5 different selectors for the material field but none
          worked, user had to identify the correct one" ["problem", "selector"]
        - "Transaction **SE16N** kept timing out, attempted 3 retries with
          increasing timeouts but ultimately needed user intervention"
          ["problem", "timing"]
        - "Could not determine which button to click for `save as variant`,
          UI had multiple similar options" ["problem", "workflow"]

        Args:
            feedback: Detailed technical description of the observation
            tags: Optional list of tags for categorization

        Returns:
            FeedbackLogResult with logged status, entry_id, and session_id
        """
        session_id = getattr(ctx, "session_id", None) if ctx else None
        session_key = session_id or "unknown"

        entry = FeedbackEntry(
            timestamp=datetime.now(timezone.utc),
            session_id=session_key,
            feedback=feedback,
            tags=tags or [],
        )

        # Store in memory
        if session_key not in _session_feedback:
            _session_feedback[session_key] = []
        _session_feedback[session_key].append(entry)

        # Log for handler to pick up
        tags_str = ", ".join(tags) if tags else ""
        _logger.info(
            "FEEDBACK | session=%s | entry_id=%s | %s | tags=[%s]",
            session_key,
            entry.entry_id,
            feedback,
            tags_str,
        )

        return FeedbackLogResult(
            logged=True,
            entry_id=entry.entry_id,
            session_id=session_key,
        )
