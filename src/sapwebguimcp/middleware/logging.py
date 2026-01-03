"""Logging middleware for tool call sequence analysis."""

import logging
import time
from datetime import timedelta
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from sapwebguimcp.models.middleware import SessionStats, ToolCall

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

    def _format_args(self, arguments: dict[str, Any] | None) -> dict[str, str]:
        """Format tool arguments for logging, masking sensitive values."""
        if not arguments:
            return {}
        sensitive_keys = {"password", "secret", "token", "key", "credential"}
        result: dict[str, str] = {}
        for k, v in arguments.items():
            if any(s in k.lower() for s in sensitive_keys):
                result[k] = "***"
            else:
                result[k] = str(v)
        return result

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        """Log tool call with per-session timing."""
        tool_name = context.message.name
        arguments = getattr(context.message, "arguments", None) or {}
        start = time.perf_counter()

        # Extract context IDs
        ctx = context.fastmcp_context
        session_id = getattr(ctx, "session_id", None) if ctx else None
        session = self._get_session(session_id)

        # Create tool call record
        formatted_args = self._format_args(arguments)
        current_call = ToolCall(name=tool_name, args=formatted_args)

        try:
            result = await call_next(context)
            duration = timedelta(seconds=time.perf_counter() - start)

            # Update session stats
            session.tool_calls.append(current_call)
            session.total_duration += duration
            session.call_count += 1

            _logger.info(
                "TOOL_DONE | session=%s | tool=%s | duration=%s | session_total=%s | sequence=%s",
                session_id,
                tool_name,
                duration,
                session.total_duration,
                session.format_sequence(last_n=20),
            )
            return result
        except Exception as e:
            duration = timedelta(seconds=time.perf_counter() - start)
            current_call.success = False
            session.tool_calls.append(current_call)
            session.total_duration += duration
            session.call_count += 1

            _logger.warning(
                "TOOL_FAIL | session=%s | tool=%s | duration=%s | error=%s | sequence=%s",
                session_id,
                tool_name,
                duration,
                str(e),
                session.format_sequence(last_n=20),
            )
            raise
