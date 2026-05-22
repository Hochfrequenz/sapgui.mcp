"""
MCP Server for SAP Web GUI browser automation.

This module provides the main entry point for the MCP server using FastMCP.
Tools are organized in separate modules under sapguimcp.tools.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastmcp import FastMCP
from fastmcp.apps.choice import Choice
from fastmcp.server.middleware.logging import LoggingMiddleware

from sapguimcp.backend.manager import close_backend
from sapguimcp.logging_config import configure_logging
from sapguimcp.middleware import ToolCallLoggingMiddleware
from sapguimcp.models.config import get_sap_config, get_settings
from sapguimcp.prompts import register_prompts
from sapguimcp.resources import register_feedback_resources, register_intent_resources
from sapguimcp.tools import (
    register_abapgit_tools,
    register_breakpoint_tools,
    register_browser_tools,
    register_catalog_tools,
    register_class_tools,
    register_com_tools,
    register_feedback_tools,
    register_fm_tools,
    register_intent_tools,
    register_quick_report_tools,
    register_sap_tools,
    register_script_tools,
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
    register_tree_tools,
)
from sapguimcp.tools.abapgit_tools import validate_github_pat

__all__ = ["main", "mcp"]

# Get settings (needed for logging configuration)
_settings = get_settings()

# Configure logging (including optional Papertrail)
configure_logging(
    log_format=_settings.log_format,
    log_level=_settings.log_level,
    papertrail_host=_settings.papertrail_host,
    papertrail_port=_settings.papertrail_port,
)
logger = logging.getLogger(__name__)

# Note: GitHub issue creation is handled directly in log_feedback tool (async)


async def _check_cdp_available(cdp_url: str) -> bool:
    """Check Chrome CDP availability. If not reachable, log that auto-launch will be attempted."""
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{cdp_url}/json/version", timeout=2.0)
        logger.info("[OK] Chrome CDP reachable at %s", cdp_url)
        return True
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        logger.info(
            "Chrome not detected at %s. Will attempt auto-launch when browser is needed.",
            cdp_url,
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
        from _sapguimcp_version import version as _server_version  # pylint: disable=import-outside-toplevel
    except (ImportError, SyntaxError):
        _server_version = "unknown"
    logger.info("[STARTING] SAP MCP Server v%s initializing (backend=%s)...", _server_version, _settings.backend_type)
    if _settings.backend_type == "webgui":
        cdp_ok = await _check_cdp_available(_settings.cdp_url)
        if cdp_ok:
            logger.info("[READY] Server started successfully. Waiting for MCP client connection on stdio.")
        else:
            logger.info("[READY] Server started. Chrome not detected yet — will auto-launch when browser is needed.")
    else:
        logger.info("[READY] Server started (backend=%s). Waiting for MCP client connection.", _settings.backend_type)

    # Validate GitHub PAT if configured (non-blocking, warns only)
    _current_settings = get_settings()
    effective_pat = _current_settings.abapgit_pat or _current_settings.github_pat
    _pat_source = "ABAPGIT_PAT" if _current_settings.abapgit_pat else "GITHUB_PAT"
    if effective_pat:
        pat_valid, pat_msg = await validate_github_pat(effective_pat)
        if pat_valid:
            logger.info("[OK] %s validated (user: %s)", _pat_source, pat_msg)
        else:
            logger.warning(
                "[ACTION REQUIRED] %s is invalid: %s. "
                "abapGit pulls will fail. Regenerate at https://github.com/settings/tokens",
                _pat_source,
                pat_msg,
            )

    try:
        yield
    finally:
        logger.info("[STOPPING] Cleaning up backend resources...")
        await close_backend()
        logger.info("[STOPPED] Server shutdown complete.")


# Instructions for the LLM about this MCP server — backend-specific
_WEBGUI_INSTRUCTIONS = """
SAP Web GUI automation server. Controls SAP through a Chrome browser with remote debugging enabled.

BROWSER SETUP:
Chrome is auto-launched with debugging flags when not already running.
If Chrome cannot be found automatically, set CHROME_PATH in the .env file.
The user may also pre-launch Chrome manually with --remote-debugging-port=9222.

