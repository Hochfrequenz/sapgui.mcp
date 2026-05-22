"""
Pydantic models for SLG1 (Application Log) lookup tool.

These models represent application log data retrieved from SLG1,
including log headers with metadata.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SLG1FileSummary",
    "SLG1LogEntry",
    "SLG1LogListResult",
]


class SLG1LogEntry(BaseModel):
    """A single application log entry from the SLG1 log list grid."""

    log_number: str = Field(description="Log number")
    object: str = Field(description="Log object (e.g., EABL, EA)")
    subobject: str = Field(default="", description="Log subobject")
    external_id: str = Field(default="", description="External identifier")
    date: str = Field(description="Log date")
    time: str = Field(description="Log time")
    user: str = Field(default="", description="User who created the log")
    message_count: int = Field(default=0, description="Total number of messages in this log")


class SLG1LogListResult(ToolResult):
    """Result of SLG1 application log lookup."""

    logs: list[SLG1LogEntry] = Field(default_factory=list, description="Log entries found")
    log_count: int = Field(default=0, description="Number of logs parsed (may be capped at 50)")
    logs_truncated: bool = Field(
        default=False,
        description="True if more logs exist than were fetched (max 50)",
    )
    filters_applied: dict[str, str] = Field(
        default_factory=dict,
        description="Filters that were applied to the search",
    )
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")


class SLG1FileSummary(ToolResult):
    """Summary returned when results are written to file."""

    output_file: str = Field(description="Path to the output file")
    log_count: int = Field(description="Number of logs retrieved")
    total_messages: int = Field(description="Total messages across all logs")
    logs_truncated: bool = Field(default=False, description="Whether the log list was truncated")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")
