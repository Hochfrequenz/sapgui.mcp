"""Browser tool result models."""

from datetime import timedelta
from typing import Literal

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SnapshotResult(ToolResult):
    """Result from browser_snapshot tool."""

    snapshot: str | None = Field(default=None, description="ARIA snapshot in YAML format")
    selector: str | None = Field(default=None, description="Scoped selector if provided")


class ScreenshotResult(ToolResult):
    """Result from browser_screenshot tool."""

    image_base64: str | None = Field(default=None, description="Base64 encoded PNG")
    full_page: bool = Field(default=False, description="Was full page captured")
    selector: str | None = Field(default=None, description="Element selector if scoped")


class ClickResult(ToolResult):
    """Result from browser_click tool."""

    selector: str = Field(description="Selector that was clicked")


class FillResult(ToolResult):
    """Result from browser_fill tool."""

    selector: str = Field(description="Selector that was filled")
    value: str = Field(description="Value that was entered")


class BrowserKeyboardResult(ToolResult):
    """Result from browser_keyboard tool."""

    key: str | None = Field(default=None, description="Key pressed")
    text: str | None = Field(default=None, description="Text typed")


class NavigateResult(ToolResult):
    """Result from browser_navigate tool."""

    url: str = Field(description="URL navigated to")
    title: str | None = Field(default=None, description="Page title after navigation")


class EvaluateResult(ToolResult):
    """Result from browser_evaluate tool."""

    result: str | None = Field(default=None, description="JSON-serialized result")
    script_snippet: str | None = Field(default=None, description="First 100 chars of script")


class WaitResult(ToolResult):
    """Result from browser_wait tool."""

    selector: str | None = Field(default=None, description="Selector waited for")
    state: Literal["attached", "detached", "hidden", "visible"] | None = Field(
        default=None, description="Element state waited for: 'visible', 'hidden', 'attached', or 'detached'"
    )
    timeout: timedelta = Field(description="Timeout duration (ISO 8601 format in JSON, e.g., 'PT30S')")


class HtmlResult(ToolResult):
    """Result from browser_get_html tool."""

    html: str | None = Field(default=None, description="HTML content")
    selector: str | None = Field(default=None, description="Scoped selector if provided")
    outer: bool = Field(default=True, description="outerHTML vs innerHTML")


class SelectOptionResult(ToolResult):
    """Result from browser_select_option tool."""

    selector: str = Field(description="Select element selector")
    selected_value: str | None = Field(default=None, description="Value selected")
    selected_label: str | None = Field(default=None, description="Label selected")
