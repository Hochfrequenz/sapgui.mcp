"""Models for SE38 (ABAP Report Editor) edit operations."""

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SE38EditResult(ToolResult):
    """Result of editing an ABAP report in SE38."""

    program_name: str = Field(description="Name of the ABAP report that was edited")
    backup_source: str = Field(description="Original source code before editing (for reference/undo)")
    # TODO: description should say "syntax check and activation" to match SE37/SE24 (both messages are stored)
    check_messages: list[str] = Field(default_factory=list, description="Messages from syntax check (Ctrl+F2)")
    activated: bool = Field(default=False, description="Whether the report was successfully activated")
