"""Models for intent and feedback logging."""

from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field

from sapguimcp.models.base import ToolResult


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


class FeedbackEntry(BaseModel):
    """A single feedback log entry for model observations."""

    timestamp: AwareDatetime = Field(description="When the feedback was logged")
    session_id: str = Field(description="Session ID")
    feedback: str = Field(description="The observation or learning")
    tags: list[str] = Field(
        default_factory=list,
        description="Optional tags for categorization",
    )
    entry_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique ID for this entry",
    )


class FeedbackLogResult(ToolResult):
    """Result from log_feedback tool."""

    logged: bool = Field(description="Whether the entry was recorded")
    entry_id: str | None = Field(default=None, description="UUID of the entry")
    session_id: str | None = Field(default=None, description="Session ID for resource access")
    # GitHub issue creation status (reflects previous flush due to buffering)
    issue_created: bool = Field(
        default=False,
        description="Whether a GitHub issue was created from buffered feedback",
    )
    issue_url: str | None = Field(
        default=None,
        description="URL of the created GitHub issue",
    )
    issue_error: str | None = Field(
        default=None,
        description="Error message if issue creation failed",
    )
