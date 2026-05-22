"""Pydantic models for SE37 (Function Module) edit results."""

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SE37EditResult(ToolResult):
    """Result of editing a function module in SE37."""

    function_module: str = Field(description="Name of the function module that was edited")
    backup_source: str = Field(description="Original source code before editing (for reference/undo)")
    check_messages: list[str] = Field(default_factory=list, description="Messages from syntax check and activation")
    activated: bool = Field(default=False, description="Whether the function module was successfully activated")
