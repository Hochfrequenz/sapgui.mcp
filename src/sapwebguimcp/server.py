"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from sapwebguimcp.models import BrowserManager, get_settings
from sapwebguimcp.tools import register_browser_tools, register_sap_tools

__all__ = ["main", "mcp"]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Application context available to all tools via lifespan."""

    browser_manager: BrowserManager


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Manage application lifecycle with type-safe context.

    This context manager:
    1. Creates and yields the browser manager for tools to use
    2. Cleans up browser resources on shutdown
    """
    settings = get_settings()
    browser_manager = BrowserManager(settings)

    logger.info("SAP Web GUI MCP Server starting...")
    logger.info("Server ready - waiting for MCP client connection on stdin.")
    logger.info("(JSON parse errors on empty input are normal when testing manually)")

    try:
        yield AppContext(browser_manager=browser_manager)
    finally:
        logger.info("Cleaning up browser resources...")
        await browser_manager.close()
        logger.info("Server shutdown complete")


# Create the FastMCP server instance
# Note: strict_input_validation requires the standalone fastmcp package.
# The mcp package's built-in FastMCP doesn't support it yet.
mcp = FastMCP(
    "sap-webgui-mcp",
    dependencies=["playwright", "pydantic-settings"],
    lifespan=app_lifespan,
)

# Register all tools
register_sap_tools(mcp)
register_browser_tools(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
