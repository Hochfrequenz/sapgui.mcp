"""Tests for the server module."""

import pytest

from sapwebguimcp.server import mcp


class TestMcpServer:
    """Tests for FastMCP server."""

    def test_mcp_server_exists(self) -> None:
        """Test that mcp server instance exists."""
        from mcp.server.fastmcp import FastMCP

        assert isinstance(mcp, FastMCP)

    def test_mcp_server_has_name(self) -> None:
        """Test that the server has the correct name."""
        assert mcp.name == "sap-webgui-mcp"

    def test_mcp_server_has_tools(self) -> None:
        """Test that tools are registered with the server."""
        # FastMCP registers tools via decorators, check some exist
        tool_names = [tool.name for tool in mcp._tool_manager._tools.values()]
        assert "sap_login" in tool_names
        assert "sap_transaction" in tool_names
        assert "browser_click" in tool_names
        assert "browser_screenshot" in tool_names
