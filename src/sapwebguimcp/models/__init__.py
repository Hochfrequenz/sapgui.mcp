"""
Data models for SAP Web GUI MCP Server.

This module contains Pydantic models and configuration classes.
"""

from sapwebguimcp.models.abapgit_models import AbapGitActionResult
from sapwebguimcp.models.alv_models import (
    AlvCellInfo,
    AlvColumn,
    AlvMetadata,
    TableCellClickResult,
)
from sapwebguimcp.models.base import TCODE_PATTERN, PopupButton, PopupInfo, PopupType, SessionId, TCode, ToolResult
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
    ClosePopupResult,
    DiscoveredButtons,
    DiscoveredFields,
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
    SessionBindResult,
    SessionCloseResult,
    SessionInfo,
    SessionListResult,
    SessionReleaseResult,
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
from sapwebguimcp.models.se09_models import (
    TransportListResult,
    TransportObject,
    TransportRequest,
    TransportTask,
)
from sapwebguimcp.models.se11_models import (
    SE11Entry,
    SE11Error,
    SE11Field,
    SE11FileSummary,
    SE11ObjectType,
    SE11Result,
)
from sapwebguimcp.models.se16_models import (
    SE16FileSummary,
    SE16Result,
    SE16Row,
)
from sapwebguimcp.models.se24_edit_models import SE24EditResult
from sapwebguimcp.models.se24_models import (
    SE24Attribute,
    SE24Entry,
    SE24Error,
    SE24FileSummary,
    SE24Method,
    SE24MethodException,
    SE24MethodParameter,
    SE24ObjectType,
    SE24ParameterCategory,
    SE24Result,
    SE24Visibility,
)
from sapwebguimcp.models.se37_edit_models import SE37EditResult
from sapwebguimcp.models.se37_models import (
    SE37Entry,
    SE37Error,
    SE37Exception,
    SE37FileSummary,
    SE37Parameter,
    SE37ParameterCategory,
    SE37Result,
    SE37TypingMethod,
)
from sapwebguimcp.models.se38_edit_models import SE38EditResult
from sapwebguimcp.models.se93_models import (
    SE93Entry,
    SE93Error,
    SE93FileSummary,
    SE93Result,
    SE93TransactionType,
)
from sapwebguimcp.models.session_registry import SessionRegistry
from sapwebguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogEntry,
    SLG1LogListResult,
)
from sapwebguimcp.models.sm37_models import (
    SM37Job,
    SM37JobListResult,
    SM37JobLog,
)
from sapwebguimcp.models.st22_models import (
    ST22Dump,
    ST22DumpDetail,
    ST22DumpDetailResult,
    ST22DumpListResult,
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
    # abapGit models
    "AbapGitActionResult",
    # Base
    "TCODE_PATTERN",
    "PopupButton",
    "PopupInfo",
    "PopupType",
    "SessionId",
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
    # Session registry
    "SessionRegistry",
    # SAP results
    "ButtonInfo",
    "CapabilitiesResult",
    "DiscoveredButtons",
    "DiscoveredFields",
    "ClosePopupResult",
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
    "SessionBindResult",
    "SessionCloseResult",
    "SessionInfo",
    "SessionListResult",
    "SessionReleaseResult",
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
    # SE11 models
    "SE11Entry",
    "SE11Error",
    "SE11Field",
    "SE11FileSummary",
    "SE11ObjectType",
    "SE11Result",
    # SE16 models
    "SE16FileSummary",
    "SE16Result",
    "SE16Row",
    # SE37 models
    "SE37Entry",
    "SE37Error",
    "SE37Exception",
    "SE37FileSummary",
    "SE37Parameter",
    "SE37ParameterCategory",
    "SE37Result",
    "SE37TypingMethod",
    # SE24 models
    "SE24Attribute",
    "SE24Entry",
    "SE24Error",
    "SE24FileSummary",
    "SE24Method",
    "SE24MethodException",
    "SE24MethodParameter",
    "SE24ObjectType",
    "SE24ParameterCategory",
    "SE24Result",
    "SE24Visibility",
    # SE24 edit models
    "SE24EditResult",
    # SE37 edit models
    "SE37EditResult",
    # SE38 edit models
    "SE38EditResult",
    # SM37 models
    "SM37Job",
    "SM37JobListResult",
    "SM37JobLog",
    # ST22 models
    "ST22Dump",
    "ST22DumpDetail",
    "ST22DumpDetailResult",
    "ST22DumpListResult",
    # SE09 models
    "TransportListResult",
    "TransportObject",
    "TransportRequest",
    "TransportTask",
    # SE93 models
    "SE93Entry",
    "SE93Error",
    "SE93FileSummary",
    "SE93Result",
    "SE93TransactionType",
    # SLG1 models
    "SLG1FileSummary",
    "SLG1LogEntry",
    "SLG1LogListResult",
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
