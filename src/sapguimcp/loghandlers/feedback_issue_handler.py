"""Log handler that creates GitHub issues from feedback entries."""

import asyncio
import logging
import re
import threading
from datetime import datetime, timezone

import httpx

_logger = logging.getLogger(__name__)


class FeedbackIssueHandler(logging.Handler):
    """
    Handler that creates GitHub issues from FEEDBACK log entries.

    - Buffers feedback per session
    - Bundles entries with same tags into single issues
    - Rate limit: max 1 issue per 60 seconds per session
    - Rate limit resets on new session
    - GitHub API calls run in background threads (non-blocking)
    """

    # Pattern to parse FEEDBACK log messages
    _FEEDBACK_PATTERN = re.compile(
        r"FEEDBACK \| session=(?P<session_id>\S+) \| entry_id=(?P<entry_id>\S+) \| "
        r"(?P<feedback>.+?) \| tags=\[(?P<tags>.*)\]$"
    )

    def __init__(
        self,
        pat: str,
        repo: str,
        rate_limit_seconds: int = 60,
    ) -> None:
        """
        Initialize the handler.

        Args:
            pat: GitHub Personal Access Token
            repo: GitHub repository (format: owner/repo)
            rate_limit_seconds: Minimum seconds between issues per session
        """
        super().__init__()
        self.pat = pat
        self.repo = repo
        self.rate_limit_seconds = rate_limit_seconds

        # Per-session state
        self._buffers: dict[str, list[dict[str, str | list[str]]]] = {}
        self._last_issue_time: dict[str, datetime] = {}
        self._lock = threading.Lock()

        # Track last issue result for reporting back
        self._last_result: dict[str, dict[str, str | bool | None]] = {}

    def get_last_result(self, session_id: str) -> dict[str, str | bool | None]:
        """Get the last issue creation result for a session."""
        with self._lock:
            return self._last_result.get(
                session_id,
                {"issue_created": False, "issue_url": None, "issue_error": None},
            )

    def emit(self, record: logging.LogRecord) -> None:
        """Buffer FEEDBACK entries, flush when rate limit allows."""
        message = record.getMessage()
        if not message.startswith("FEEDBACK |"):
            return

        match = self._FEEDBACK_PATTERN.match(message)
        if not match:
            return

        session_id = match.group("session_id")
        entry_id = match.group("entry_id")
        feedback = match.group("feedback")
        tags_str = match.group("tags")
        tags = [t.strip() for t in tags_str.split(",")] if tags_str else []

        entry = {
            "entry_id": entry_id,
            "feedback": feedback,
            "tags": tags,
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        }

        with self._lock:
            self._buffers.setdefault(session_id, []).append(entry)

            if self._can_flush(session_id):
                self._flush_session(session_id)

    def _can_flush(self, session_id: str) -> bool:
        """Check if rate limit allows flushing."""
        last = self._last_issue_time.get(session_id)
        if last is None:
            return True
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= self.rate_limit_seconds

    def _flush_session(self, session_id: str) -> None:
        """Bundle buffered entries by tags and create issues in background."""
        entries = self._buffers.pop(session_id, [])
        if not entries:
            return

        # Group by frozenset of tags
        groups: dict[frozenset[str], list[dict[str, str | list[str]]]] = {}
        for entry in entries:
            tags = entry.get("tags", [])
            if isinstance(tags, list):
                key = frozenset(tags)
            else:
                key = frozenset()
            groups.setdefault(key, []).append(entry)

        # Update last issue time immediately to prevent duplicate flushes
        self._last_issue_time[session_id] = datetime.now(timezone.utc)

        # Create issues in background thread (non-blocking)
        for tag_set, group_entries in groups.items():
            thread = threading.Thread(
                target=self._create_bundled_issue_sync,
                args=(session_id, sorted(tag_set), group_entries),
                daemon=True,
            )
            thread.start()

    def _build_issue_title(
        self,
        entries: list[dict[str, str | list[str]]],
        tags: list[str],
    ) -> str:
        """Build the issue title from entries and tags."""
        if len(entries) == 1:
            feedback = str(entries[0].get("feedback", ""))
            if len(feedback) > 60:
                return f"Feedback: {feedback[:60]}..."
            return f"Feedback: {feedback}"
        tags_display = ", ".join(tags) if tags else "(no tags)"
        return f"Feedback ({len(entries)} entries): {tags_display}"

    def _build_issue_body(
        self,
        session_id: str,
        entries: list[dict[str, str | list[str]]],
    ) -> str:
        """Build the issue body from session and entries."""
        parts = [f"**Session**: `{session_id}`\n"]
        for i, entry in enumerate(entries, 1):
            entry_tags = entry.get("tags", [])
            tags_str = ", ".join(entry_tags) if isinstance(entry_tags, list) and entry_tags else "(none)"
            parts.append(
                f"## Entry {i} - {entry.get('timestamp', 'unknown')}\n\n"
                f"{entry.get('feedback', '')}\n\n"
                f"**Tags**: {tags_str}\n"
            )
        return "\n".join(parts)

    def _create_bundled_issue_sync(
        self,
        session_id: str,
        tags: list[str],
        entries: list[dict[str, str | list[str]]],
    ) -> None:
        """Synchronous wrapper to run async issue creation in background thread."""
        asyncio.run(self._create_bundled_issue(session_id, tags, entries))

    async def _create_bundled_issue(
        self,
        session_id: str,
        tags: list[str],
        entries: list[dict[str, str | list[str]]],
    ) -> None:
        """Create a single GitHub issue from bundled entries."""
        title = self._build_issue_title(entries, tags)
        body = self._build_issue_body(session_id, entries)
        issue_url, error = await self._create_github_issue(title, body)

        with self._lock:
            self._last_result[session_id] = {
                "issue_created": issue_url is not None,
                "issue_url": issue_url,
                "issue_error": error,
            }

        if issue_url:
            _logger.info("Created GitHub issue: %s", issue_url)
        elif error:
            _logger.warning("Failed to create GitHub issue: %s", error)

    async def _ensure_label_exists(self, client: httpx.AsyncClient, headers: dict[str, str]) -> None:
        """Ensure the model-feedback label exists, create if not."""
        label_url = f"https://api.github.com/repos/{self.repo}/labels/model-feedback"

        # Check if label exists
        response = await client.get(label_url, headers=headers)
        if response.status_code == 200:
            return  # Label exists

        # Create the label
        create_url = f"https://api.github.com/repos/{self.repo}/labels"
        payload = {
            "name": "model-feedback",
            "color": "d4c5f9",  # Light purple
            "description": "Feedback from AI model about tooling improvements",
        }
        await client.post(create_url, headers=headers, json=payload)
        # Ignore errors - label creation may fail if user lacks permissions

    async def _create_github_issue(
        self,
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
            "Authorization": f"Bearer {self.pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Ensure label exists before creating issue
                await self._ensure_label_exists(client, headers)

                url = f"https://api.github.com/repos/{self.repo}/issues"
                payload = {
                    "title": title,
                    "body": body,
                    "labels": ["model-feedback"],
                }
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code == 201:
                    return response.json().get("html_url"), None
                return None, f"GitHub API error: {response.status_code}"
        except httpx.RequestError as e:
            return None, f"Request failed: {e}"
