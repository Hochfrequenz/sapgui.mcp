"""Shared type definitions for the backend abstraction layer."""

from __future__ import annotations

from pydantic import Field

from sapwebguimcp.models.base import ToolResult


class CheckActivateResult(ToolResult):
    """Result of a check-and-activate editor operation."""

    messages: list[str] = Field(
        default_factory=list,
        description="Check and activate status messages",
    )
    activated: bool = Field(
        default=False,
        description="Whether the object was successfully activated",
    )
