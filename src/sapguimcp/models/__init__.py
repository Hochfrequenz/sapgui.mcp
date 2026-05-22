"""
Shared data models — the contract between desktop and webgui backends.

Both projects depend on these models after the split. Backend-specific
models live in their respective packages:

- ``backend/webgui/models/`` — browser_results, session_registry
- ``backend/desktop/models/`` — com_results

See also: ``backend/webgui/types.py`` (AriaSnapshot),
``backend/desktop/types.py`` (ComTreeSnapshot).
"""

from sapguimcp.models.abapgit_models import AbapGitActionResult, AbapGitListResult, AbapGitRepoInfo
from sapguimcp.models.alv_models import (
    AlvCellInfo,
    AlvMetadata,
    TableCellClickResult,
)
from sapguimcp.models.base import TCODE_PATTERN, PopupButton, PopupInfo, PopupType, SessionId, TCode, ToolResult
from sapguimcp.models.config import (
    BrowserMode,
    BrowserType,
    SapGuiSettings,
    get_sap_config,
    get_settings,
)
from sapguimcp.models.intent_models import (
    FeedbackEntry,
    FeedbackLogResult,
    IntentEntry,
    IntentLogResult,
)
from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapguimcp.models.sap_results import (
    ButtonInfo,
    CapabilitiesResult,
    ClickButtonResult,
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
    FormFieldsResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    SapFieldType,
    ScreenInfo,
    ScreenText,
    SelectDropdownResult,
    SelectTabResult,
    SessionBindResult,
    SessionCloseResult,
    SessionInfo,
    SessionListResult,
    SessionReleaseResult,
    SessionResetResult,
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
from sapguimcp.models.se09_models import (
    TransportListResult,
    TransportRequest,
)
from sapguimcp.models.se11_models import (
    SE11Entry,
    SE11Error,
    SE11Field,
    SE11FileSummary,
    SE11ObjectType,
    SE11Result,
)
from sapguimcp.models.se16_models import (
    SE16FileSummary,
    SE16Result,
    SE16Row,
)
from sapguimcp.models.se24_edit_models import SE24EditResult
from sapguimcp.models.se24_models import (
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
from sapguimcp.models.se37_edit_models import SE37EditResult
from sapguimcp.models.se37_models import (
    SE37Entry,
    SE37Error,
    SE37Exception,
    SE37FileSummary,
    SE37Parameter,
    SE37ParameterCategory,
    SE37Result,
    SE37TypingMethod,
)
from sapguimcp.models.se38_edit_models import SE38EditResult
from sapguimcp.models.se93_models import (
    SE93Entry,
    SE93Error,
    SE93FileSummary,
    SE93Result,
    SE93TransactionType,
)
from sapguimcp.models.slg1_models import (
    SLG1FileSummary,
    SLG1LogEntry,
    SLG1LogListResult,
)
from sapguimcp.models.sm30_models import (
    SM30FileSummary,
    SM30Row,
    SM30ViewResult,
    SM30ViewType,
)
from sapguimcp.models.sm37_models import (
    SM37Job,
    SM37JobListResult,
    SM37JobLog,
)
from sapguimcp.models.spro_models import (
    SPROActivity,
    SPROFileSummary,
    SPROSearchResult,
)
from sapguimcp.models.st22_models import (
    ST22Dump,
    ST22DumpDetail,
    ST22DumpDetailResult,
    ST22DumpListResult,
)

__all__ = [
    # abapGit models
    "AbapGitActionResult",
    "AbapGitListResult",
    "AbapGitRepoInfo",
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
    "AlvMetadata",
    "TableCellClickResult",
    # Config models
    "BrowserMode",
    "BrowserType",
    "SapGuiSettings",
    "get_sap_config",
    "get_settings",
    # Quick report models
    "QuickReportResult",
    "ScreenClassification",
    # SAP results
    "ButtonInfo",
    "CapabilitiesResult",
    "ClickButtonResult",
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
    "FormFieldsResult",
    "KeepaliveResult",
    "KeyboardResult",
    "LoginResult",
    "SapFieldType",
    "ScreenInfo",
    "ScreenText",
    "SelectDropdownResult",
    "SelectTabResult",
    "SessionBindResult",
    "SessionCloseResult",
    "SessionInfo",
    "SessionListResult",
    "SessionReleaseResult",
    "SessionResetResult",
    "SessionStatus",
    "SetFieldResult",
    "ShortcutInfo",
    "ShortcutsResult",
    "StatusBarInfo",
    "TableData",
    "TableRow",
    "ToolInfo",
    "TransactionResult",
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
    "TransportRequest",
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
    # SPRO models
    "SPROActivity",
    "SPROFileSummary",
    "SPROSearchResult",
    # SM30 models
    "SM30FileSummary",
    "SM30Row",
    "SM30ViewResult",
    "SM30ViewType",
]
