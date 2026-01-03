"""
MCP tools for SAP Web GUI automation.

This package contains tool modules that are registered with the FastMCP server:
- sap_tools: SAP-specific tools (login, transaction, keepalive)
- browser_tools: Generic browser automation tools (click, fill, screenshot, etc.)
- intent_tools: Intent logging for audit trail
"""

from sapwebguimcp.tools.browser_tools import register_browser_tools
from sapwebguimcp.tools.intent_tools import (
    clear_session_intents,
    get_session_intents,
    register_intent_tools,
)
from sapwebguimcp.tools.sap_tools import register_sap_tools

__all__ = [
    "register_browser_tools",
    "register_intent_tools",
    "register_sap_tools",
    "get_session_intents",
    "clear_session_intents",
]
