"""
Data models for SAP Web GUI MCP Server.

This module contains Pydantic models and configuration classes.
"""

from sapwebguimcp.models.base import TCODE_PATTERN, TCode, ToolResult
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
from sapwebguimcp.models.intent_models import IntentEntry, IntentLogResult
from sapwebguimcp.models.sap_results import (
    DiscoveredFields,
    FieldFillError,
    FieldInfo,
    FieldLookupResult,
    FillFormResult,
    KeepaliveResult,
    KeyboardResult,
    LoginResult,
    ScreenInfo,
    ScreenText,
    SessionStatus,
    SetFieldResult,
    StatusBarInfo,
    TableData,
    TableRow,
    TransactionResult,
)

__all__ = [
    # Base
    "TCODE_PATTERN",
    "TCode",
    "ToolResult",
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
    "DiscoveredFields",
    "FieldFillError",
    "FieldInfo",
    "FieldLookupResult",
    "FillFormResult",
    "KeepaliveResult",
    "KeyboardResult",
    "LoginResult",
    "ScreenInfo",
    "ScreenText",
    "SessionStatus",
    "SetFieldResult",
    "StatusBarInfo",
    "TableData",
    "TableRow",
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
    # Intent models
    "IntentEntry",
    "IntentLogResult",
]
