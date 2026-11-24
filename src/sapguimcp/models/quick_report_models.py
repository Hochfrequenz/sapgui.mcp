"""Models for the sap_quick_report composite tool."""

from enum import StrEnum

from pydantic import Field

from sapguimcp.models.base import ToolResult
from sapguimcp.models.sap_results import ScreenText, StatusBarType, TableData


class ScreenClassification(StrEnum):
    """What appeared on screen after F8."""

    TABLE = "table"
    LIST = "list"
    EMPTY = "empty"
    ERROR = "error"
    UNKNOWN = "unknown"


class QuickReportResult(ToolResult):
    """Result of sap_quick_report."""

    tcode: str = Field(description="Transaction code that was executed")
    screen_type: ScreenClassification = Field(
        description="What appeared after F8: table, list, empty, error, or unknown"
    )
    page_title: str = Field(default="", description="Screen title after F8")
    status_bar_type: StatusBarType | None = Field(default=None, description="Status bar type after F8")
    status_bar_message: str | None = Field(default=None, description="Status bar text after F8")
    table: TableData | None = Field(
        default=None, description="Rows of the ALV grid or table control (screen_type 'table')"
    )
    list_lines: list[str] | None = Field(
        default=None, description="Text lines of the classic list (screen_type 'list')"
    )
    list_truncated: bool = Field(default=False, description="True if the classic list has more lines than max_rows")
    screen_text: ScreenText | None = Field(
        default=None, description="Screen text when screen_type is 'error' or 'unknown'"
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings from the pipeline")
