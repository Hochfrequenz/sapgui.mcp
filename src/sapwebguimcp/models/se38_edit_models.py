"""Models for SE38 (ABAP Report Editor) edit operations."""

from pydantic import Field

from sapwebguimcp.models.base import ToolResult


class SE38EditResult(ToolResult):
    """Result of editing an ABAP report in SE38."""

    program_name: str = Field(description="Name of the ABAP report that was edited")
    backup_source: str = Field(description="Original source code before editing (for reference/undo)")
    check_messages: list[str] = Field(default_factory=list, description="Messages from syntax check (Ctrl+F2)")
    activated: bool = Field(default=False, description="Whether the report was successfully activated")
