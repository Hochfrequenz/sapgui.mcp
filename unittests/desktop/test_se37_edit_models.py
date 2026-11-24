"""Tests for the SE37 edit tool: result model and registration (unit tests, no SAP)."""

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from sapguimcp.models.se37_edit_models import SE37EditResult
from sapguimcp.tools.se37_edit_tools import register_se37_edit_tools


def test_se37_edit_result_success() -> None:
    """Test successful SE37EditResult creation."""
    result = SE37EditResult(
        success=True,
        function_module="Z_TEST_MCP_EDIT",
        backup_source="FUNCTION Z_TEST_MCP_EDIT.\nENDFUNCTION.",
        check_messages=["No syntax errors found"],
        activated=True,
    )
    assert result.success is True
    assert result.function_module == "Z_TEST_MCP_EDIT"
    assert result.backup_source == "FUNCTION Z_TEST_MCP_EDIT.\nENDFUNCTION."
    assert result.activated is True
    assert result.error is None


def test_se37_edit_result_failure() -> None:
    """Test failed SE37EditResult creation via factory."""
    result = SE37EditResult.failure(
        error="Syntax error in line 3",
        function_module="Z_TEST_MCP_EDIT",
        backup_source="FUNCTION Z_TEST_MCP_EDIT.\nENDFUNCTION.",
        check_messages=["Syntax error: unexpected token"],
        activated=False,
    )
    assert result.success is False
    assert result.error == "Syntax error in line 3"
    assert result.activated is False


def test_se37_edit_result_validation_error() -> None:
    """Test that success=True with error raises ValidationError."""
    with pytest.raises(ValidationError):
        SE37EditResult(
            success=True,
            error="This should not be set",
            function_module="Z_TEST",
            backup_source="",
            check_messages=[],
            activated=False,
        )


@pytest.mark.anyio
async def test_se37_edit_tool_is_registered() -> None:
    """Test that register_se37_edit_tools adds the tool to a FastMCP instance."""
    mcp = FastMCP("test")
    register_se37_edit_tools(mcp)

    tool = await mcp.get_tool("sap_se37_edit")
    assert tool is not None, "sap_se37_edit tool not found after registration"
