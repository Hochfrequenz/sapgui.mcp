"""Tests for the SE38 edit tool: result model and registration (unit tests, no SAP)."""

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from sapguimcp.models.se38_edit_models import SE38EditResult
from sapguimcp.tools.se38_edit_tools import register_se38_edit_tools


def test_se38_edit_result_success() -> None:
    """Test successful SE38EditResult creation."""
    result = SE38EditResult(
        success=True,
        program_name="ZTEST_MCP_EDIT",
        backup_source="REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'.",
        check_messages=["No syntax errors found"],
        activated=True,
    )
    assert result.success is True
    assert result.program_name == "ZTEST_MCP_EDIT"
    assert result.backup_source == "REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'."
    assert result.activated is True
    assert result.error is None


def test_se38_edit_result_failure() -> None:
    """Test failed SE38EditResult creation via factory."""
    result = SE38EditResult.failure(
        error="Syntax error in line 3",
        program_name="ZTEST_MCP_EDIT",
        backup_source="REPORT ZTEST_MCP_EDIT.\nWRITE 'OLD'.",
        check_messages=["Syntax error: unexpected token"],
        activated=False,
    )
    assert result.success is False
    assert result.error == "Syntax error in line 3"
    assert result.activated is False


def test_se38_edit_result_validation_error() -> None:
    """Test that success=True with error raises ValidationError."""
    with pytest.raises(ValidationError):
        SE38EditResult(
            success=True,
            error="This should not be set",
            program_name="ZTEST",
            backup_source="",
            check_messages=[],
            activated=False,
        )


@pytest.mark.anyio
async def test_se38_edit_tool_is_registered() -> None:
    """Test that register_se38_edit_tools adds the tool to a FastMCP instance."""
    mcp = FastMCP("test")
    register_se38_edit_tools(mcp)

    tool = await mcp.get_tool("sap_se38_edit")
    assert tool is not None, "sap_se38_edit tool not found after registration"
