"""SAP tool result models."""

from typing import Literal

from pydantic import BaseModel, Field

from sapwebguimcp.models.base import TCode, ToolResult


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
    """Result from sap_keyboard tool."""

    key: str = Field(description="Key that was sent")
    page_title: str | None = Field(default=None, description="Current page title after")


class KeepaliveResult(ToolResult):
    """Result from sap_keepalive_start/stop tools."""

    running: bool = Field(description="Whether keepalive is now running")
    interval_seconds: int | None = Field(default=None, ge=1, description="Ping interval if running")


class StatusBarInfo(ToolResult):
    """Result from sap_read_status_bar tool."""

    type: Literal["S", "E", "W", "I", "none"] = Field(
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
    """A single table row with row number and cell data."""

    row: int = Field(ge=1, description="Row number (1-indexed)")
    data: dict[str, str] = Field(description="Cell values by column header")


class TableData(ToolResult):
    """Result from sap_read_table tool."""

    headers: list[str] = Field(default_factory=list, description="Column headers")
    rows: list[TableRow] = Field(default_factory=list, description="Row data")
    total_rows: int = Field(default=0, ge=0, description="Total rows found")
    start_row: int = Field(default=1, ge=1, description="First row returned (1-indexed)")
    end_row: int | None = Field(default=None, ge=1, description="Last row returned")


class FieldInfo(BaseModel):
    """Single field discovered on screen."""

    id: str | None = Field(default=None, description="Element ID attribute")
    name: str | None = Field(default=None, description="Field name from SAP lsdata attribute")
    label: str | None = Field(default=None, description="Associated label text")
    type: str | None = Field(default=None, description="Input type (text, checkbox, etc.)")
    selector: str = Field(description="CSS selector for targeting this field")
    value: str | None = Field(default=None, description="Current field value if readable")


class DiscoveredFields(ToolResult):
    """Result from sap_discover_fields tool."""

    field_count: int = Field(ge=0, description="Number of fields found")
    fields: list[FieldInfo] = Field(default_factory=list)


class FieldLookupResult(ToolResult):
    """Result from sap_lookup_fields tool."""

    transaction: TCode = Field(description="Transaction code looked up")
    fields: dict[str, str] = Field(default_factory=dict, description="Field name → selector")
    similar_transactions: list[str] | None = Field(default=None, description="Similar tcodes if not found")
