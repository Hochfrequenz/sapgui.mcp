"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.logging import LoggingMiddleware

from sapwebguimcp.models import close_browser_manager
from sapwebguimcp.tools import register_browser_tools, register_sap_tools

__all__ = ["main", "mcp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class SessionStats:
    """Accumulated statistics for a session."""

    tool_calls: list[str] = field(default_factory=list)
    total_duration: timedelta = field(default_factory=lambda: timedelta())
    call_count: int = 0


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

        logger.info(
            "TOOL_CALL | session=%s | tool=%s | call_number=%d | sequence=%s",
            session_id,
            tool_name,
            session.call_count + 1,
            " -> ".join(session.tool_calls[-3:] + [tool_name]) if session.tool_calls else tool_name,
        )

        try:
            result = await call_next(context)
            duration = timedelta(seconds=time.perf_counter() - start)

            # Update session stats
            session.tool_calls.append(tool_name)
            session.total_duration += duration
            session.call_count += 1

            logger.info(
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

            logger.info(
                "TOOL_FAIL | session=%s | tool=%s | duration=%s | error=%s",
                session_id,
                tool_name,
                duration,
                str(e),
            )
            raise


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """
    Manage application lifecycle.

    This context manager handles cleanup of browser resources on shutdown.
    The browser manager is initialized lazily on first use via get_browser_manager().
    """
    logger.info("SAP Web GUI MCP Server starting...")
    logger.info("Server ready - waiting for MCP client connection on stdin.")
    logger.info("(JSON parse errors on empty input are normal when testing manually)")

    try:
        yield
    finally:
        logger.info("Cleaning up browser resources...")
        await close_browser_manager()
        logger.info("Server shutdown complete")


# Create the FastMCP server instance with strict input validation
mcp = FastMCP(
    "sap-webgui-mcp",
    lifespan=app_lifespan,
    strict_input_validation=True,
)

# Add logging middleware for tool call sequence analysis
mcp.add_middleware(ToolCallLoggingMiddleware())

# Add FastMCP built-in logging with payload visibility
mcp.add_middleware(LoggingMiddleware(include_payloads=True, max_payload_length=1000))

# Register all tools
register_sap_tools(mcp)
register_browser_tools(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
