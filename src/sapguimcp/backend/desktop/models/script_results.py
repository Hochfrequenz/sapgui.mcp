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

    version: int = Field(default=1, description="Version of the sandbox contract.")
    allowed_builtins: list[str] = Field(
        description="Names of built-in functions and types available in the sandbox.",
    )
    safe_builtins: list[str] = Field(
        description="Alias for allowed_builtins matching SAFE_BUILTINS.",
    )
    injected_names: list[str] = Field(
        description="Global names injected into the script execution environment.",
    )

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError as err:
            raise KeyError(item) from err

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str) and hasattr(self, item)

    def keys(self) -> list[str]:
        return list(self.model_fields.keys())

    def items(self) -> list[tuple[str, Any]]:
        return [(k, getattr(self, k)) for k in self.model_fields]

    def values(self) -> list[Any]:
        return [getattr(self, k) for k in self.model_fields]
