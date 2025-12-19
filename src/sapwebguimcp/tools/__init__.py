"""
MCP tools for SAP Web GUI automation.

This package contains tool modules that are registered with the FastMCP server:
- sap_tools: SAP-specific tools (login, transaction, keepalive)
- browser_tools: Generic browser automation tools (click, fill, screenshot, etc.)
"""

from sapwebguimcp.tools.browser_tools import register_browser_tools
from sapwebguimcp.tools.sap_tools import register_sap_tools

__all__ = [
    "register_browser_tools",
    "register_sap_tools",
]
