"""
MCP tools for SAP Web GUI automation.

This package contains tool modules that are registered with the FastMCP server:
- sap_tools: SAP-specific tools (login, transaction, keepalive)
- browser_tools: Generic browser automation tools (click, fill, screenshot, etc.)
- intent_tools: Intent logging for audit trail
- feedback_tools: Feedback logging for optimization observations
"""

from sapwebguimcp.tools.browser_tools import register_browser_tools
from sapwebguimcp.tools.feedback_tools import (
    clear_session_feedback,
    get_session_feedback,
    register_feedback_tools,
)
from sapwebguimcp.tools.intent_tools import (
    clear_session_intents,
    get_session_intents,
    register_intent_tools,
)
from sapwebguimcp.tools.sap_tools import register_sap_tools
from sapwebguimcp.tools.se11_tools import register_se11_tools
from sapwebguimcp.tools.se16_tools import register_se16_tools
from sapwebguimcp.tools.se24_tools import register_se24_tools
from sapwebguimcp.tools.se37_tools import register_se37_tools
from sapwebguimcp.tools.se93_tools import register_se93_tools
from sapwebguimcp.tools.workflow_tools import register_workflow_tools

__all__ = [
    "register_browser_tools",
    "register_feedback_tools",
    "register_intent_tools",
    "register_sap_tools",
    "register_se11_tools",
    "register_se16_tools",
    "register_se24_tools",
    "register_se37_tools",
    "register_se93_tools",
    "register_workflow_tools",
    "get_session_feedback",
    "clear_session_feedback",
    "get_session_intents",
    "clear_session_intents",
]
