"""
Pydantic models for abapGit tool results.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class AbapGitActionResult(BaseModel):
    """
    Result for abapGit actions (pull, stage, diff, check).

    Use factory methods for consistent creation:
        AbapGitActionResult.success("pull", "repo", "message")
        AbapGitActionResult.failure("pull", "repo", "error")
    """

    success: bool = Field(description="Whether the action succeeded")
    action: Literal["pull", "stage", "diff", "check"] = Field(description="Action type")
    repo_name: str = Field(description="Repository name")
    message: str | None = Field(default=None, description="Status message")
    error: str | None = Field(default=None, description="Error message if failed")
    executed_at: datetime = Field(description="When the action was executed")
    clicked_action: str | None = Field(
        default=None,
        description="The action button text that was clicked (e.g., 'Pull', 'Stage')",
    )

    @classmethod
    def success_result(
        cls,
        action: Literal["pull", "stage", "diff", "check"],
        repo_name: str,
        message: str,
        clicked_action: str | None = None,
    ) -> "AbapGitActionResult":
        """Create a success result."""
        return cls(
            success=True,
            action=action,
            repo_name=repo_name,
            message=message,
            executed_at=datetime.now(UTC),
            clicked_action=clicked_action,
        )

    @classmethod
    def failure_result(
        cls,
        action: Literal["pull", "stage", "diff", "check"],
        repo_name: str,
        error: str,
        clicked_action: str | None = None,
    ) -> "AbapGitActionResult":
        """Create a failure result."""
        return cls(
            success=False,
            action=action,
            repo_name=repo_name,
            error=error,
            executed_at=datetime.now(UTC),
            clicked_action=clicked_action,
        )
