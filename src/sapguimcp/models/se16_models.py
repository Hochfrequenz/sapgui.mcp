"""SE16 (Data Browser) query result models."""

from typing import Any

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult


class SE16Row(BaseModel):
    """A single row from SE16 query result.

    Design decision: Using dict[str, Any] to allow smart type coercion
    (numbers, dates) while maintaining Pydantic serializability. If a value
    cannot be safely coerced, it remains as string. All values are guaranteed
    JSON-serializable.

    Why not dict[str, str]? We want to preserve numeric types where possible
    so LLMs can perform calculations without parsing strings. The parser
    attempts safe coercion (int, float) and falls back to string on failure.
    """

    data: dict[str, Any] = Field(description="Column name -> value (types coerced where safe)")


class SE16Result(ToolResult):
    """Result of SE16 query - returns all rows inline.

    Use this for small to medium result sets. For large results (1000+ rows),
    consider using output_file parameter to write to disk instead.
    """

    table: str = Field(description="Table name that was queried")
    total_hits: int = Field(description="Total rows matching query (from SAP 'Number of Hits')")
    returned_rows: int = Field(description="Number of rows actually returned")
    truncated: bool = Field(description="True if total_hits >= max_hits (more data may exist in table)")
    columns: list[str] = Field(description="Column names in order")
    rows: list[SE16Row] = Field(default_factory=list, description="All collected rows")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp when query completed")


class SE16FileSummary(ToolResult):
    """Summary result when SE16 output is written to file.

    Returned instead of SE16Result when output_file parameter is provided.
    Contains metadata and a preview of the first few rows.
    """

    output_file: str = Field(description="Path to JSON file containing full SE16Result")
    table: str = Field(description="Table name that was queried")
    total_hits: int = Field(description="Total rows matching query")
    returned_rows: int = Field(description="Number of rows written to file")
    truncated: bool = Field(description="True if total_hits >= max_hits")
    columns: list[str] = Field(description="Column names in order")
    sample_rows: list[SE16Row] = Field(default_factory=list, description="Preview of first 5 rows")
