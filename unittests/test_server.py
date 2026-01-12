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

    def test_catalog_tools_are_registered(self) -> None:
        """Test that transaction catalog tools are registered."""
        tool_names = {tool.name for tool in mcp._tool_manager._tools.values()}
        expected_catalog_tools = {
            "search_transactions",
        }
        assert expected_catalog_tools.issubset(
            tool_names
        ), f"Missing catalog tools: {expected_catalog_tools - tool_names}"

    def test_search_transactions_has_description(self) -> None:
        """Test that search_transactions has a descriptive docstring."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        assert "search_transactions" in tools
        tool = tools["search_transactions"]
        assert tool.description is not None
        assert "search" in tool.description.lower()
        # Check for usage examples in description
        assert "create" in tool.description.lower() or "order" in tool.description.lower()

    def test_search_transactions_mcp_tool_returns_valid_response(self) -> None:
        """Test that search_transactions MCP tool returns CatalogSearchResponse."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        search_tool = tools["search_transactions"]

        # Call the tool with a query
        result = asyncio.run(search_tool.fn(query="VA01"))

        # Verify response structure (CatalogSearchResponse)
        assert result.success is True
        assert result.query == "VA01"
        assert isinstance(result.total_results, int)
        assert isinstance(result.results, list)

        # Verify result structure for exact match
        if result.total_results > 0:
            first_result = result.results[0]
            assert first_result.tcode == "VA01"  # Exact match should be first
            assert first_result.score == 100.0  # Exact match score
            assert first_result.match_type == "exact_tcode"
            assert isinstance(first_result.description, str)
            assert isinstance(first_result.area, str | None)

    def test_search_transactions_mcp_tool_with_area_filter(self) -> None:
        """Test that search_transactions MCP tool respects area filter."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        search_tool = tools["search_transactions"]

        # Search with area filter
        result = asyncio.run(search_tool.fn(query="order", area="SD"))

        assert result.success is True
        assert result.query == "order"

        # All results should be in SD area (if any)
        if result.total_results > 0:
            for r in result.results:
                assert r.area is None or r.area.startswith("SD"), f"Expected SD area, got {r.area}"

    def test_search_transactions_mcp_tool_empty_query(self) -> None:
        """Test that search_transactions handles empty query gracefully."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        search_tool = tools["search_transactions"]

        # Empty query should return empty results, not crash
        result = asyncio.run(search_tool.fn(query=""))

        assert result.success is True
        assert result.total_results == 0
        assert result.results == []

    def test_search_transactions_mcp_tool_no_matches(self) -> None:
        """Test that search_transactions returns hint when no matches."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        search_tool = tools["search_transactions"]

        # Query that won't match anything
        result = asyncio.run(search_tool.fn(query="ZZZNONEXISTENT999"))

        assert result.success is True
        assert result.total_results == 0
        assert result.results == []
        # Should have a hint when no results
        assert result.hint is not None
        assert "no transactions found" in result.hint.lower()

    def test_search_transactions_mcp_tool_german_keyword(self) -> None:
        """Test that search_transactions finds German descriptions (catalog is in German)."""
        tools = {tool.name: tool for tool in mcp._tool_manager._tools.values()}
        search_tool = tools["search_transactions"]

        # Search for "anlage" (German for "create" - common in SAP descriptions)
        result = asyncio.run(search_tool.fn(query="anlage"))

        assert result.success is True
        assert result.query == "anlage"

        # Should find transactions with "anlage" in description
        assert result.total_results > 0, "Expected to find transactions with 'anlage' in German catalog"
        # Verify at least one result has "anlage" in description
        has_anlage = any("anlage" in r.description.lower() for r in result.results)
        assert has_anlage, "Expected 'anlage' in at least one description"