IMPORTANT: Do NOT attempt to install Chrome or any browser.

PREREQUISITES:
- Chrome installed (auto-detected, or CHROME_PATH set in .env)
- VPN connected (if SAP system is on internal network)
- CDP proxy running (for Docker setups)

IF CONNECTION FAILS:
Do NOT try to install browsers. Instead, ask the user to verify:
1. "Is Chrome installed?" (set CHROME_PATH in .env if not auto-detected)
2. "Is your VPN connected?" (for internal SAP systems)
3. "Is the CDP proxy running?" (docker compose up -d)

COMMON ERROR CAUSES:
- "Chrome not found" / "Chrome konnte nicht ... gefunden werden": Set CHROME_PATH in .env
- "SAP URL not reachable": VPN not connected
- Login fails: Check user/password/client in ~/.config/sap-mcp/systems.json

WORKFLOW:
1. Call sap_login first to open SAP and authenticate
2. Use sap_transaction to navigate to transactions (e.g., VA01, SE16, BP)
3. Use browser_snapshot to see current screen state
4. Use browser_fill/browser_click for interactions
5. Prefer SAP-specific tools (sap_fill_form, sap_click_button) over browser_* tools when available

ESCAPE HATCHES (when SAP-specific tools are insufficient):
- browser_snapshot: See current DOM/ARIA tree
- browser_evaluate: Execute arbitrary JavaScript
- browser_click / browser_fill: Interact with elements by CSS selector
- browser_navigate: Navigate to a URL (e.g., SAP Help Portal)
"""

_CROSS_SERVER_GUIDANCE = """
WHEN TO USE THIS SERVER vs sap-adt MCP:
If sap-adt (SAP ADT MCP) tools are available, prefer them for:
- Reading/writing ABAP source code (get_source, patch_source, set_source_from_file)
- Creating ABAP objects (create_object: PROG, CLAS, INTF, FUGR, MSAG, DDLS, TABL, DTEL, DOMA)
- Transport management (get_transport_requests, create_transport, release_transport on S4)
- Activation, syntax checks, ATC checks, unit tests
- Code completion, pretty printing, refactoring
- Debugging (breakpoints, stepping, variable inspection)
- DDIC lookups (get_object_info, get_ddic_info)

Use THIS server (sap-desktop/sap-webgui) for:
- Customizing transactions (SPRO, SM30, SM34)
- Transport release on ECC (SE09 — ADT release may silently fail on ECC)
- Complex GUI interactions (popups, drag-and-drop, tree navigation)
- Transactions without ADT endpoints (SE21 on ECC, SM37, SLG1, ST22, SQVI)
- Visual verification of screen state
- abapGit operations via SAP GUI (SE80 > abapGit)

TRANSACTION SELECTION:
- Prefer dedicated transactions (SE38, SE24, SE37, SE21) over SE80
- SE80 has a complex split-screen layout that tools struggle to parse
"""

_DESKTOP_INSTRUCTIONS = """
SAP GUI Desktop automation server. Controls SAP GUI for Windows via COM Scripting (ActiveX/OLE).

PREREQUISITES:
- SAP GUI for Windows installed and running
- SAP GUI Scripting enabled on the server (RZ11 parameter: sapgui/user_scripting = TRUE)
- SAP GUI Scripting enabled on the client (SAP GUI Options > Accessibility & Scripting > Enable Scripting)
- SAP Logon landscape configured with the target connection name

CONNECTION:
The server connects using the default_system from ~/.config/sap-mcp/systems.json.
Each system entry has a sap_logon_entry field (the bold description text in the SAP Logon pad).
Override via the system_key parameter in sap_login() (pass the dictionary key from systems.json).

IF CONNECTION FAILS:
Ask the user to verify:
1. "Is SAP GUI running?" (SAP Logon must be open)
2. "Is scripting enabled?" (both server-side RZ11 and client-side SAP GUI Options)
3. "Does the sap_logon_entry in systems.json match the SAP Logon pad description exactly?"

COMMON ERROR CAUSES:
- RPC_E_DISCONNECTED: SAP GUI closed or session timed out — call sap_login() again
- "Scripting disabled": Enable in SAP GUI Options > Accessibility & Scripting
- Login fails: Check user/password/client in ~/.config/sap-mcp/systems.json

