"""Logging middleware for tool call sequence analysis.

This middleware tracks:
- Tool call sequences with arguments (last 20 calls shown)
- Per-session cumulative timing
- Transaction round times (time between consecutive calls to the same transaction)

Transaction Round Tracking:
    When using MCP tools for repetitive SAP tasks (e.g., processing invoices,
    updating master data), calling the same transaction again indicates the
    start of a new iteration. The middleware measures the time between these
    calls as "round_time", helping identify:
    - Average time per iteration
    - Performance degradation over many iterations
    - Workflow bottlenecks

Example log output (with StructuredFormatter):
    Tool completed tool=sap_transaction session=abc duration_ms=1500
    round_time_ms=154000 total_ms=300000 seq=...

    The round_time_ms=154000 shows it took ~2.5 minutes since the last
    sap_transaction call, representing one complete processing cycle.
"""

import logging
import time
from datetime import timedelta
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from sapwebguimcp.models.middleware import SessionStats, ToolCall

__all__ = ["ToolCallLoggingMiddleware"]

_logger = logging.getLogger(__name__)


class ToolCallLoggingMiddleware(Middleware):
    """Middleware to log tool calls with per-session timing and sequence tracking.

    Logs tool call sequences, durations, and transaction round times for
    analyzing repetitive SAP workflows.
    """

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
        sensitive_keys = {"password", "secret", "token", "credential", "api_key", "secret_key"}
        result: dict[str, str] = {}
        for k, v in arguments.items():
            if any(s in k.lower() for s in sensitive_keys):
                result[k] = "***"
            else:
                result[k] = str(v)
        return result

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:  # pylint: disable=too-many-locals
        """Log tool call with per-session timing."""
        tool_name = context.message.name
        args = self._format_args(getattr(context.message, "arguments", None) or {})
        start = time.perf_counter()

        ctx = context.fastmcp_context
        session_id = getattr(ctx, "session_id", None) if ctx else None
        session = self._get_session(session_id)
        current_call = ToolCall(name=tool_name, args=args)

        # Track transaction round times (resets round_start_index if same tcode)
        round_time: timedelta | None = None
        if tool_name == "sap_transaction" and (tcode := args.get("tcode")):
            round_time = session.record_transaction(tcode)

        try:
            result = await call_next(context)
        except Exception as e:
            duration = timedelta(seconds=time.perf_counter() - start)
            current_call.success = False
            session.tool_calls.append(current_call)
            session.total_duration += duration
            session.call_count += 1
            _logger.warning(
                "Tool failed",
                extra={
                    "tool": tool_name,
                    "session": session_id,
                    "duration_ms": int(duration.total_seconds() * 1000),
                    "error": str(e),
                    "seq": session.format_sequence(last_n=20),
                },
            )
            raise

        # Update session stats and log success
        duration = timedelta(seconds=time.perf_counter() - start)
        session.tool_calls.append(current_call)
        session.total_duration += duration
        session.call_count += 1

        extra = {
            "tool": tool_name,
            "session": session_id,
            "duration_ms": int(duration.total_seconds() * 1000),
            "total_ms": int(session.total_duration.total_seconds() * 1000),
            "seq": session.format_sequence(last_n=20, current_round_only=True),
        }
        if round_time is not None:
            extra["round_time_ms"] = int(round_time.total_seconds() * 1000)
        _logger.info("Tool completed", extra=extra)
        return result
