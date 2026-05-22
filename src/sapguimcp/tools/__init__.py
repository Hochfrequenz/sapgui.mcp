"""
MCP tools for SAP Web GUI automation.

This package contains tool modules that are registered with the FastMCP server:
- sap_tools: SAP-specific tools (login, transaction, keepalive)
- browser_tools: Generic browser automation tools (click, fill, screenshot, etc.)
- intent_tools: Intent logging for accountability
- feedback_tools: Feedback logging for optimization observations
"""

from sapguimcp.tools.abapgit_tools import register_abapgit_tools
from sapguimcp.tools.breakpoint_tools import register_breakpoint_tools
from sapguimcp.tools.browser_tools import register_browser_tools
from sapguimcp.tools.catalog_tools import register_catalog_tools
from sapguimcp.tools.class_tools import register_class_tools
from sapguimcp.tools.com_tools import register_com_tools
from sapguimcp.tools.feedback_tools import (
    clear_session_feedback,
    get_session_feedback,
    register_feedback_tools,
)
from sapguimcp.tools.fm_tools import register_fm_tools
from sapguimcp.tools.intent_tools import (
    clear_session_intents,
    get_session_intents,
    register_intent_tools,
)
from sapguimcp.tools.quick_report_tools import register_quick_report_tools
from sapguimcp.tools.sap_tools import register_sap_tools
from sapguimcp.tools.script_tools import register_script_tools
from sapguimcp.tools.se09_tools import register_se09_tools
from sapguimcp.tools.se11_tools import register_se11_tools
from sapguimcp.tools.se16_tools import register_se16_tools
from sapguimcp.tools.se24_edit_tools import register_se24_edit_tools
from sapguimcp.tools.se24_tools import register_se24_tools
from sapguimcp.tools.se37_edit_tools import register_se37_edit_tools
from sapguimcp.tools.se37_tools import register_se37_tools
from sapguimcp.tools.se38_edit_tools import register_se38_edit_tools
from sapguimcp.tools.se93_tools import register_se93_tools
from sapguimcp.tools.slg1_tools import register_slg1_tools
from sapguimcp.tools.sm30_tools import register_sm30_tools
from sapguimcp.tools.sm37_tools import register_sm37_tools
from sapguimcp.tools.spro_tools import register_spro_tools
from sapguimcp.tools.st22_tools import register_st22_tools
from sapguimcp.tools.table_tools import register_table_tools
from sapguimcp.tools.tree_tools import register_tree_tools

__all__ = [
    "register_abapgit_tools",
    "register_breakpoint_tools",
    "register_browser_tools",
    "register_catalog_tools",
    "register_com_tools",
    "register_class_tools",
    "register_feedback_tools",
    "register_fm_tools",
    "register_intent_tools",
    "register_quick_report_tools",
    "register_sap_tools",
    "register_script_tools",
    "register_se11_tools",
    "register_se16_tools",
    "register_se24_edit_tools",
    "register_se24_tools",
    "register_se37_edit_tools",
    "register_se37_tools",
    "register_se38_edit_tools",
    "register_se09_tools",
    "register_se93_tools",
    "register_slg1_tools",
    "register_sm30_tools",
    "register_spro_tools",
    "register_sm37_tools",
    "register_st22_tools",
    "register_table_tools",
    "register_tree_tools",
    "get_session_feedback",
    "clear_session_feedback",
    "get_session_intents",
    "clear_session_intents",
]
