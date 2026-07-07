"""Models for ABAP external breakpoint management tools."""

from typing import Literal

from pydantic import BaseModel, Field

from sapguimcp.models.base import ToolResult

_ObjectType = Literal["PROG", "CLAS", "FUGR"]


class BreakpointEntry(BaseModel):
    """A single external breakpoint entry."""

    line_number: int = Field(description="1-indexed SAP display line number", ge=1)
    source_line: str = Field(description="Source code text at this line")


class BreakpointSetResult(ToolResult):
    """Result of sap_breakpoint_set."""

    object_type: _ObjectType = Field(description="Object type: PROG, CLAS, or FUGR")
    object_name: str = Field(description="Program name, class name, or function group name")
    method_name: str | None = Field(default=None, description="Method or function module name (None for PROG)")
    line_number: int | None = Field(default=None, description="Resolved 1-indexed line number")
    action: Literal["set"] = Field(default="set", description="What actually happened")
    status_message: str = Field(default="", description="Raw SAP status bar message")
    confirmation_skipped: bool = Field(
        default=False,
        description=(
            "True if the breakpoint was armed without a real human confirmation "
            "(the connected MCP client doesn't support elicitation, or asking failed) — "
            "fail-open. False means a human explicitly confirmed via the client's "
            "confirmation dialog."
        ),
    )


class BreakpointDeleteResult(ToolResult):
    """Result of sap_breakpoint_delete."""

    object_type: _ObjectType = Field(description="Object type: PROG, CLAS, or FUGR")
    object_name: str = Field(description="Program name, class name, or function group name")
    method_name: str | None = Field(default=None, description="Method or function module name (None for PROG)")
    line_number: int | None = Field(default=None, description="1-indexed line number")
    action: Literal["deleted", "was_not_set"] = Field(default="deleted", description="What actually happened")
    status_message: str = Field(default="", description="Raw SAP status bar message")


class BreakpointListResult(ToolResult):
    """Result of sap_breakpoint_list."""

    object_type: _ObjectType = Field(description="Object type: PROG, CLAS, or FUGR")
    object_name: str = Field(description="Program name, class name, or function group name")
    method_name: str | None = Field(default=None, description="Method or function module name (None for PROG)")
    breakpoints: list[BreakpointEntry] = Field(
        default_factory=list, description="All external breakpoints found on the object"
    )
