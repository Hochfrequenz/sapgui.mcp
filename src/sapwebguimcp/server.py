"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from sapwebguimcp.models import close_browser_manager
from sapwebguimcp.tools import register_browser_tools, register_sap_tools

__all__ = ["main", "mcp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


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

# Register all tools
register_sap_tools(mcp)
register_browser_tools(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
