"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from sapwebguimcp.loghandlers import IntentFileHandler
from sapwebguimcp.middleware import ToolCallLoggingMiddleware
from sapwebguimcp.models import close_browser_manager
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.resources import register_feedback_resources, register_intent_resources
from sapwebguimcp.tools import (
    register_browser_tools,
    register_feedback_tools,
    register_intent_tools,
    register_sap_tools,
    register_se11_tools,
    register_workflow_tools,
)

__all__ = ["main", "mcp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Get settings for handler configuration
_settings = get_settings()

# Configure intent file handler if AUDIT_LOG_DIR is set
if _settings.audit_log_dir:
    _intent_handler = IntentFileHandler(Path(_settings.audit_log_dir))
    logging.getLogger().addHandler(_intent_handler)
    logger.info("Intent audit logging enabled: %s", _settings.audit_log_dir)

# Note: GitHub issue creation is handled directly in log_feedback tool (async)


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
register_se11_tools(mcp)
register_browser_tools(mcp)
register_intent_tools(mcp)
register_feedback_tools(mcp)
register_workflow_tools(mcp)

# Register resources
register_intent_resources(mcp)
register_feedback_resources(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
