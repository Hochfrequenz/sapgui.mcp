"""Tests for the server module."""

import asyncio

from fastmcp import FastMCP

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
        expected_sap_tools = {
            "sap_login",
            "sap_transaction",
            "sap_keepalive_start",
            "sap_keepalive_stop",
            "sap_get_capabilities",
        }
        assert expected_sap_tools.issubset(tool_names), f"Missing SAP tools: {expected_sap_tools - tool_names}"

    def test_sap_get_capabilities_has_description(self) -> None:
        """Test that sap_get_capabilities has a non-empty description."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        assert "sap_get_capabilities" in tools
        tool = tools["sap_get_capabilities"]
        assert tool.description is not None
        assert len(tool.description) > 50  # Should have substantial description
        assert "RECOMMENDED" in tool.description

    def test_sap_get_capabilities_returns_all_tools(self) -> None:
        """Test that sap_get_capabilities returns all registered tools."""
        # Get the tool function
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        capabilities_tool = tools["sap_get_capabilities"]

        # Call the tool function
        result = asyncio.run(capabilities_tool.fn())

        # Verify result structure
        assert result.success is True
        assert result.error is None
        assert len(result.tools) > 0

        # Verify known tools are present
        tool_names = {t.name for t in result.tools}
        expected_tools = {"sap_login", "sap_transaction", "browser_click", "log_intent"}
        assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

        # Verify tools have descriptions
        for tool_info in result.tools:
            assert tool_info.name, "Tool name should not be empty"
            assert tool_info.description, f"Tool {tool_info.name} should have description"

        # Verify SAP knowledge is loaded
        assert result.sap_knowledge is not None, "SAP knowledge should be loaded"
        assert "Keyboard Shortcuts" in result.sap_knowledge, "Knowledge should contain shortcuts section"
        assert "sap_get_shortcuts" in result.sap_knowledge, "Knowledge should mention sap_get_shortcuts"

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
