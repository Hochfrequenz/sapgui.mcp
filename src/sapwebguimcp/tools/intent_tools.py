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

    @mcp.tool(
        description=(
            "MANDATORY: Log intent for audit trail when using SAP. "
            "You MUST call this at the start of every SAP task and before "
            "any SAP write operation. Required for compliance and accountability."
        )
    )
    async def log_intent(
        intent: str,
        context: dict[str, str] | None = None,
        ctx: Context | None = None,
    ) -> IntentLogResult:
        """
        MANDATORY: Log a high-level intent for audit trail.

        You MUST use this tool when performing SAP operations. This is REQUIRED
        for compliance and accountability in SAP environments - not optional.

        WHEN TO CALL (required):
        - ALWAYS at the start of every SAP-related user request
        - ALWAYS before any SAP write operation (create, update, delete, post)
        - At milestones during multi-step SAP workflows (e.g., "Order 3 of 10")
        - Before running transactions that modify data

        Args:
            intent: High-level description of what was requested or what you
                    intend to do (e.g., "User requested to create sales order
                    for customer 12345")
            context: Optional context dict (e.g., {"tcode": "VA01", "customer": "12345"})

        Returns:
            IntentLogResult with logged status, entry_id, and session_id
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

        return IntentLogResult(
            logged=True,
            entry_id=entry.entry_id,
            session_id=session_key,
        )
