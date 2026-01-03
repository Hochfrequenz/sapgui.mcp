"""Models for intent logging."""

from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field

from sapwebguimcp.models.base import ToolResult


class IntentEntry(BaseModel):
    """A single intent log entry."""

    timestamp: AwareDatetime = Field(description="When the intent was logged")
    session_id: str = Field(description="Session ID")
    intent: str = Field(description="High-level description of the intent")
    context: dict[str, str] = Field(
        default_factory=dict,
        description="Optional context like tcode, document_id",
    )
    entry_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID for this entry",
    )


class IntentLogResult(ToolResult):
    """Result from log_intent tool."""

    logged: bool = Field(description="Whether the entry was recorded")
    entry_id: str | None = Field(default=None, description="UUID of the entry")
    session_id: str | None = Field(default=None, description="Session ID for resource access")
