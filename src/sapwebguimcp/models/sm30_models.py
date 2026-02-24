"""
Pydantic models for SM30 (Table Maintenance View) lookup tool.

These models represent view data retrieved from SM30 in display mode,
including dynamically-parsed column headers and row values.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from sapwebguimcp.models.base import ToolResult

__all__ = [
    "SM30Row",
    "SM30ViewResult",
    "SM30FileSummary",
    "SM30ViewType",
]

# View type detection
SM30ViewType = Literal["flat", "unsupported"]


class SM30Row(BaseModel):
    """A single row from an SM30 table maintenance view.

    Uses dict[str, str] since SM30 views contain configuration data
    that is best represented as strings (unlike SE16 which benefits
    from type coercion for numeric queries).
    """

    values: dict[str, str] = Field(description="Column name -> cell value")


class SM30ViewResult(ToolResult):
    """Result of SM30 table maintenance view lookup."""

    view_name: str = Field(description="View or table name that was looked up")
    description: str = Field(default="", description="View description from screen title")
    view_type: SM30ViewType = Field(description="Detected view type: 'flat' or 'unsupported'")
    columns: list[str] = Field(default_factory=list, description="Column names in display order")
    rows: list[SM30Row] = Field(default_factory=list, description="All rows from the view")
    row_count: int = Field(default=0, description="Number of rows returned")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp when data was retrieved")


class SM30FileSummary(ToolResult):
    """Summary result when SM30 output is written to file.

    Returned instead of SM30ViewResult when output_file parameter is provided.
    Contains metadata and a preview of the first few rows.
    """

    output_file: str = Field(description="Path to JSON file containing full SM30ViewResult")
    view_name: str = Field(description="View or table name that was looked up")
    description: str = Field(default="", description="View description")
    view_type: SM30ViewType = Field(description="Detected view type")
    columns: list[str] = Field(default_factory=list, description="Column names in order")
    row_count: int = Field(default=0, description="Total rows written to file")
    sample_rows: list[SM30Row] = Field(default_factory=list, description="Preview of first 5 rows")
