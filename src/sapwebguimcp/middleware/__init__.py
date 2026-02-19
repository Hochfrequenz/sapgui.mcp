"""Middleware for the SAP Web GUI MCP server."""

from sapwebguimcp.middleware.logging import ToolCallLoggingMiddleware, set_sap_identity

__all__ = ["ToolCallLoggingMiddleware", "set_sap_identity"]
