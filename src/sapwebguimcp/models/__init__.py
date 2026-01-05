"""
Data models for SAP Web GUI MCP Server.

This module contains Pydantic models and configuration classes.
"""

from sapwebguimcp.models.alv_models import (
    AlvCellInfo,
    AlvColumn,
    AlvMetadata,
    TableCellClickResult,
)
from sapwebguimcp.models.base import TCODE_PATTERN, PopupButton, PopupInfo, TCode, ToolResult
from sapwebguimcp.models.browser import (
    BrowserManager,
    close_browser_manager,
    get_browser_manager,
)
from sapwebguimcp.models.browser_results import (
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
from sapwebguimcp.models.config import (
    BrowserMode,
    BrowserType,
    SapWebGuiSettings,
    get_settings,
)
from sapwebguimcp.models.intent_models import (
    FeedbackEntry,
    FeedbackLogResult,
    IntentEntry,
    IntentLogResult,
)
from sapwebguimcp.models.sap_results import (
    ButtonInfo,
    CapabilitiesResult,
    DiscoveredButtons,
    DiscoveredFields,
    DismissPopupResult,
    DropdownFillResult,
    DropdownInfo,
    FieldFillError,
    FieldInfo,
    FieldLookupResult,
    FillFormResult,
    FormField,
    FormFieldsProcessResult,
    FormFieldsResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    SapFieldType,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    SetFieldResult,
    ShortcutInfo,
    ShortcutsResult,
    StatusBarInfo,
    TableData,
    TableRow,
    ToolInfo,
    TransactionResult,
)
from sapwebguimcp.models.workflow_models import (
    Workflow,
    WorkflowDeleteResult,
    WorkflowError,
    WorkflowListResult,
    WorkflowRunResult,
    WorkflowSaveInput,
    WorkflowSaveResult,
    WorkflowSubmitResult,
)

__all__ = [
    # Base
    "TCODE_PATTERN",
    "PopupButton",
    "PopupInfo",
    "TCode",
    "ToolResult",
    # ALV models
    "AlvCellInfo",
    "AlvColumn",
    "AlvMetadata",
    "TableCellClickResult",
    # Config models
    "BrowserMode",
    "BrowserType",
    "SapWebGuiSettings",
    "get_settings",
    # Browser manager
    "BrowserManager",
    "get_browser_manager",
    "close_browser_manager",
    # SAP results
    "ButtonInfo",
    "CapabilitiesResult",
    "DiscoveredButtons",
    "DiscoveredFields",
    "DismissPopupResult",
    "DropdownFillResult",
    "DropdownInfo",
    "FieldFillError",
    "FieldInfo",
    "FieldLookupResult",
    "FillFormResult",
    "FormField",
    "FormFieldsProcessResult",
    "FormFieldsResult",
    "KeepaliveResult",
    "KeyboardResult",
    "LoginResult",
    "SapFieldType",
    "ScreenInfo",
    "ScreenText",
    "SessionStatus",
    "SetFieldResult",
    "ShortcutInfo",
    "ShortcutsResult",
    "StatusBarInfo",
    "TableData",
    "TableRow",
    "ToolInfo",
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
    # Intent and feedback models
    "FeedbackEntry",
    "FeedbackLogResult",
    "IntentEntry",
    "IntentLogResult",
    # Workflow models
    "Workflow",
    "WorkflowDeleteResult",
    "WorkflowError",
    "WorkflowListResult",
    "WorkflowRunResult",
    "WorkflowSaveInput",
    "WorkflowSaveResult",
    "WorkflowSubmitResult",
]
