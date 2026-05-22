"""SAP tool result models."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from sapguimcp.models.alv_models import AlvCellInfo, AlvMetadata
from sapguimcp.models.base import PopupInfo, TCode, ToolResult

# Shared type for SAP status bar message types
StatusBarType = Literal["S", "E", "W", "I", "none"]
"""Status bar message type: 'S' (success), 'E' (error), 'W' (warning), 'I' (info), 'none' (empty)."""


class SapFieldType(StrEnum):
    """Type of SAP input control."""

    TEXT = "text"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    RADIO = "radio"


class FormField(BaseModel):
    """A fillable field on a SAP screen."""

    id: str = Field(description="Element ID for targeting with sap_fill_form or browser tools")
    label: str = Field(description="Visible label text associated with this field")
    field_type: SapFieldType = Field(description="Type of input control: text, dropdown, checkbox, or radio")
    current_value: str | None = Field(default=None, description="Current field value, or None if empty")
    checked: bool | None = Field(
        default=None,
        description="True/False for checkbox/radio fields, None for text/dropdown",
    )
    readonly: bool = Field(
        default=False, description="True if field cannot be edited (HTML readonly/disabled attribute)"
    )
    options: list[str] | None = Field(
        default=None,
        description="Available options for dropdown fields. Only populated when include_dropdown_options=True",
    )


class DropdownInfo(BaseModel):
    """Dropdown field info for sap_get_screen_text."""

    id: str = Field(description="Element ID for targeting")
    label: str = Field(description="Visible label text")
    options: list[str] = Field(description="Available dropdown options")


class LoginResult(ToolResult):
    """Result from sap_login tool."""

    url: str | None = Field(default=None, description="SAP URL that was accessed")
    user: str | None = Field(default=None, description="Logged in username")
    already_logged_in: bool = Field(default=False, description="Was already logged in")
    guidance: str | None = Field(
        default=None,
        description="Recommended next action after login (e.g., call sap_get_capabilities)",
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Registry session ID assigned to the new login (e.g. 's1', 's2'). "
            "Pass this as the 'session' / 'session_id' parameter on subsequent "
            "tool calls to address this specific login when multiple parallel "
            "sessions are active. Desktop backend only — webgui currently runs "
            "a single session."
        ),
    )


class TransactionResult(ToolResult):
    """Result from sap_transaction tool."""

    tcode: TCode = Field(description="Transaction code executed")
    page_title: str | None = Field(default=None, description="Current page title")
    new_window: bool = Field(default=False, description="Opened in new session")
    session_id: str | None = Field(
        default=None,
        description="Session ID of new session (only set when new_window=True)",
    )
    session_count: int | None = Field(default=None, ge=1, description="Number of SAP sessions")


class SessionStatus(ToolResult):
    """Result from sap_session_status tool."""

    status: Literal["active", "timed_out", "logged_off", "no_page", "unknown"] = Field(
        description="Session state: 'active' (responsive), 'timed_out', 'logged_off', 'no_page', or 'unknown'"
    )
    message: str = Field(description="Human-readable status description")


class SessionInfo(BaseModel):
    """Information about a single SAP session."""

    session_id: str = Field(description="Session identifier (e.g., 's1', 's2')")
    tcode: str | None = Field(default=None, description="Current transaction code (e.g., 'VA01')")
    title: str | None = Field(default=None, description="Current screen title")
    is_primary: bool = Field(default=False, description="True if this is the primary session ('s1')")
    agent_id: str | None = Field(default=None, description="Agent bound to this session, if any")
    system_name: str | None = Field(default=None, description="SAP system ID (e.g., 'S4U', 'HFQ')")
    client: str | None = Field(default=None, description="SAP client number (e.g., '100')")
    user: str | None = Field(default=None, description="Logged-in SAP user")


class SessionListResult(ToolResult):
    """Result from sap_session_list tool."""

    sessions: list[SessionInfo] = Field(
        default_factory=list, description="All active SAP sessions with their current state"
    )

    @property
    def session_count(self) -> int:
        """Number of active sessions."""
        return len(self.sessions)


class SessionCloseResult(ToolResult):
    """Result from sap_session_close tool."""

    session_id: str | None = Field(default=None, description="ID of the session that was closed (e.g., 's2')")
    remaining_sessions: int = Field(default=0, ge=0, description="Sessions still active after closing")


class SessionBindResult(ToolResult):
    """Result from sap_session_bind tool."""

    session_id: str | None = Field(default=None, description="ID of the session that was bound")
    agent_id: str | None = Field(default=None, description="Agent that now owns the session")
    previous_agent: str | None = Field(default=None, description="Previous agent binding, if any")


class SessionReleaseResult(ToolResult):
    """Result from sap_session_release tool."""

    session_id: str | None = Field(default=None, description="ID of the session that was released")
    released_agent: str | None = Field(default=None, description="Agent that was unbound, if any")


class SessionResetResult(ToolResult):
    """Result from sap_session_reset_to_primary tool.

    Reports the outcome of bulk-closing every session except the primary
    one. ``killed_agents`` lists agents whose bound sessions were closed
    — those agents must rebind to a different session before their next
    call. See issue #637 for the parallel-agent drift scenario.
    """

    closed_sessions: list[str] = Field(
        default_factory=list,
        description="Session IDs that were closed (e.g. ['s2', 's3', 's4'])",
    )
    remaining_sessions: list[str] = Field(
        default_factory=list,
        description="Session IDs still active after the reset (typically just ['s1'])",
    )
    killed_agents: list[str] = Field(
        default_factory=list,
        description=(
            "Agent IDs whose bound sessions were closed by this reset. "
            "These agents must call sap_session_bind on a different session before continuing."
        ),
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Per-session error strings, one per failed close attempt",
    )


class KeyboardResult(ToolResult):
    """Result from sap_press_key tool.

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
    system_name: str | None = Field(default=None, description="SAP system ID (e.g., 'S4U', 'HFQ')")
    client: str | None = Field(default=None, description="SAP client number (e.g., '100')")
    user: str | None = Field(default=None, description="Logged-in SAP user")


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
    dropdowns: list[DropdownInfo] | None = Field(
        default=None,
        description="Dropdown fields with available options. Only populated when include_dropdown_options=True",
    )


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


