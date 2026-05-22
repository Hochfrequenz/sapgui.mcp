# Pydantic Tool Results Design

## Overview

Replace string return types on all MCP tools with strictly typed Pydantic models. Enable `strict_input_validation=True` on FastMCP server startup.

## Problem

Currently, all tools in `sap_tools.py` and `browser_tools.py` return plain strings. This makes it difficult to:

- Parse structured data from tool results
- Enforce consistent error handling patterns
- Validate inputs before execution
- Provide type safety for LLM tool calls

## Solution

Create Pydantic models for all tool return types with:

- Base `ToolResult` class with standardized error handling
- Validators enforcing invariants (success/error consistency, transaction code format)
- `extra="allow"` for flexibility
- ISO 8601 timedelta serialization

## Package Structure

```
src/sapguimcp/models/
├── __init__.py          # Add new exports
├── base.py              # NEW: ToolResult base class
├── browser_manager.py   # Existing
├── browser_results.py   # NEW: Browser tool result models
├── sap_results.py       # NEW: SAP tool result models
└── keepalive.py         # Existing
```

## Base Model (`base.py`)

```python
import re
from datetime import timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TCODE_PATTERN = re.compile(r"^[A-Z0-9_/]+$")


class ToolResult(BaseModel):
    """Base class for all MCP tool results with standardized error handling.

    Per MCP spec, tool errors should be reported within the result object,
    not as protocol-level errors. This allows the LLM to observe and handle errors.

    Invariants enforced by validation:
    - success=True → error must be None
    - success=False → error must be non-empty string
    """

    model_config = ConfigDict(
        extra="allow",
        ser_json_timedelta="iso8601",
    )

    success: bool = Field(default=True, description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if success=False")

    @model_validator(mode="after")
    def validate_success_error_consistency(self) -> Self:
        """Enforce that success and error are consistent."""
        if self.success and self.error is not None:
            raise ValueError("success=True requires error=None")
        if not self.success and not self.error:
            raise ValueError("success=False requires non-empty error message")
        return self

    @property
    def is_error(self) -> bool:
        """Convenience property matching MCP's isError convention."""
        return not self.success

    @classmethod
    def failure(cls, error: str, **kwargs):
        """Factory method to create a failed result."""
        return cls(success=False, error=error, **kwargs)
```

## SAP Result Models (`sap_results.py`)

```python
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from sapguimcp.models.base import TCODE_PATTERN, ToolResult


class LoginResult(ToolResult):
    """Result from sap_login tool."""

    url: str | None = Field(default=None, description="SAP URL that was accessed")
    user: str | None = Field(default=None, description="Logged in username")
    already_logged_in: bool = Field(default=False, description="Was already logged in")


class TransactionResult(ToolResult):
    """Result from sap_transaction tool."""

    tcode: str = Field(description="Transaction code executed")
    page_title: str | None = Field(default=None, description="Current page title")
    new_window: bool = Field(default=False, description="Opened in new session")
    session_count: int | None = Field(default=None, ge=1, description="Number of SAP sessions")

    @field_validator("tcode")
    @classmethod
    def validate_tcode(cls, v: str) -> str:
        """Transaction codes must be uppercase with only A-Z, 0-9, _, /."""
        v = v.upper()
        if not TCODE_PATTERN.match(v):
            raise ValueError(f"Invalid transaction code format: {v}")
        return v


class SessionStatus(ToolResult):
    """Result from sap_session_status tool."""

    status: Literal["active", "timed_out", "logged_off", "no_page", "unknown"]
    message: str = Field(description="Human-readable status description")


class KeyboardResult(ToolResult):
    """Result from sap_press_key tool."""

    key: str = Field(description="Key that was sent")
    page_title: str | None = Field(default=None, description="Current page title after")


class KeepaliveResult(ToolResult):
    """Result from sap_keepalive_start/stop tools."""

    running: bool = Field(description="Whether keepalive is now running")
    interval_seconds: int | None = Field(default=None, ge=1, description="Ping interval if running")


class StatusBarInfo(ToolResult):
    """Result from sap_read_status_bar tool."""

    type: Literal["S", "E", "W", "I", "none"] = Field(description="Message type")
    message: str = Field(default="", description="Status bar text")


class ScreenInfo(ToolResult):
    """Result from sap_get_screen_info tool."""

    transaction: str | None = Field(default=None, description="Current transaction code")
    title: str = Field(description="Window/page title")
    url: str = Field(description="Current URL")
    program: str | None = Field(default=None, description="ABAP program name")
    dynpro: str | None = Field(default=None, description="Screen number")


class ScreenText(ToolResult):
    """Result from sap_get_screen_text tool."""

    title: str = Field(description="Screen title")
    status_bar: str | None = Field(default=None)
    tabs: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    table_headers: list[str] = Field(default_factory=list)
    main_content: list[str] = Field(default_factory=list)


class TableData(ToolResult):
    """Result from sap_read_table tool."""

    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[dict[str, str]] = Field(default_factory=list, description="Row data")
    total_rows: int = Field(default=0, ge=0, description="Total rows found")
    start_row: int = Field(default=1, ge=1, description="First row returned (1-indexed)")
    end_row: int | None = Field(default=None, ge=1, description="Last row returned")


class FieldInfo(BaseModel):
    """Single field discovered on screen."""

    id: str | None = None
    name: str | None = None
    label: str | None = None
    type: str | None = None
    selector: str = Field(description="CSS selector to use")
    value: str | None = None


class DiscoveredFields(ToolResult):
    """Result from sap_discover_fields tool."""

    field_count: int = Field(ge=0, description="Number of fields found")
    fields: list[FieldInfo] = Field(default_factory=list)


class FieldLookupResult(ToolResult):
    """Result from sap_lookup_fields tool."""

    transaction: str = Field(description="Transaction code looked up")
    fields: dict[str, str] = Field(default_factory=dict, description="Field name → selector")
    similar_transactions: list[str] | None = Field(default=None, description="Similar tcodes if not found")

    @field_validator("transaction")
    @classmethod
    def validate_transaction(cls, v: str) -> str:
        v = v.upper()
        if not TCODE_PATTERN.match(v):
            raise ValueError(f"Invalid transaction code format: {v}")
        return v
```

