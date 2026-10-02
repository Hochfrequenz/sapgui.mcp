"""Pydantic model for sap_run_script tool results."""

from typing import Any

from pydantic import BaseModel, Field

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


class SandboxContract(BaseModel):
    """Sandbox execution contract for sap_run_script."""

    version: int = Field(description="Version of the sandbox contract (see SANDBOX_CONTRACT_VERSION).")
    allowed_builtins: list[str] = Field(
        description="Names of built-in functions and types available in the sandbox.",
    )
    injected_names: list[str] = Field(
        description="Global names injected into the script execution environment.",
    )
