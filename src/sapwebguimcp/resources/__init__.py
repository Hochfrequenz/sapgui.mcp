"""MCP resources for SAP WebGUI MCP server."""

from sapwebguimcp.resources.bapi_catalog_resource import register_bapi_catalog_resources
from sapwebguimcp.resources.feedback_resource import register_feedback_resources
from sapwebguimcp.resources.intent_resource import register_intent_resources

__all__ = [
    "register_bapi_catalog_resources",
    "register_feedback_resources",
    "register_intent_resources",
]
