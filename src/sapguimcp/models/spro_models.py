"""
Pydantic models for SPRO (Customizing IMG) search tool.

These models represent search results from the SAP Implementation Guide (IMG),
where each result is an IMG activity with its parent node and area context.
"""

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult

__all__ = [
    "SPROActivity",
    "SPROSearchResult",
    "SPROFileSummary",
]


class SPROActivity(BaseModel):
    """A single IMG customizing activity from SPRO search results."""

    activity_name: str = Field(description="Name of the customizing activity (e.g., 'Define Countries')")
    parent_node: str = Field(default="", description="Immediate parent node in the IMG tree")
    area: str = Field(default="", description="Broad area/section in the IMG tree")


class SPROSearchResult(ToolResult):
    """Result of SPRO IMG search."""

    query: str = Field(description="Search keyword that was used")
    activities: list[SPROActivity] = Field(default_factory=list, description="Matching IMG activities")
    activity_count: int = Field(default=0, description="Number of activities found")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp when search was executed")


class SPROFileSummary(ToolResult):
    """Summary result when SPRO output is written to file."""

    output_file: str = Field(description="Path to JSON file with full SPROSearchResult")
    query: str = Field(description="Search keyword that was used")
    activity_count: int = Field(default=0, description="Total activities found")
    sample_activities: list[SPROActivity] = Field(default_factory=list, description="Preview of first 5 activities")
    retrieved_at: AwareDatetime = Field(description="UTC timestamp when search was executed")
