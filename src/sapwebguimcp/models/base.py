"""Base model for MCP tool results with standardized error handling."""

from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

# Transaction code type: uppercase A-Z, 0-9, underscore, slash
# BeforeValidator normalizes to uppercase before pattern validation
TCODE_PATTERN = r"^[A-Z0-9_/]+$"
TCode = Annotated[str, BeforeValidator(str.upper), Field(pattern=TCODE_PATTERN)]


class PopupType(StrEnum):
    """Type of popup dialog."""

    HELP = "help"  # F4 search help, value lists
    CONFIRM = "confirm"  # Yes/No decisions
    ERROR = "error"  # Validation errors, warnings
    INFO = "info"  # Informational messages
    UNKNOWN = "unknown"  # Can't determine (default)


class PopupButton(BaseModel):
    """A button in a popup dialog."""

    label: str = Field(description="Button text (e.g., 'Ja', 'Nein', 'Abbrechen')")
    accesskey: str | None = Field(default=None, description="Keyboard shortcut (e.g., 'J', 'N')")
    id: str | None = Field(default=None, description="Button element ID for clicking")


class PopupInfo(BaseModel):
    """Info about an active popup dialog."""

    popup_type: PopupType = Field(
        default=PopupType.UNKNOWN,
        description="Type of popup if detectable: help, confirm, error, info, or unknown",
    )
    message: str | None = Field(default=None, description="Popup message text")
    buttons: list[PopupButton] = Field(default_factory=list, description="Available buttons")
    close_button_id: str | None = Field(default=None, description="ID of X close button if present")

    @property
    def has_close_button(self) -> bool:
        """Whether the popup has an X close button."""
        return self.close_button_id is not None


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
    popup: PopupInfo | None = Field(
        default=None,
        description="Present when a popup dialog is active on screen",
    )

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
    def failure(cls, error: str, **kwargs: Any) -> Self:
        """Factory method to create a failed result."""
        return cls(success=False, error=error, **kwargs)
