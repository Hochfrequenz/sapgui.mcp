"""Middleware for the SAP Web GUI MCP server."""

from sapwebguimcp.middleware.logging import ToolCallLoggingMiddleware

__all__ = ["ToolCallLoggingMiddleware"]
