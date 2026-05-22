"""Pydantic model for sap_run_script tool results."""

from typing import Any

from pydantic import Field

from sapguimcp.models.base import ToolResult


class SapRunScriptResult(ToolResult):
    """Result from sap_run_script. Inherits ToolResult success/error invariant."""

    output: list[Any] = Field(
        default_factory=list,
        description="Values collected via output() calls during script execution, in call order.",
    )
    error_traceback: str | None = Field(
        default=None,
        description="Full formatted traceback if the script raised; None on success.",
    )
