"""Middleware for the SAP Web GUI MCP server."""

from sapguimcp.middleware.logging import ToolCallLoggingMiddleware, set_sap_identity

__all__ = ["ToolCallLoggingMiddleware", "set_sap_identity"]
