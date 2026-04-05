"""Tests for general-purpose tools: sap_click_button, sap_select_tab, sap_select_dropdown, sap_screenshot."""

import asyncio

import pytest
from pydantic import ValidationError

from sapwebguimcp.models import ClickButtonResult, SelectDropdownResult, SelectTabResult
from sapwebguimcp.server import mcp


class TestNewToolsRegistered:
    """Verify that the four new general-purpose tools are registered with FastMCP."""

    _tools: dict[str, object] = {}

    @classmethod
    def _get_tools(cls) -> dict[str, object]:
        if not cls._tools:
            cls._tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
        return cls._tools

    def test_sap_click_button_registered(self) -> None:
        """sap_click_button must be a registered MCP tool."""
        assert "sap_click_button" in self._get_tools()

    def test_sap_select_tab_registered(self) -> None:
        """sap_select_tab must be a registered MCP tool."""
        assert "sap_select_tab" in self._get_tools()

    def test_sap_select_dropdown_registered(self) -> None:
        """sap_select_dropdown must be a registered MCP tool."""
        assert "sap_select_dropdown" in self._get_tools()

    def test_sap_screenshot_registered(self) -> None:
        """sap_screenshot must be a registered MCP tool."""
        assert "sap_screenshot" in self._get_tools()

    def test_sap_click_button_has_description(self) -> None:
        """sap_click_button must have a substantive description."""
        tool = self._get_tools()["sap_click_button"]
        assert tool.description  # type: ignore[union-attr]
        assert len(tool.description) > 50  # type: ignore[union-attr]
        assert "label" in tool.description.lower()  # type: ignore[union-attr]

    def test_sap_select_tab_has_description(self) -> None:
        """sap_select_tab must have a substantive description."""
        tool = self._get_tools()["sap_select_tab"]
        assert tool.description  # type: ignore[union-attr]
        assert len(tool.description) > 50  # type: ignore[union-attr]
        assert "tab" in tool.description.lower()  # type: ignore[union-attr]

    def test_sap_select_dropdown_has_description(self) -> None:
        """sap_select_dropdown must have a substantive description."""
        tool = self._get_tools()["sap_select_dropdown"]
        assert tool.description  # type: ignore[union-attr]
        assert len(tool.description) > 50  # type: ignore[union-attr]
        assert "dropdown" in tool.description.lower()  # type: ignore[union-attr]

    def test_sap_screenshot_has_description(self) -> None:
        """sap_screenshot must have a substantive description."""
        tool = self._get_tools()["sap_screenshot"]
        assert tool.description  # type: ignore[union-attr]
        assert len(tool.description) > 50  # type: ignore[union-attr]
        assert "screenshot" in tool.description.lower()  # type: ignore[union-attr]

    def test_new_tools_in_capabilities(self) -> None:
        """All new tools must be discoverable via sap_get_capabilities."""
        tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
        expected = {"sap_click_button", "sap_select_tab", "sap_select_dropdown", "sap_screenshot"}
        assert expected.issubset(tool_names), f"Missing: {expected - tool_names}"


class TestClickButtonResult:
    """Tests for ClickButtonResult model."""

    def test_success(self) -> None:
        """Successful button click."""
        result = ClickButtonResult(label="Execute")
        assert result.success is True
        assert result.label == "Execute"
        assert result.error is None

    def test_failure(self) -> None:
        """Failed button click via factory method."""
        result = ClickButtonResult.failure("Button 'Foo' not found", label="Foo")
        assert result.success is False
        assert result.error == "Button 'Foo' not found"
        assert result.label == "Foo"

    def test_success_with_error_fails(self) -> None:
        """success=True with error must raise ValidationError."""
        with pytest.raises(ValidationError):
            ClickButtonResult(success=True, error="oops", label="X")


class TestSelectTabResult:
    """Tests for SelectTabResult model."""

    def test_success(self) -> None:
        """Successful tab selection."""
        result = SelectTabResult(label="Address")
        assert result.success is True
        assert result.label == "Address"

    def test_failure(self) -> None:
        """Failed tab selection."""
        result = SelectTabResult.failure("Tab 'Details' not found", label="Details")
        assert result.success is False
        assert result.error == "Tab 'Details' not found"
        assert result.label == "Details"


class TestSelectDropdownResult:
    """Tests for SelectDropdownResult model."""

    def test_success(self) -> None:
        """Successful dropdown selection."""
        result = SelectDropdownResult(label="Country", value="DE")
        assert result.success is True
        assert result.label == "Country"
        assert result.value == "DE"
        assert result.available_options is None

    def test_failure_with_options(self) -> None:
        """Failed dropdown selection returns available options."""
        result = SelectDropdownResult.failure(
            "Value 'XX' not found",
            label="Country",
            value="XX",
            available_options=["DE", "US", "FR"],
        )
        assert result.success is False
        assert result.available_options == ["DE", "US", "FR"]

    def test_failure_no_options(self) -> None:
        """Failed dropdown selection without options."""
        result = SelectDropdownResult.failure(
            "Field 'Foo' not found",
            label="Foo",
            value="bar",
        )
        assert result.success is False
        assert result.available_options is None
