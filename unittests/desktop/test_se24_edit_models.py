"""Tests for the SE24 edit tool: result model and registration (unit tests, no SAP)."""

import pytest
from fastmcp import FastMCP
from pydantic import ValidationError

from sapguimcp.models.se24_edit_models import SE24EditResult
from sapguimcp.tools.se24_edit_tools import register_se24_edit_tools


def test_se24_edit_result_success() -> None:
    """Test successful SE24EditResult creation."""
    result = SE24EditResult(
        success=True,
        class_name="ZCL_TEST_MCP_EDIT",
        method_name="DO_SOMETHING",
        backup_source="  METHOD do_something.\n  ENDMETHOD.",
        check_messages=["No syntax errors found"],
        activated=True,
    )
    assert result.success is True
    assert result.class_name == "ZCL_TEST_MCP_EDIT"
    assert result.method_name == "DO_SOMETHING"
    assert result.backup_source == "  METHOD do_something.\n  ENDMETHOD."
    assert result.activated is True
    assert result.error is None


def test_se24_edit_result_failure() -> None:
    """Test failed SE24EditResult creation via factory."""
    result = SE24EditResult.failure(
        error="Syntax error in line 3",
        class_name="ZCL_TEST_MCP_EDIT",
        method_name="DO_SOMETHING",
        backup_source="  METHOD do_something.\n  ENDMETHOD.",
        check_messages=["Syntax error: unexpected token"],
        activated=False,
    )
    assert result.success is False
    assert result.error == "Syntax error in line 3"
    assert result.activated is False


def test_se24_edit_result_validation_error() -> None:
    """Test that success=True with error raises ValidationError."""
    with pytest.raises(ValidationError):
        SE24EditResult(
            success=True,
            error="This should not be set",
            class_name="ZCL_TEST",
            method_name="DO_SOMETHING",
            backup_source="",
            check_messages=[],
            activated=False,
        )


@pytest.mark.anyio
async def test_se24_edit_tool_is_registered() -> None:
    """Test that register_se24_edit_tools adds the tool to a FastMCP instance."""
    mcp = FastMCP("test")
    register_se24_edit_tools(mcp)

    tool = await mcp.get_tool("sap_se24_edit")
    assert tool is not None, "sap_se24_edit tool not found after registration"
