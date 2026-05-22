"""Unit tests for general-purpose MCP tools: sap_click_button, sap_select_tab, sap_select_dropdown, sap_screenshot.

Tests tool registration, result models, and tool behaviour with mocked backends.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from sapguimcp.models import ClickButtonResult, SelectDropdownResult, SelectTabResult
from sapguimcp.models.base import PopupInfo
from sapguimcp.models.sap_results import DropdownFillResult
from sapguimcp.server import mcp

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PATCH_GET_BACKEND = "sapguimcp.tools.sap_tools.get_backend"


def _make_backend(backend_type: str = "webgui", **overrides) -> AsyncMock:
    """Create a mock backend with sensible defaults for general-purpose tools."""
    backend = AsyncMock()
    backend.backend_type = backend_type
    backend.check_popup = AsyncMock(return_value=overrides.get("popup", None))
    backend.click_button = AsyncMock(return_value=None)
    backend.click_tab = AsyncMock(return_value=None)
    backend.select_dropdown = AsyncMock(return_value=overrides.get("dropdown_result", DropdownFillResult(success=True)))
    backend.take_screenshot = AsyncMock(return_value=overrides.get("screenshot_bytes", b"\x89PNG_FAKE"))
    backend.wait_for_ready = AsyncMock(return_value=None)
    return backend


def _parse_result(raw) -> dict:
    """Extract first text content from MCP CallToolResult and parse as JSON."""
    text = raw.content[0].text
    return json.loads(text)


# ============================================================================
# 1. Tool Registration
# ============================================================================


class TestToolRegistration:
    """All four new tools must be registered with FastMCP."""

    _tools: dict[str, object] = {}

    @classmethod
    def _get_tools(cls) -> dict[str, object]:
        if not cls._tools:
            cls._tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
        return cls._tools

    @pytest.mark.parametrize(
        "tool_name",
        ["sap_click_button", "sap_select_tab", "sap_select_dropdown", "sap_screenshot"],
    )
    def test_tool_registered(self, tool_name: str) -> None:
        assert tool_name in self._get_tools()

    @pytest.mark.parametrize(
        ("tool_name", "keyword"),
        [
            ("sap_click_button", "button"),
            ("sap_select_tab", "tab"),
            ("sap_select_dropdown", "dropdown"),
            ("sap_screenshot", "screenshot"),
        ],
    )
    def test_tool_description_contains_keyword(self, tool_name: str, keyword: str) -> None:
        tool = self._get_tools()[tool_name]
        assert tool.description and len(tool.description) > 50  # type: ignore[union-attr]
        assert keyword in tool.description.lower()  # type: ignore[union-attr]


# ============================================================================
# 2. Result Model Validation
# ============================================================================


class TestClickButtonResult:
    def test_success(self) -> None:
        result = ClickButtonResult(label="Execute")
        assert result.success is True
        assert result.label == "Execute"
        assert result.error is None

    def test_failure(self) -> None:
        result = ClickButtonResult.failure("not found", label="Foo")
        assert result.success is False
        assert result.error == "not found"

    def test_success_with_error_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClickButtonResult(success=True, error="oops", label="X")

    def test_failure_without_error_raises(self) -> None:
        with pytest.raises(ValidationError):
            ClickButtonResult(success=False, error=None, label="X")


class TestSelectTabResult:
    def test_success(self) -> None:
        result = SelectTabResult(label="Address")
        assert result.success is True
        assert result.label == "Address"

    def test_failure(self) -> None:
        result = SelectTabResult.failure("not found", label="Details")
        assert result.success is False


class TestSelectDropdownResult:
    def test_success(self) -> None:
        result = SelectDropdownResult(label="Country", value="DE")
        assert result.success is True
        assert result.available_options is None

    def test_failure_with_options(self) -> None:
        result = SelectDropdownResult.failure("not found", label="Country", value="XX", available_options=["DE", "US"])
        assert result.success is False
        assert result.available_options == ["DE", "US"]

    def test_failure_without_options(self) -> None:
        result = SelectDropdownResult.failure("not found", label="Foo", value="bar")
        assert result.success is False
        assert result.available_options is None


# ============================================================================
# 3. Tool Behaviour — sap_click_button
# ============================================================================


class TestSapClickButton:
    """Test sap_click_button tool via FastMCP Client with mocked backend."""

    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        backend = _make_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_click_button", {"label": "Execute"})
        data = _parse_result(raw)
        assert data["success"] is True
        assert data["label"] == "Execute"
        backend.click_button.assert_awaited_once_with("Execute")
        backend.wait_for_ready.assert_awaited_once()

    @pytest.mark.anyio
    async def test_empty_label_returns_failure(self) -> None:
        async with Client(mcp) as client:
            raw = await client.call_tool("sap_click_button", {"label": ""})
        data = _parse_result(raw)
        assert data["success"] is False
        assert "empty" in data["error"].lower()

    @pytest.mark.anyio
    async def test_backend_not_found(self) -> None:
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=ValueError("No backend"))):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_click_button", {"label": "OK"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert "No backend" in data["error"]

    @pytest.mark.anyio
    async def test_popup_blocking(self) -> None:
        popup = PopupInfo(message="Save changes?")
        backend = _make_backend(popup=popup)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_click_button", {"label": "OK"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert "popup" in data["error"].lower() or "Popup" in data["error"]
        backend.click_button.assert_not_awaited()

    @pytest.mark.anyio
    async def test_desktop_backend_skips_popup_check(self) -> None:
        """Desktop backend should not call check_popup (it manages windows differently)."""
        backend = _make_backend(backend_type="desktop")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_click_button", {"label": "Save"})
        data = _parse_result(raw)
        assert data["success"] is True
        backend.check_popup.assert_not_awaited()

    @pytest.mark.anyio
    async def test_button_not_found_value_error(self) -> None:
        backend = _make_backend()
        backend.click_button = AsyncMock(side_effect=ValueError("Button 'Foo' not found"))
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_click_button", {"label": "Foo"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert "not found" in data["error"]

    @pytest.mark.anyio
    async def test_generic_exception(self) -> None:
        backend = _make_backend()
        backend.click_button = AsyncMock(side_effect=RuntimeError("crash"))
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_click_button", {"label": "OK"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert "crash" in data["error"]


# ============================================================================
# 4. Tool Behaviour — sap_select_tab
# ============================================================================


class TestSapSelectTab:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        backend = _make_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_tab", {"label": "Address"})
        data = _parse_result(raw)
        assert data["success"] is True
        assert data["label"] == "Address"
        backend.click_tab.assert_awaited_once_with("Address")

    @pytest.mark.anyio
    async def test_empty_label_returns_failure(self) -> None:
        async with Client(mcp) as client:
            raw = await client.call_tool("sap_select_tab", {"label": ""})
        data = _parse_result(raw)
        assert data["success"] is False

    @pytest.mark.anyio
    async def test_backend_not_found(self) -> None:
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=ValueError("No backend"))):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_tab", {"label": "X"})
        data = _parse_result(raw)
        assert data["success"] is False

    @pytest.mark.anyio
    async def test_popup_blocking(self) -> None:
        popup = PopupInfo(message="Unsaved changes")
        backend = _make_backend(popup=popup)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_tab", {"label": "Details"})
        data = _parse_result(raw)
        assert data["success"] is False
        backend.click_tab.assert_not_awaited()

    @pytest.mark.anyio
    async def test_desktop_backend_skips_popup_check(self) -> None:
        backend = _make_backend(backend_type="desktop")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_tab", {"label": "Details"})
        data = _parse_result(raw)
        assert data["success"] is True
        backend.check_popup.assert_not_awaited()

    @pytest.mark.anyio
    async def test_tab_not_found(self) -> None:
        backend = _make_backend()
        backend.click_tab = AsyncMock(side_effect=ValueError("Tab 'X' not found"))
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_tab", {"label": "X"})
        data = _parse_result(raw)
        assert data["success"] is False

    @pytest.mark.anyio
    async def test_generic_exception(self) -> None:
        backend = _make_backend()
        backend.click_tab = AsyncMock(side_effect=RuntimeError("crash"))
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_tab", {"label": "Y"})
        data = _parse_result(raw)
        assert data["success"] is False


# ============================================================================
# 5. Tool Behaviour — sap_select_dropdown
# ============================================================================


class TestSapSelectDropdown:
    @pytest.mark.anyio
    async def test_happy_path(self) -> None:
        backend = _make_backend()
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "Country", "value": "DE"})
        data = _parse_result(raw)
        assert data["success"] is True
        assert data["label"] == "Country"
        assert data["value"] == "DE"
        backend.select_dropdown.assert_awaited_once_with("Country", "DE")

    @pytest.mark.anyio
    async def test_empty_label_returns_failure(self) -> None:
        async with Client(mcp) as client:
            raw = await client.call_tool("sap_select_dropdown", {"label": "", "value": "DE"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert "empty" in data["error"].lower()

    @pytest.mark.anyio
    async def test_backend_not_found(self) -> None:
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=ValueError("No backend"))):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "X", "value": "Y"})
        data = _parse_result(raw)
        assert data["success"] is False

    @pytest.mark.anyio
    async def test_popup_blocking(self) -> None:
        popup = PopupInfo(message="Confirm?")
        backend = _make_backend(popup=popup)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "X", "value": "Y"})
        data = _parse_result(raw)
        assert data["success"] is False
        backend.select_dropdown.assert_not_awaited()

    @pytest.mark.anyio
    async def test_desktop_backend_skips_popup_check(self) -> None:
        backend = _make_backend(backend_type="desktop")
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "Country", "value": "DE"})
        data = _parse_result(raw)
        assert data["success"] is True
        backend.check_popup.assert_not_awaited()

    @pytest.mark.anyio
    async def test_dropdown_value_not_found_returns_available_options(self) -> None:
        backend = _make_backend(
            dropdown_result=DropdownFillResult(
                success=False,
                error_message="Value 'XX' not in list",
                available_options=["DE", "US", "FR"],
            )
        )
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "Country", "value": "XX"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert data["available_options"] == ["DE", "US", "FR"]
        assert "XX" in data["error"]

    @pytest.mark.anyio
    async def test_dropdown_field_not_found(self) -> None:
        backend = _make_backend(
            dropdown_result=DropdownFillResult(success=False, error_message="Field 'Foo' not found")
        )
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "Foo", "value": "bar"})
        data = _parse_result(raw)
        assert data["success"] is False
        assert data["available_options"] is None

    @pytest.mark.anyio
    async def test_value_error_from_backend(self) -> None:
        backend = _make_backend()
        backend.select_dropdown = AsyncMock(side_effect=ValueError("bad input"))
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "X", "value": "Y"})
        data = _parse_result(raw)
        assert data["success"] is False

    @pytest.mark.anyio
    async def test_generic_exception(self) -> None:
        backend = _make_backend()
        backend.select_dropdown = AsyncMock(side_effect=RuntimeError("crash"))
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_select_dropdown", {"label": "X", "value": "Y"})
        data = _parse_result(raw)
        assert data["success"] is False


# ============================================================================
# 6. Tool Behaviour — sap_screenshot
# ============================================================================


class TestSapScreenshot:
    @pytest.mark.anyio
    async def test_happy_path_returns_image(self) -> None:
        fake_png = b"\x89PNG\r\n\x1a\nFAKE_IMAGE_DATA"
        backend = _make_backend(screenshot_bytes=fake_png)
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            async with Client(mcp) as client:
                raw = await client.call_tool("sap_screenshot", {})
        # Screenshot returns an Image, not JSON — check we got binary-ish content
        assert raw.content, "Screenshot should return content"
        backend.take_screenshot.assert_awaited_once()

    @pytest.mark.anyio
    async def test_backend_not_found_raises(self) -> None:
        with patch(_PATCH_GET_BACKEND, new=AsyncMock(side_effect=ValueError("No backend"))):
            async with Client(mcp) as client:
                # sap_screenshot raises ValueError (not ToolResult.failure),
                # so FastMCP wraps it as a ToolError
                with pytest.raises(ToolError, match="No backend"):
                    await client.call_tool("sap_screenshot", {})
