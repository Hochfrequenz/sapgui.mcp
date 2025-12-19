"""Tests for the server module."""

from mcp.server.fastmcp import FastMCP

from sapwebguimcp.server import mcp


class TestMcpServer:
    """Tests for FastMCP server configuration."""

    def test_mcp_server_is_fastmcp_instance(self) -> None:
        """Test that mcp is a FastMCP instance."""
        assert isinstance(mcp, FastMCP)

    def test_mcp_server_has_correct_name(self) -> None:
        """Test that the server has the expected name."""
        assert mcp.name == "sap-webgui-mcp"

    def test_sap_tools_are_registered(self) -> None:
        """Test that SAP-specific tools are registered."""
        tool_names = {tool.name for tool in mcp._tool_manager._tools.values()}
        expected_sap_tools = {"sap_login", "sap_transaction", "sap_keepalive_start", "sap_keepalive_stop"}
        assert expected_sap_tools.issubset(tool_names), f"Missing SAP tools: {expected_sap_tools - tool_names}"

    def test_browser_tools_are_registered(self) -> None:
        """Test that browser automation tools are registered."""
        tool_names = {tool.name for tool in mcp._tool_manager._tools.values()}
        expected_browser_tools = {
            "browser_click",
            "browser_fill",
            "browser_keyboard",
            "browser_navigate",
            "browser_screenshot",
            "browser_snapshot",
            "browser_evaluate",
            "browser_wait",
            "browser_get_html",
            "browser_select_option",
        }
        assert expected_browser_tools.issubset(
            tool_names
        ), f"Missing browser tools: {expected_browser_tools - tool_names}"
