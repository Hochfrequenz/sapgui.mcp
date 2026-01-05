"""
Feedback logging tools for model observations.

This module provides the log_feedback tool for models to document
patterns, friction points, and optimization opportunities.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastmcp import Context, FastMCP

from sapwebguimcp.models import FeedbackEntry, FeedbackLogResult
from sapwebguimcp.models.config import get_settings

__all__ = ["register_feedback_tools", "get_session_feedback", "clear_session_feedback"]

_logger = logging.getLogger(__name__)

# In-memory store for feedback entries per session
_session_feedback: dict[str, list[FeedbackEntry]] = {}


def get_session_feedback(session_id: str) -> list[FeedbackEntry]:
    """Get all feedback entries for a session."""
    return _session_feedback.get(session_id, [])


def clear_session_feedback(session_id: str) -> None:
    """Clear feedback entries for a session."""
    _session_feedback.pop(session_id, None)


async def _create_github_issue(
    pat: str,
    repo: str,
    title: str,
    body: str,
) -> tuple[str | None, str | None]:
    """
    Create a GitHub issue via REST API (async).

    Returns:
        (issue_url, None) on success
        (None, error_message) on failure
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if label exists, create if not
            label_url = f"https://api.github.com/repos/{repo}/labels/model-feedback"
            response = await client.get(label_url, headers=headers)
            if response.status_code != 200:
                # Create the label
                create_url = f"https://api.github.com/repos/{repo}/labels"
                payload = {
                    "name": "model-feedback",
                    "color": "d4c5f9",  # Light purple
                    "description": "Feedback from AI model about tooling improvements",
                }
                await client.post(create_url, headers=headers, json=payload)

            # Create the issue
            url = f"https://api.github.com/repos/{repo}/issues"
            issue_payload: dict[str, str | list[str]] = {
                "title": title,
                "body": body,
                "labels": ["model-feedback"],
            }
            response = await client.post(url, headers=headers, json=issue_payload)
            if response.status_code == 201:
                return response.json().get("html_url"), None
            return None, f"GitHub API error: {response.status_code} - {response.text}"
    except httpx.RequestError as e:
        return None, f"Request failed: {e}"


async def _create_issue_background(pat: str, repo: str, title: str, body: str) -> None:
    """Background task to create GitHub issue and log result."""
    issue_url, issue_error = await _create_github_issue(pat, repo, title, body)
    if issue_url:
        _logger.info("Created GitHub issue: %s", issue_url)
    elif issue_error:
        _logger.warning("Failed to create GitHub issue: %s", issue_error)


def register_feedback_tools(mcp: FastMCP) -> None:
    """Register feedback logging tools with the MCP server."""

    @mcp.tool(
        description=(
            "Log technical feedback about tool usage patterns, friction points, "
            "or optimization opportunities. ENCOURAGED whenever you notice something "
            "that could improve tooling. If GITHUB_PAT configured, auto-posts as GitHub issue. "
            "BE DETAILED: include transaction code, steps to reproduce, tool names, selectors, "
            "timing observations, what you tried, error messages. "
            "TAGS: 'tool-combination' (tools always used together), 'repetition' (same tool repeated), "
            "'selector' (hard to find), 'timing' (slow/timeout), 'workflow' (could be simplified), "
            "'missing-tool', 'error-handling', 'deadlock' (got stuck), 'problem' (blocked progress). "
            "Use markdown formatting: `backticks` for code, **bold** for emphasis."
        )
    )
    async def log_feedback(  # pylint: disable=missing-function-docstring
        feedback: str,
        tags: list[str] | None = None,
        ctx: Context | None = None,
    ) -> FeedbackLogResult:
        session_id = getattr(ctx, "session_id", None) if ctx else None
        session_key = session_id or "unknown"

        entry = FeedbackEntry(
            timestamp=datetime.now(timezone.utc),
            session_id=session_key,
            feedback=feedback,
            tags=tags or [],
        )

        # Store in memory
        if session_key not in _session_feedback:
            _session_feedback[session_key] = []
        _session_feedback[session_key].append(entry)

        # Log for audit trail
        tags_str = ", ".join(tags) if tags else ""
        _logger.info(
            "FEEDBACK | session=%s | entry_id=%s | %s | tags=[%s]",
            session_key,
            entry.entry_id,
            feedback,
            tags_str,
        )

        # Create GitHub issue in background if PAT is configured
        settings = get_settings()
        issue_pending = False

        if settings.github_pat:
            # Build issue title and body
            title = feedback[:60] + "..." if len(feedback) > 60 else feedback
            title = f"Feedback: {title}"

            tags_display = ", ".join(tags) if tags else "(none)"
            body = (
                f"**Session**: `{session_key}`\n\n"
                f"## Feedback\n\n{feedback}\n\n"
                f"**Tags**: {tags_display}\n\n"
                f"**Timestamp**: {entry.timestamp.isoformat()}\n"  # pylint: disable=no-member
            )

            # Fire and forget - create issue in background
            asyncio.create_task(
                _create_issue_background(
                    pat=settings.github_pat,
                    repo=settings.github_repo,
                    title=title,
                    body=body,
                )
            )
            issue_pending = True
            _logger.debug("GitHub issue creation started in background")

        return FeedbackLogResult(
            logged=True,
            entry_id=entry.entry_id,
            session_id=session_key,
            issue_created=issue_pending,  # True means "creation started"
            issue_url=None,  # Not available immediately (background task)
            issue_error=None,
        )
