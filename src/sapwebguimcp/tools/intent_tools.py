"""
Intent logging tools for audit trail.

This module provides the log_intent tool for models to document their
high-level intentions, creating an audit trail for accountability.
"""

import logging
from datetime import datetime, timezone

from fastmcp import Context, FastMCP

from sapwebguimcp.models import IntentEntry, IntentLogResult

__all__ = ["register_intent_tools", "get_session_intents", "clear_session_intents"]

_logger = logging.getLogger(__name__)

# In-memory store for intent entries per session
_session_intents: dict[str, list[IntentEntry]] = {}


def get_session_intents(session_id: str) -> list[IntentEntry]:
    """Get all intent entries for a session."""
    return _session_intents.get(session_id, [])


def clear_session_intents(session_id: str) -> None:
    """Clear intent entries for a session."""
    _session_intents.pop(session_id, None)


def register_intent_tools(mcp: FastMCP) -> None:
    """Register intent logging tools with the MCP server."""

    @mcp.tool(description="Log a high-level intent for audit trail")
    async def log_intent(
        intent: str,
        context: dict[str, str] | None = None,
        ctx: Context | None = None,
    ) -> IntentLogResult:
        """
        Log a high-level intent for audit trail.

        Use this to document what the user requested or what action you're about
        to perform. This creates an audit trail for accountability, separate from
        technical tool call logs.

        Call this:
        - At the start of a user request to document what was asked
        - Before significant write operations
        - At milestones (e.g., "Document 3 of 10 complete")

        Args:
            intent: High-level description of the intent
            context: Optional context dict (e.g., {"tcode": "VA02", "document_id": "4711"})

        Returns:
            IntentLogResult with logged status and entry_id
        """
        session_id = getattr(ctx, "session_id", None) if ctx else None
        session_key = session_id or "unknown"

        entry = IntentEntry(
            timestamp=datetime.now(timezone.utc),
            session_id=session_key,
            intent=intent,
            context=context or {},
        )

        # Store in memory
        if session_key not in _session_intents:
            _session_intents[session_key] = []
        _session_intents[session_key].append(entry)

        # Log for handler to pick up
        context_str = ", ".join(f"{k}={v}" for k, v in (context or {}).items())
        _logger.info(
            "INTENT | session=%s | entry_id=%s | %s | context={%s}",
            session_key,
            entry.entry_id,
            intent,
            context_str,
        )

        return IntentLogResult(logged=True, entry_id=entry.entry_id)