## Browser Result Models (`browser_results.py`)

```python
from datetime import timedelta
from typing import Literal

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SnapshotResult(ToolResult):
    """Result from browser_snapshot tool."""

    snapshot: dict | None = Field(default=None, description="Accessibility tree as dict")
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
    state: Literal["attached", "detached", "hidden", "visible"] | None = Field(default=None)
    timeout: timedelta = Field(description="Timeout duration")


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
```

## Updated `models/__init__.py`

```python
from sapguimcp.models.base import TCODE_PATTERN, ToolResult
from sapguimcp.models.browser_manager import BrowserManager, get_browser_manager
from sapguimcp.models.browser_results import (
    BrowserKeyboardResult,
    ClickResult,
    EvaluateResult,
    FillResult,
    HtmlResult,
    NavigateResult,
    ScreenshotResult,
    SelectOptionResult,
    SnapshotResult,
    WaitResult,
)
from sapguimcp.models.keepalive import KeepaliveManager
from sapguimcp.models.sap_results import (
    DiscoveredFields,
    FieldInfo,
    FieldLookupResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    StatusBarInfo,
    TableData,
    TransactionResult,
)

__all__ = [
    # Base
    "TCODE_PATTERN",
    "ToolResult",
    # Existing
    "BrowserManager",
    "get_browser_manager",
    "KeepaliveManager",
    # SAP results
    "DiscoveredFields",
    "FieldInfo",
    "FieldLookupResult",
    "KeepaliveResult",
    "KeyboardResult",
    "LoginResult",
    "ScreenInfo",
    "ScreenText",
    "SessionStatus",
    "StatusBarInfo",
    "TableData",
    "TransactionResult",
    # Browser results
    "BrowserKeyboardResult",
    "ClickResult",
    "EvaluateResult",
    "FillResult",
    "HtmlResult",
    "NavigateResult",
    "ScreenshotResult",
    "SelectOptionResult",
    "SnapshotResult",
    "WaitResult",
]
```

## Server Startup Update

In `server.py`:

```python
# Before:
mcp = FastMCP("sapgui")

# After:
mcp = FastMCP("sapgui", strict_input_validation=True)
```

## Screenshot Special Case

`browser_screenshot` should return `ImageContent` directly for proper MCP image handling:

```python
from mcp.types import ImageContent

async def browser_screenshot(...) -> ImageContent:
    # ...
    return ImageContent(
        type="image",
        data=base64_png,
        mimeType="image/png"
    )
```

## Tool Return Type Updates

Each tool changes from `-> str` to its specific result model:

| Tool                    | Return Type             |
| ----------------------- | ----------------------- |
| `sap_login`             | `LoginResult`           |
| `sap_transaction`       | `TransactionResult`     |
| `sap_session_status`    | `SessionStatus`         |
| `sap_press_key`          | `KeyboardResult`        |
| `sap_keepalive_start`   | `KeepaliveResult`       |
| `sap_keepalive_stop`    | `KeepaliveResult`       |
| `sap_read_status_bar`   | `StatusBarInfo`         |
| `sap_get_screen_info`   | `ScreenInfo`            |
| `sap_get_screen_text`   | `ScreenText`            |
| `sap_read_table`        | `TableData`             |
| `sap_discover_fields`   | `DiscoveredFields`      |
| `sap_lookup_fields`     | `FieldLookupResult`     |
| `browser_snapshot`      | `SnapshotResult`        |
| `browser_screenshot`    | `ImageContent`          |
| `browser_click`         | `ClickResult`           |
| `browser_fill`          | `FillResult`            |
| `browser_keyboard`      | `BrowserKeyboardResult` |
| `browser_navigate`      | `NavigateResult`        |
| `browser_evaluate`      | `EvaluateResult`        |
| `browser_wait`          | `WaitResult`            |
| `browser_get_html`      | `HtmlResult`            |
| `browser_select_option` | `SelectOptionResult`    |

## Implementation Order

1. Create `models/base.py` with `ToolResult`
2. Create `models/sap_results.py` with SAP models
3. Create `models/browser_results.py` with browser models
4. Update `models/__init__.py` exports
5. Update `sap_tools.py` return types and implementations
6. Update `browser_tools.py` return types and implementations
7. Update `server.py` with `strict_input_validation=True`
8. Run tests to verify

## Testing

Existing integration tests validate tool behavior. Add unit tests for:

- `ToolResult` validation (success/error consistency)
- Transaction code validation
- Integer field constraints (ge=0, ge=1)
- Timedelta serialization format
