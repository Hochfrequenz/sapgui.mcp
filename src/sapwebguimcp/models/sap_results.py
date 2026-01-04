"""SAP tool result models."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from sapwebguimcp.models.alv_models import AlvCellInfo, AlvMetadata
from sapwebguimcp.models.base import TCode, ToolResult

# Shared type for SAP status bar message types
StatusBarType = Literal["S", "E", "W", "I", "none"]
"""Status bar message type: 'S' (success), 'E' (error), 'W' (warning), 'I' (info), 'none' (empty)."""


class LoginResult(ToolResult):
    """Result from sap_login tool."""

    url: str | None = Field(default=None, description="SAP URL that was accessed")
    user: str | None = Field(default=None, description="Logged in username")
    already_logged_in: bool = Field(default=False, description="Was already logged in")


class TransactionResult(ToolResult):
    """Result from sap_transaction tool."""

    tcode: TCode = Field(description="Transaction code executed")
    page_title: str | None = Field(default=None, description="Current page title")
    new_window: bool = Field(default=False, description="Opened in new session")
    session_count: int | None = Field(default=None, ge=1, description="Number of SAP sessions")


class SessionStatus(ToolResult):
    """Result from sap_session_status tool."""

    status: Literal["active", "timed_out", "logged_off", "no_page", "unknown"] = Field(
        description="Session state: 'active' (responsive), 'timed_out', 'logged_off', 'no_page', or 'unknown'"
    )
    message: str = Field(description="Human-readable status description")


class KeyboardResult(ToolResult):
    """Result from sap_keyboard tool.

    For shortcut keys (F-keys or Ctrl+*), the status bar is automatically read
    after the keystroke since SAP often displays feedback there.
    """

    key: str = Field(description="Key that was sent")
    page_title: str | None = Field(default=None, description="Current page title after")
    status_bar_read: bool = Field(
        default=False,
        description="Whether status bar was read (only for shortcuts: F-keys, Ctrl+*)",
    )
    status_bar_type: StatusBarType | None = Field(
        default=None,
        description="Status bar type if read",
    )
    status_bar_message: str | None = Field(
        default=None,
        description="Status bar text if read. None if not read, empty string if read but empty.",
    )

    @model_validator(mode="after")
    def _validate_status_bar_consistency(self) -> "KeyboardResult":
        """Ensure status_bar_message is set iff status_bar_read is True."""
        if self.status_bar_read:
            if self.status_bar_message is None:
                raise ValueError("status_bar_message must be set when status_bar_read is True")
            if self.status_bar_type is None:
                raise ValueError("status_bar_type must be set when status_bar_read is True")
        else:
            if self.status_bar_message is not None:
                raise ValueError("status_bar_message must be None when status_bar_read is False")
            if self.status_bar_type is not None:
                raise ValueError("status_bar_type must be None when status_bar_read is False")
        return self


class KeepaliveResult(ToolResult):
    """Result from sap_keepalive_start/stop tools."""

    running: bool = Field(description="Whether keepalive is now running")
    interval_seconds: int | None = Field(default=None, ge=1, description="Ping interval if running")


class StatusBarInfo(ToolResult):
    """Result from sap_read_status_bar tool."""

    type: StatusBarType = Field(
        description="Message type: 'S' (success), 'E' (error), 'W' (warning), 'I' (info), or 'none'"
    )
    message: str = Field(default="", description="Status bar text")


class ScreenInfo(ToolResult):
    """Result from sap_get_screen_info tool."""

    transaction: str | None = Field(default=None, description="Current transaction code")
    title: str = Field(description="Window/page title")
    url: str = Field(description="Current URL")
    program: str | None = Field(default=None, description="ABAP program name")
    dynpro: str | None = Field(default=None, description="Screen number")


class ScreenText(ToolResult):
    """Result from sap_get_screen_text tool.

    Extracts all readable text from the current SAP screen, organized by element type.
    """

    title: str = Field(description="Screen title")
    status_bar: str | None = Field(default=None, description="Current status bar message")
    tabs: list[str] = Field(default_factory=list, description="Tab labels if present")
    labels: list[str] = Field(default_factory=list, description="Field labels (deduplicated)")
    buttons: list[str] = Field(default_factory=list, description="Button labels (deduplicated)")
    table_headers: list[str] = Field(default_factory=list, description="Table column headers")
    main_content: list[str] = Field(default_factory=list, description="Other visible text content")


class TableRow(BaseModel):
    """A single table row with row number and cell data.

    For ALV grids, includes cell-level click metadata with pre-escaped CSS selectors.
    """

    row: int = Field(ge=1, description="Row number (1-indexed)")
    data: dict[str, str] = Field(description="Cell values by column header")
    cells: dict[str, AlvCellInfo] | None = Field(
        default=None,
        description="Cell click metadata (ALV grids only). Keys are column headers.",
    )


class TableData(ToolResult):
    """Result from sap_read_table tool.

    For ALV grids, includes grid-level metadata with hotspot column info.
    Use the `cells` field on each row to get pre-escaped CSS selectors for clicking.
    """

    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[TableRow] = Field(default_factory=list, description="Row data")
    total_rows: int = Field(default=0, ge=0, description="Total rows found")
    start_row: int = Field(default=1, ge=1, description="First row returned (1-indexed)")
    end_row: int | None = Field(default=None, ge=1, description="Last row returned")
    alv: AlvMetadata | None = Field(
        default=None,
        description="ALV grid metadata (only present for ALV grids)",
    )


class FieldInfo(BaseModel):
    """Single field discovered on screen."""

    id: str | None = Field(default=None, description="Element ID attribute")
    name: str | None = Field(default=None, description="Element name attribute")
    field_id: str | None = Field(
        default=None, description="SAP field ID extracted from lsdata (e.g., 'NAME_FIRST', 'STREET')"
    )
    label: str | None = Field(default=None, description="Associated label text")
    type: str | None = Field(default=None, description="Input type (text, checkbox, etc.)")
    selector: str = Field(description="Best CSS selector for targeting this field")
    alternative_selectors: list[str] = Field(default_factory=list, description="Other valid CSS selectors")
    value: str | None = Field(default=None, description="Current field value if readable")


class DiscoveredFields(ToolResult):
    """Result from sap_discover_fields tool."""

    field_count: int = Field(ge=0, description="Number of fields found")
    fields: list[FieldInfo] = Field(
        default_factory=list,
        description="List of discovered fields with selectors - use the 'selector' field for targeting",
    )


class FieldLookupResult(ToolResult):
    """Result from sap_lookup_fields tool."""

    transaction: TCode = Field(description="Transaction code looked up")
    fields: dict[str, str] = Field(default_factory=dict, description="Field name → selector")
    similar_transactions: list[str] | None = Field(default=None, description="Similar tcodes if not found")


class FieldFillError(BaseModel):
    """Error that occurred while filling a specific field."""

    field: str = Field(description="Field key (label or selector) that failed")
    error: str = Field(description="Error message")


class FillFormResult(ToolResult):
    """Result from sap_fill_form tool."""

    filled: list[str] = Field(default_factory=list, description="Fields successfully filled")
    not_found: list[str] = Field(default_factory=list, description="Fields not found on page")
    errors: list[FieldFillError] = Field(default_factory=list, description="Fields that errored during fill")


class SetFieldResult(ToolResult):
    """Result from sap_set_field tool."""

    label: str = Field(default="", description="Label or selector used to find the field")
    value: str = Field(default="", description="Value that was set")
    selector_used: str | None = Field(default=None, description="CSS selector that matched the field")


class ShortcutInfo(BaseModel):
    """Single keyboard shortcut discovered on the current screen."""

    action: str = Field(description="Action/button text (e.g., 'Person anlegen', 'Ausführen')")
    shortcut: str = Field(description="Keyboard shortcut (e.g., 'F5', 'Strg+F5', 'Umschalt+F3')")


class ShortcutsResult(ToolResult):
    """Result from sap_get_shortcuts tool."""

    shortcuts: list[ShortcutInfo] = Field(
        default_factory=list,
        description="List of keyboard shortcuts available on current screen",
    )

    @property
    def shortcut_count(self) -> int:
        """Number of shortcuts found."""
        return len(self.shortcuts)


class DismissPopupResult(ToolResult):
    """Result from sap_dismiss_popup tool."""

    button_clicked: str | None = Field(default=None, description="Label of button that was clicked")
    popup_dismissed: bool = Field(default=False, description="Whether popup is now gone")
    status_bar_type: StatusBarType = Field(default="none", description="Status bar message type after dismissing popup")
    status_bar_message: str = Field(default="", description="Status bar text after dismissing popup")
