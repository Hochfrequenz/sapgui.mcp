"""Logging middleware for tool call sequence analysis."""

import logging
import time
from datetime import timedelta
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from sapwebguimcp.models.middleware import SessionStats

__all__ = ["ToolCallLoggingMiddleware"]

_logger = logging.getLogger(__name__)


class ToolCallLoggingMiddleware(Middleware):
    """Middleware to log tool calls with per-session timing and sequence tracking."""

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, SessionStats] = {}

    def _get_session(self, session_id: str | None) -> SessionStats:
        """Get or create session stats."""
        key = session_id or "unknown"
        if key not in self._sessions:
            self._sessions[key] = SessionStats()
        return self._sessions[key]

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        """Log tool call with per-session timing."""
        tool_name = context.message.params.get("name", "unknown")
        start = time.perf_counter()

        # Extract context IDs
        ctx = context.fastmcp_context
        session_id = getattr(ctx, "session_id", None) if ctx else None
        session = self._get_session(session_id)

        # Show sequence: last 3 calls -> current
        sequence = " -> ".join(session.tool_calls[-3:] + [tool_name]) if session.tool_calls else tool_name

        _logger.debug(
            "TOOL_CALL | session=%s | tool=%s | call_number=%d | sequence=%s",
            session_id,
            tool_name,
            session.call_count + 1,
            sequence,
        )

        try:
            result = await call_next(context)
            duration = timedelta(seconds=time.perf_counter() - start)

            # Update session stats
            session.tool_calls.append(tool_name)
            session.total_duration += duration
            session.call_count += 1

            _logger.info(
                "TOOL_DONE | session=%s | tool=%s | duration=%s | session_total=%s",
                session_id,
                tool_name,
                duration,
                session.total_duration,
            )
            return result
        except Exception as e:
            duration = timedelta(seconds=time.perf_counter() - start)
            session.tool_calls.append(f"{tool_name}[FAILED]")
            session.total_duration += duration
            session.call_count += 1

            _logger.warning(
                "TOOL_FAIL | session=%s | tool=%s | duration=%s | error=%s",
                session_id,
                tool_name,
                duration,
                str(e),
            )
            raise
