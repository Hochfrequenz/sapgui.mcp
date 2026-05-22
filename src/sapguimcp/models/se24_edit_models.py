"""Pydantic models for SE24 (Class Builder) edit results."""

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SE24EditResult(ToolResult):
    """Result of editing a class method in SE24."""

    class_name: str = Field(description="Name of the class that was edited")
    method_name: str = Field(description="Name of the method that was edited")
    backup_source: str = Field(description="Original method source code before editing (for reference/undo)")
    check_messages: list[str] = Field(default_factory=list, description="Messages from syntax check and activation")
    activated: bool = Field(default=False, description="Whether the class was successfully activated")
