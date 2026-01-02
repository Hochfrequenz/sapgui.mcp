"""Base model for MCP tool results with standardized error handling."""

from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

# Transaction code type: uppercase A-Z, 0-9, underscore, slash
# BeforeValidator normalizes to uppercase before pattern validation
TCODE_PATTERN = r"^[A-Z0-9_/]+$"
TCode = Annotated[str, BeforeValidator(str.upper), Field(pattern=TCODE_PATTERN)]


class ToolResult(BaseModel):
    """Base class for all MCP tool results with standardized error handling.

    Per MCP spec, tool errors should be reported within the result object,
    not as protocol-level errors. This allows the LLM to observe and handle errors.

    Invariants enforced by validation:
    - success=True → error must be None
    - success=False → error must be non-empty string
    """

    model_config = ConfigDict(
        extra="allow",
        ser_json_timedelta="iso8601",
    )

    success: bool = Field(default=True, description="Whether the operation succeeded")
    error: str | None = Field(default=None, description="Error message if success=False")

    @model_validator(mode="after")
    def validate_success_error_consistency(self) -> Self:
        """Enforce that success and error are consistent."""
        if self.success and self.error is not None:
            raise ValueError("success=True requires error=None")
        if not self.success and not self.error:
            raise ValueError("success=False requires non-empty error message")
        return self

    @property
    def is_error(self) -> bool:
        """Convenience property matching MCP's isError convention."""
        return not self.success

    @classmethod
    def failure(cls, error: str, **kwargs):
        """Factory method to create a failed result."""
        return cls(success=False, error=error, **kwargs)
