"""MCP resources for SAP WebGUI MCP server."""

from sapguimcp.resources.feedback_resource import register_feedback_resources
from sapguimcp.resources.intent_resource import register_intent_resources

__all__ = ["register_feedback_resources", "register_intent_resources"]
