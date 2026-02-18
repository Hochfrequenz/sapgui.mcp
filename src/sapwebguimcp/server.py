"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from sapwebguimcp.logging_config import configure_logging
from sapwebguimcp.loghandlers import IntentFileHandler
from sapwebguimcp.middleware import ToolCallLoggingMiddleware
from sapwebguimcp.models import close_browser_manager
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.prompts import register_prompts
from sapwebguimcp.resources import register_feedback_resources, register_intent_resources
from sapwebguimcp.tools import (
    register_abapgit_tools,
    register_browser_tools,
    register_catalog_tools,
    register_class_tools,
    register_feedback_tools,
    register_fm_tools,
    register_intent_tools,
    register_sap_tools,
    register_se11_tools,
    register_se16_tools,
    register_se24_tools,
    register_se37_tools,
    register_se93_tools,
    register_table_tools,
    register_workflow_tools,
)

__all__ = ["main", "mcp", "_check_cdp_available"]

# Get settings (needed for logging configuration)
_settings = get_settings()

# Configure logging (including optional Papertrail)
configure_logging(papertrail_host=_settings.papertrail_host, papertrail_port=_settings.papertrail_port)
logger = logging.getLogger(__name__)

# Configure intent file handler if AUDIT_LOG_DIR is set
if _settings.audit_log_dir:
    _intent_handler = IntentFileHandler(Path(_settings.audit_log_dir))
    logging.getLogger().addHandler(_intent_handler)
    logger.info("Intent audit logging enabled: %s", _settings.audit_log_dir)

# Note: GitHub issue creation is handled directly in log_feedback tool (async)


async def _check_cdp_available(cdp_url: str) -> None:
    """Log Chrome CDP availability status. Non-blocking — warns but does not fail."""
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{cdp_url}/json/version", timeout=2.0)
        logger.info("Chrome CDP detected at %s", cdp_url)
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        logger.warning(
            "Chrome not detected on CDP. "
            "Please start Chrome with: "
            'chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome-debug"'
        )


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """
    Manage application lifecycle.

    This context manager handles cleanup of browser resources on shutdown.
    The browser manager is initialized lazily on first use via get_browser_manager().
    """
    logger.info("SAP Web GUI MCP Server starting...")
    await _check_cdp_available(_settings.cdp_url)
    logger.info("Server ready - waiting for MCP client connection on stdin.")
    logger.info("(JSON parse errors on empty input are normal when testing manually)")

    try:
        yield
    finally:
        logger.info("Cleaning up browser resources...")
        await close_browser_manager()
        logger.info("Server shutdown complete")


# Instructions for the LLM about this MCP server
SERVER_INSTRUCTIONS = """
SAP Web GUI automation server. Controls SAP through a Chrome browser with remote debugging enabled.

IMPORTANT: Do NOT attempt to install Chrome or any browser. The user must start Chrome manually.

PREREQUISITES (user must set up BEFORE using these tools):
- Chrome running with --remote-debugging-port=9222 (user starts this manually)
- VPN connected (if SAP system is on internal network)
- CDP proxy running (for Docker setups)

IF CONNECTION FAILS:
Do NOT try to install browsers. Instead, ask the user to verify:
1. "Is Chrome running with --remote-debugging-port=9222?"
2. "Is your VPN connected?" (for internal SAP systems)
3. "Is the CDP proxy running?" (docker compose up -d)

COMMON ERROR CAUSES:
- "Cannot connect to browser": Chrome not started with debugging flags, or CDP proxy not running
- "SAP URL not reachable": VPN not connected
- Login fails: Check SAP_USER, SAP_PASSWORD, SAP_MANDANT environment variables

WORKFLOW:
1. Call sap_login first to open SAP and authenticate
2. Use sap_transaction to navigate to transactions (e.g., VA01, SE16, BP)
3. Use browser_snapshot to see current screen state
4. Use browser_fill/browser_click for interactions
"""

# Create the FastMCP server instance with strict input validation
mcp = FastMCP(
    "sap-webgui-mcp",
    instructions=SERVER_INSTRUCTIONS,
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
register_se16_tools(mcp)
register_se24_tools(mcp)
register_se37_tools(mcp)
register_se93_tools(mcp)
register_catalog_tools(mcp)
register_table_tools(mcp)
register_fm_tools(mcp)
register_class_tools(mcp)
register_browser_tools(mcp)
register_intent_tools(mcp)
register_feedback_tools(mcp)
register_workflow_tools(mcp)
register_abapgit_tools(mcp)

# Register prompts
register_prompts(mcp)

# Register resources
register_intent_resources(mcp)
register_feedback_resources(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
