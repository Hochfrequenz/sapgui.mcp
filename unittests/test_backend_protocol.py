"""Tests for CheckActivateResult and backend structure."""

from sapguimcp.models.base import CheckActivateResult


def test_check_activate_result_is_tool_result() -> None:
    """CheckActivateResult must be a ToolResult subclass."""
    from sapguimcp.models import ToolResult

    assert issubclass(CheckActivateResult, ToolResult)


def test_check_activate_result_defaults() -> None:
    """CheckActivateResult should have sensible defaults."""
    result = CheckActivateResult(success=True)
    assert result.success is True
    assert result.messages == []
    assert result.activated is False


def test_check_activate_result_with_values() -> None:
    """CheckActivateResult should accept all fields."""
    result = CheckActivateResult(
        success=True,
        messages=["Syntax check OK", "Activation successful"],
        activated=True,
    )
    assert result.activated is True
    assert len(result.messages) == 2
