"""Models for sap_quick_report composite tool."""

from enum import StrEnum

from pydantic import Field

from sapguimcp.models.base import ToolResult
from sapguimcp.models.sap_results import (
    ScreenText,
    StatusBarType,
    TableData,
)


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

    # Status bar (flat fields, consistent with KeyboardResult pattern)
    status_bar_type: StatusBarType | None = Field(default=None, description="Status bar type if read")
    status_bar_message: str | None = Field(default=None, description="Status bar text if read")

    # screen_type="table"
    table: TableData | None = Field(default=None, description="Table data when screen_type is 'table' or 'list'")

    # screen_type="error" or "unknown"
    screen_text: ScreenText | None = Field(
        default=None,
        description="Screen text when screen_type is 'error' or 'unknown'",
    )

    # Warnings (e.g. "Checkbox 'Geplant' not found on screen")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings from the pipeline",
    )