class ButtonInfo(BaseModel):
    """Single button discovered on screen."""

    label: str = Field(description="Button text (from title attribute or lsdata)")
    id: str | None = Field(default=None, description="Element ID attribute")
    selector: str | None = Field(default=None, description="CSS selector for clicking this button")
    shortcut: str | None = Field(default=None, description="Keyboard shortcut if shown (e.g., 'F3', 'Strg+S')")
    accesskey: str | None = Field(default=None, description="Accesskey attribute for keyboard activation")


class DiscoveredButtons(ToolResult):
    """Result from sap_discover_buttons tool."""

    button_count: int = Field(ge=0, description="Number of buttons found")
    buttons: list[ButtonInfo] = Field(
        default_factory=list,
        description="List of discovered buttons with selectors - use the 'selector' field for clicking",
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
    available_options: list[str] | None = Field(
        default=None,
        description="For dropdown fields: list of valid options when requested value was not found",
    )


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
    available_options: list[str] | None = Field(
        default=None,
        description="For dropdown fields: list of valid options when requested value was not found",
    )


class FormFieldsResult(ToolResult):
    """Result from sap_get_form_fields tool."""

    fields: list[FormField] = Field(
        default_factory=list,
        description="Fillable fields discovered on the current screen",
    )

    @property
    def field_count(self) -> int:
        """Number of fields found."""
        return len(self.fields)

    @property
    def dropdown_count(self) -> int:
        """Number of dropdown fields found."""
        return sum(1 for f in self.fields if f.field_type == SapFieldType.DROPDOWN)


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


class ClosePopupResult(ToolResult):
    """Result from sap_close_popup tool."""

    button_clicked: str | None = Field(default=None, description="Label of button that was clicked")
    popup_closed: bool = Field(default=False, description="Whether popup is now gone")
    status_bar_type: StatusBarType = Field(default="none", description="Status bar message type after closing popup")
    status_bar_message: str = Field(default="", description="Status bar text after closing popup")


class ClickButtonResult(ToolResult):
    """Result from sap_click_button tool."""

    label: str = Field(description="Button label that was clicked")


class SelectTabResult(ToolResult):
    """Result from sap_select_tab tool."""

    label: str = Field(description="Tab label that was selected")


class SelectDropdownResult(ToolResult):
    """Result from sap_select_dropdown tool."""

    label: str = Field(description="Dropdown field label")
    value: str = Field(description="Option value that was selected")
    available_options: list[str] | None = Field(
        default=None,
        description="Available options if selection failed (e.g., value not found)",
    )


class DropdownFillResult(BaseModel):
    """Internal result from filling a dropdown field."""

    success: bool = Field(description="Whether the dropdown option was selected")
    error_message: str | None = Field(default=None, description="Error message if selection failed")
    available_options: list[str] | None = Field(default=None, description="Valid options if requested value not found")
    popup_after: PopupInfo | None = Field(default=None, description="Popup that appeared after selection")


class ToolInfo(BaseModel):
    """Information about a single MCP tool."""

    name: str = Field(description="Tool name (e.g., 'sap_login', 'browser_click')")
    description: str = Field(description="Full tool description including usage guidance")


class CapabilitiesResult(ToolResult):
    """Result from sap_get_capabilities tool."""

    tools: list[ToolInfo] = Field(
        default_factory=list,
        description="All available tools with their names and descriptions",
    )
    sap_knowledge: str | None = Field(
        default=None,
        description="Free-form SAP domain knowledge, tips, and best practices in markdown format",
    )

    @property
    def tool_count(self) -> int:
        """Number of tools available."""
        return len(self.tools)
