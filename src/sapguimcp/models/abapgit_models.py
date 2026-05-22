"""
Pydantic models for abapGit tool results.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from sapguimcp.models.base import ToolResult


class AbapGitRepoInfo(BaseModel):
    """Metadata for a single registered abapGit repository."""

    name: str = Field(description="Repository name in SAP (e.g. Z_MY_REPO)")
    url: str = Field(description="Remote Git URL")
    package: str = Field(description="ABAP development package (devclass)")
    branch: str = Field(description="Git branch name (e.g. refs/heads/main)")
    last_pull_at: str | None = Field(default=None, description="Last pull timestamp (ABAP TIMESTAMPL type)")
    last_pull_by: str | None = Field(default=None, description="SAP user who last pulled")
    is_offline: bool = Field(default=False, description="Whether this is an offline repo")


class AbapGitListResult(ToolResult):
    """Result of listing registered abapGit repositories."""

    repos: list[AbapGitRepoInfo] = Field(default_factory=list, description="Registered repositories")


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
