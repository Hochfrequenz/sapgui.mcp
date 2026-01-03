"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from sapwebguimcp.models import close_browser_manager
from sapwebguimcp.tools import register_browser_tools, register_sap_tools

__all__ = ["main", "mcp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ToolCallLoggingMiddleware(Middleware):
    """Middleware to log tool calls with context for sequence analysis."""

    async def on_call_tool(
        self, context: MiddlewareContext, call_next: Any
    ) -> Any:
        """Log tool call with request context and timing."""
        tool_name = context.message.params.get("name", "unknown")
        start = time.perf_counter()

        # Extract context IDs if available
        ctx = context.fastmcp_context
        request_id = getattr(ctx, "request_id", None) if ctx else None
        session_id = getattr(ctx, "session_id", None) if ctx else None
        client_id = getattr(ctx, "client_id", None) if ctx else None

        logger.info(
            "TOOL_CALL_START | tool=%s | session=%s | request=%s | client=%s",
            tool_name,
            session_id,
            request_id,
            client_id,
        )

        try:
            result = await call_next(context)
            duration = timedelta(seconds=time.perf_counter() - start)

            logger.info(
                "TOOL_CALL_END | tool=%s | session=%s | duration=%s | success=True",
                tool_name,
                session_id,
                duration,
            )
            return result
        except Exception as e:
            duration = timedelta(seconds=time.perf_counter() - start)
            logger.info(
                "TOOL_CALL_END | tool=%s | session=%s | duration=%s | success=False | error=%s",
                tool_name,
                session_id,
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

# Register all tools
register_sap_tools(mcp)
register_browser_tools(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
