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
import secrets
import time
import uuid
from datetime import timedelta
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from sapguimcp.models.middleware import SapIdentity, SessionStats, ToolCall

__all__ = ["ToolCallLoggingMiddleware", "new_request_id", "set_sap_identity"]

_logger = logging.getLogger(__name__)


def new_request_id() -> str:
    """Generate a UUID v7 string for use as a per-tool-call correlation ID.

    UUID v7 is time-ordered (RFC 9562): the high 48 bits encode the unix
    timestamp in milliseconds, so log entries cluster naturally by emission
    time when sorted lexically. We implement v7 inline rather than pull in
    a third-party library since CPython only added uuid7 in 3.13 and the
    package supports >=3.11.
    """
    ts_ms = (time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    n = (ts_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return str(uuid.UUID(int=n))


# Module-level reference for cross-boundary communication (tools -> middleware).
_sessions_ref: dict[str, SessionStats] = {}


def set_sap_identity(session_id: str | None, identity: SapIdentity) -> None:
    """Set SAP identity for a session. Called by sap_login after successful login."""
    key = session_id or "unknown"
    if key not in _sessions_ref:
        _sessions_ref[key] = SessionStats()
    _sessions_ref[key].sap_identity = identity


class ToolCallLoggingMiddleware(Middleware):
    """Middleware to log tool calls with per-session timing and sequence tracking.

    Logs tool call sequences, durations, and transaction round times for
    analyzing repetitive SAP workflows.
    """

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, SessionStats] = _sessions_ref

    def _get_session(self, session_id: str | None) -> SessionStats:
        """Get or create session stats."""
        key = session_id or "unknown"
        if key not in self._sessions:
            self._sessions[key] = SessionStats()
        return self._sessions[key]

    def _identity_extra(self, session: SessionStats) -> dict[str, str]:
        """Extract identity fields from session for log extra."""
        if session.sap_identity is None:
            return {}
        return session.sap_identity.model_dump(mode="json")

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
        request_id = new_request_id()
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
            extra = {
                "request_id": request_id,
                "tool": tool_name,
                "session": session_id,
                "duration_ms": int(duration.total_seconds() * 1000),
                "error": str(e),
                "seq": session.format_sequence(last_n=20),
            }
            extra.update(self._identity_extra(session))
            _logger.warning("Tool failed", extra=extra, exc_info=True)
            raise

        # Update session stats and log success
        duration = timedelta(seconds=time.perf_counter() - start)
        session.tool_calls.append(current_call)
        session.total_duration += duration
        session.call_count += 1

        extra = {
            "request_id": request_id,
            "tool": tool_name,
            "session": session_id,
            "duration_ms": int(duration.total_seconds() * 1000),
            "total_ms": int(session.total_duration.total_seconds() * 1000),
            "seq": session.format_sequence(last_n=20, current_round_only=True),
        }
        if round_time is not None:
            extra["round_time_ms"] = int(round_time.total_seconds() * 1000)
        extra.update(self._identity_extra(session))
        _logger.info("Tool completed", extra=extra)
        return result
