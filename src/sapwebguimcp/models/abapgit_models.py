"""
Pydantic models for abapGit tool results.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AbapGitRepo(BaseModel):
    """Information about an abapGit repository."""

    name: str = Field(description="Repository name")
    package: str | None = Field(default=None, description="SAP package")
    remote_url: str | None = Field(default=None, description="Remote git URL")
    branch: str | None = Field(default=None, description="Current branch")


class AbapGitPullResult(BaseModel):
    """Result of an abapGit pull operation."""

    success: bool = Field(description="Whether the pull succeeded")
    repo_name: str = Field(description="Name of the repository that was pulled")
    message: str | None = Field(default=None, description="Status message")
    error: str | None = Field(default=None, description="Error message if failed")
    pulled_at: datetime = Field(description="When the pull was executed")


class AbapGitStageResult(BaseModel):
    """Result of an abapGit stage operation."""

    success: bool = Field(description="Whether navigating to stage succeeded")
    repo_name: str = Field(description="Name of the repository")
    message: str | None = Field(default=None, description="Status message")
    error: str | None = Field(default=None, description="Error message if failed")
    staged_at: datetime = Field(description="When the stage was initiated")


class AbapGitRepoListResult(BaseModel):
    """Result of listing abapGit repositories."""

    success: bool = Field(description="Whether the list operation succeeded")
    repos: list[AbapGitRepo] = Field(default_factory=list, description="List of repos")
    error: str | None = Field(default=None, description="Error message if failed")
    retrieved_at: datetime = Field(description="When the list was retrieved")


class AbapGitActionResult(BaseModel):
    """Generic result for abapGit actions."""

    success: bool = Field(description="Whether the action succeeded")
    action: Literal["pull", "stage", "diff", "check"] = Field(description="Action type")
    repo_name: str = Field(description="Repository name")
    message: str | None = Field(default=None, description="Status message")
    error: str | None = Field(default=None, description="Error message if failed")
    executed_at: datetime = Field(description="When the action was executed")
