"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapwebguimcp.tools.
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastmcp import FastMCP
from fastmcp.server.middleware.logging import LoggingMiddleware

from sapwebguimcp.backend.manager import close_backend
from sapwebguimcp.logging_config import configure_logging
from sapwebguimcp.middleware import ToolCallLoggingMiddleware
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.prompts import register_prompts
from sapwebguimcp.resources import register_feedback_resources, register_intent_resources
from sapwebguimcp.tools import (
    register_abapgit_tools,
    register_browser_tools,
    register_catalog_tools,
    register_class_tools,
    register_com_tools,
    register_feedback_tools,
    register_fm_tools,
    register_intent_tools,
    register_quick_report_tools,
    register_sap_tools,
    register_se09_tools,
    register_se11_tools,
    register_se16_tools,
    register_se24_edit_tools,
    register_se24_tools,
    register_se37_edit_tools,
    register_se37_tools,
    register_se38_edit_tools,
    register_se93_tools,
    register_slg1_tools,
    register_sm30_tools,
    register_sm37_tools,
    register_spro_tools,
    register_st22_tools,
    register_table_tools,
    register_workflow_tools,
)
from sapwebguimcp.tools.abapgit_tools import validate_github_pat

__all__ = ["main", "mcp"]

# Get settings (needed for logging configuration)
_settings = get_settings()

# Configure logging (including optional Papertrail)
configure_logging(papertrail_host=_settings.papertrail_host, papertrail_port=_settings.papertrail_port)
logger = logging.getLogger(__name__)

# Note: GitHub issue creation is handled directly in log_feedback tool (async)


async def _check_cdp_available(cdp_url: str) -> bool:
    """Check Chrome CDP availability and log status. Non-blocking — warns but does not fail."""
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{cdp_url}/json/version", timeout=2.0)
        logger.info("[OK] Chrome CDP reachable at %s", cdp_url)
        return True
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        if sys.platform == "win32":
            hint = (
                '& "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"'
                ' --remote-debugging-port=9222 --user-data-dir="C:\\temp\\chrome-debug"'
                " (NOTE: Chrome path may differ — if installed per-user, try"
                ' "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe" instead)'
            )
        elif sys.platform == "darwin":
            hint = (
                '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"'
                " --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug"
            )
        else:
            hint = "google-chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug"
        logger.warning(
            "[ACTION REQUIRED] Chrome not detected at %s. "
            "Start Chrome with remote debugging, then restart this server: %s",
            cdp_url,
            hint,
        )
        return False


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """
    Manage application lifecycle.

    This context manager handles cleanup of backend resources on shutdown.
    The backend is initialized lazily on first tool call via get_backend().
    """
    try:
        from _sapwebguimcp_version import version as _server_version
    except (ImportError, SyntaxError):
        _server_version = "unknown"
    logger.info("[STARTING] SAP MCP Server v%s initializing (backend=%s)...", _server_version, _settings.backend_type)
    if _settings.backend_type == "webgui":
        cdp_ok = await _check_cdp_available(_settings.cdp_url)
        if cdp_ok:
            logger.info("[READY] Server started successfully. Waiting for MCP client connection on stdio.")
        else:
            logger.info("[WAITING] Server started but Chrome is not available. Start Chrome, then restart this server.")
    else:
        logger.info("[READY] Server started (backend=%s). Waiting for MCP client connection.", _settings.backend_type)

    # Validate GitHub PAT if configured (non-blocking, warns only)
    _current_settings = get_settings()
    effective_pat = _current_settings.abapgit_pat or _current_settings.github_pat
    if effective_pat:
        pat_valid, pat_msg = await validate_github_pat(effective_pat)
        if pat_valid:
            logger.info("[OK] GitHub PAT validated (user: %s)", pat_msg)
        else:
            logger.warning(
                "[ACTION REQUIRED] GitHub PAT is invalid: %s. "
                "abapGit pulls will fail. Regenerate at https://github.com/settings/tokens",
                pat_msg,
            )

    try:
        yield
    finally:
        logger.info("[STOPPING] Cleaning up backend resources...")
        await close_backend()
        logger.info("[STOPPED] Server shutdown complete.")


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

# Register tools — conditionally based on backend type
_backend = _settings.backend_type

# Always available: SAP tools + transaction-specific tools
register_sap_tools(mcp)
register_se11_tools(mcp)
register_se16_tools(mcp)
register_se24_tools(mcp)
register_se37_tools(mcp)
register_se09_tools(mcp)
register_se93_tools(mcp)
register_slg1_tools(mcp)
register_sm30_tools(mcp)
register_sm37_tools(mcp)
register_spro_tools(mcp)
register_st22_tools(mcp)
register_catalog_tools(mcp)
register_table_tools(mcp)
register_fm_tools(mcp)
register_class_tools(mcp)
register_se24_edit_tools(mcp)
register_se38_edit_tools(mcp)

# Always available: logging and workflows
register_intent_tools(mcp)
register_feedback_tools(mcp)
register_workflow_tools(mcp)

# WebGUI only: browser escape hatches, abapgit (JS-dependent), SE37 editor (no desktop impl)
if _backend == "webgui":
    register_browser_tools(mcp)
    register_abapgit_tools(mcp)
    register_se37_edit_tools(mcp)
    register_quick_report_tools(mcp)

# Desktop only: COM escape hatches
if _backend == "desktop":
    register_com_tools(mcp)

# Register prompts
register_prompts(mcp)

# Register resources
register_intent_resources(mcp)
register_feedback_resources(mcp)


def main() -> None:
    """Main entry point for the MCP server."""
    try:
        mcp.run(show_banner=False)
    except Exception:
        logger.critical("[CRASHED] Server crashed with unhandled exception", exc_info=True)
        raise
    finally:
        logging.shutdown()


if __name__ == "__main__":
    main()