WORKFLOW:
1. Call sap_login first to open SAP and authenticate
2. Use sap_transaction to navigate to transactions (e.g., VA01, SE16, BP)
3. Use sap_com_snapshot to see the SAP GUI element tree with element IDs
4. Use SAP-specific tools (sap_fill_form, sap_click_button, sap_press_key) for interactions
5. Use sap_com_evaluate as escape hatch for operations not covered by SAP-specific tools

MULTI-SESSION SUPPORT (#671):
sap_login() opens a NEW parallel session each call — re-login does NOT
replace prior logins. You can be logged in as multiple distinct
(client, user) tuples on the same SAP Logon entry concurrently. The
LoginResult.session_id field carries the registry ID ('s1', 's2', ...)
of the new session; pass that as the `session` / `session_id` parameter
on subsequent tool calls to address THIS specific login. Use
sap_session_list to see all currently active sessions, and
sap_session_close to close any of them (including 's1' if you want).

ESCAPE HATCHES (when SAP-specific tools are insufficient):
- sap_com_snapshot: Get element tree with IDs (e.g., wnd[0]/usr/txtFIELD_NAME)
- sap_com_evaluate: Execute COM operations on elements by ID
  - action="get": Read a property (e.g., Text, Selected, Value)
  - action="set": Write a property (args=["value"])
  - action="call": Invoke a method (e.g., SendVKey on wnd[0], Press on buttons)
  - Use element IDs from sap_com_snapshot (e.g., "wnd[0]/usr/cmbFIELD")
  - VKey codes: 0=Enter, 3=F3/Back, 8=F8/Execute, 11=F11/Save, 12=F12/Cancel
- sap_run_script: Run a Python script against the live session in one round-trip
  - Use when the number of operations depends on a runtime value (rows in a grid,
    nodes in a tree, status-conditional branching) — replaces many sap_com_evaluate
    calls with a single script. Faster and uses fewer tokens.
  - Provides: session (GuiSession), output(value) to collect results
  - import and print are not available; use output() instead
"""


def _build_instructions() -> str:
    base = _DESKTOP_INSTRUCTIONS if _settings.backend_type == "desktop" else _WEBGUI_INSTRUCTIONS
    base = _CROSS_SERVER_GUIDANCE + base
    try:
        sap_cfg = get_sap_config()
        keys = list(sap_cfg.systems.keys())
        default = sap_cfg.default_system
        systems_info = (
            f"\nAVAILABLE SYSTEMS (from systems.json):\n"
            f"Default: {default!r}\n"
            f"All system keys: {keys}\n"
            f"When multiple systems are configured, use the choose tool to let the user "
            f"pick a system before calling sap_login(). "
            f"Pass the selected key as system_key to sap_login().\n"
        )
        return base + systems_info
    except (FileNotFoundError, ValueError):  # config not found or invalid — don't crash
        return base


SERVER_INSTRUCTIONS = _build_instructions()

# Create the FastMCP server instance with strict input validation
_SERVER_NAME = "sap-desktop-mcp" if _settings.backend_type == "desktop" else "sap-webgui-mcp"
mcp = FastMCP(
    _SERVER_NAME,
    instructions=SERVER_INSTRUCTIONS,
    lifespan=app_lifespan,
    strict_input_validation=True,
)

# Add logging middleware for tool call sequence analysis
mcp.add_middleware(ToolCallLoggingMiddleware())

# Add Choice provider so the LLM can present system selection UI to the user
mcp.add_provider(Choice())

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
register_breakpoint_tools(mcp)

# Always available: logging, abapgit
register_intent_tools(mcp)
register_feedback_tools(mcp)
register_abapgit_tools(mcp)

# WebGUI only: browser escape hatches, SE37 editor (no desktop impl)
if _backend == "webgui":
    register_browser_tools(mcp)
    register_se37_edit_tools(mcp)
    register_quick_report_tools(mcp)

if _backend == "desktop":
    register_com_tools(mcp)
    register_tree_tools(mcp)
    register_script_tools(mcp)

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
