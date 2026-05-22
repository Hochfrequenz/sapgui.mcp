"""Pydantic models for ST22 (Short Dump Analysis) lookup tool.

These models represent ABAP runtime error (short dump) data retrieved from ST22,
including dump list entries and detailed dump information.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "ST22Dump",
    "ST22DumpDetail",
    "ST22DumpDetailResult",
    "ST22DumpListResult",
]


class ST22Dump(BaseModel):
    """A short dump entry from the ST22 list view."""

    index: int = Field(description="Position in the list (0-based, for use with dump_index)")
    time: str = Field(description="Time of the dump (HH:MM:SS)")
    program: str = Field(description="ABAP program that caused the dump")
    include: str | None = Field(default=None, description="Include name (if applicable)")
    error_type: str = Field(description="Runtime error type (e.g., RABAX_STATE, MESSAGE_TYPE_X)")
    short_text: str = Field(description="Human-readable short description")
    user: str = Field(description="SAP user who triggered the dump")


class ST22DumpDetail(BaseModel):
    """Detailed information from a single short dump."""

    error_type: str = Field(default="", description="Runtime error type")
    short_text: str = Field(default="", description="Human-readable short description")
    what_happened: str = Field(default="", description="Extracted from 'What happened?' section")
    how_to_correct: str = Field(default="", description="Extracted from 'How to correct' section")
    program: str = Field(default="", description="ABAP program name")
    include: str | None = Field(default=None, description="Include name")
    line: int | None = Field(default=None, description="Source line number where error occurred")
    call_stack: list[str] = Field(default_factory=list, description="Call stack entries")
    raw_text: str = Field(description="Full dump text (truncated to ~10KB) as fallback")


class ST22DumpListResult(ToolResult):
    """Result of ST22 dump list retrieval."""

    dumps: list[ST22Dump] = Field(default_factory=list, description="Short dump entries")
    dump_count: int = Field(default=0, description="Total number of dumps found")
    date_searched: str = Field(default="", description="Date that was searched (YYYY-MM-DD)")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")


class ST22DumpDetailResult(ToolResult):
    """Result of ST22 dump detail retrieval."""

    detail: ST22DumpDetail | None = Field(default=None, description="Dump detail data")
    retrieved_at: AwareDatetime = Field(description="When the data was retrieved")
