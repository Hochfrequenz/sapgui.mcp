"""Tests for the SapUiBackend protocol hierarchy."""

from sapwebguimcp.backend.protocol import (
    CheckActivateResult,
    SapEditor,
    SapNavigation,
    SapPopup,
    SapUiBackend,
    SapUiInspection,
    SapUiPrimitives,
)


def test_all_sub_protocols_are_runtime_checkable() -> None:
    """All five sub-protocols must be @runtime_checkable."""
    for proto in (
        SapUiPrimitives,
        SapUiInspection,
        SapNavigation,
        SapEditor,
        SapPopup,
        SapUiBackend,
    ):
        assert hasattr(proto, "__protocol_attrs__") or hasattr(
            proto, "__abstractmethods__"
        ), f"{proto.__name__} is not a Protocol"


def test_check_activate_result_is_tool_result() -> None:
    """CheckActivateResult must be a ToolResult subclass."""
    from sapwebguimcp.models import ToolResult

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


def test_webgui_backend_implements_protocol() -> None:
    """WebGuiBackend must satisfy the SapUiBackend protocol."""
    from sapwebguimcp.backend.webgui.backend import WebGuiBackend

    assert issubclass(WebGuiBackend, SapUiBackend)
