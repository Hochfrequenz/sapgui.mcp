"""Tests for the FeedbackIssueHandler."""

import json
import logging
import time
from datetime import datetime, timezone
from unittest.mock import patch

import httpx
import pytest
import respx

from sapguimcp.loghandlers.feedback_issue_handler import FeedbackIssueHandler


class TestFeedbackIssueHandler:
    """Tests for FeedbackIssueHandler."""

    def test_ignores_non_feedback_messages(self) -> None:
        """Test that non-FEEDBACK messages are ignored."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="INTENT | session=abc | entry_id=123 | some intent | context={}",
            args=(),
            exc_info=None,
        )

        # Non-feedback messages should not trigger any buffer activity
        handler.emit(record)
        assert "abc" not in handler._buffers

    def test_parses_feedback_message(self) -> None:
        """Test that FEEDBACK messages are parsed and buffered."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess123 | entry_id=entry456 | Test feedback | tags=[tag1, tag2]",
            args=(),
            exc_info=None,
        )

        # Prevent actual flush by setting a recent last_issue_time
        handler._last_issue_time["sess123"] = datetime.now(timezone.utc)

        handler.emit(record)

        assert "sess123" in handler._buffers
        assert len(handler._buffers["sess123"]) == 1
        entry = handler._buffers["sess123"][0]
        assert entry["feedback"] == "Test feedback"
        assert entry["tags"] == ["tag1", "tag2"]
        assert entry["entry_id"] == "entry456"

    def test_parses_empty_tags(self) -> None:
        """Test parsing of FEEDBACK message with no tags."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess123 | entry_id=entry456 | No tags here | tags=[]",
            args=(),
            exc_info=None,
        )

        handler._last_issue_time["sess123"] = datetime.now(timezone.utc)

        handler.emit(record)

        entry = handler._buffers["sess123"][0]
        assert entry["tags"] == []

    def test_flushes_on_first_message(self) -> None:
        """Test that first message triggers immediate flush."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess123 | entry_id=entry456 | First feedback | tags=[]",
            args=(),
            exc_info=None,
        )

        # Mock the sync wrapper to avoid actual HTTP calls
        with patch.object(handler, "_create_bundled_issue_sync") as mock_sync:
            handler.emit(record)

            # Buffer should be empty after flush
            assert "sess123" not in handler._buffers

            # Wait for thread to start
            time.sleep(0.1)
            mock_sync.assert_called_once()

    def test_rate_limiting(self) -> None:
        """Test that rate limiting prevents immediate flush."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo", rate_limit_seconds=60)

        # First message triggers flush
        record1 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess123 | entry_id=entry1 | First | tags=[]",
            args=(),
            exc_info=None,
        )

        with patch.object(handler, "_create_bundled_issue_sync") as mock_sync:
            handler.emit(record1)
            time.sleep(0.1)
            assert mock_sync.call_count == 1

            # Second message should be buffered (rate limited)
            record2 = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="FEEDBACK | session=sess123 | entry_id=entry2 | Second | tags=[]",
                args=(),
                exc_info=None,
            )
            handler.emit(record2)

            # Should still be 1 call (second was buffered)
            time.sleep(0.1)
            assert mock_sync.call_count == 1
            # Should be buffered
            assert len(handler._buffers.get("sess123", [])) == 1

    def test_different_sessions_independent(self) -> None:
        """Test that different sessions have independent rate limits."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo", rate_limit_seconds=60)

        record1 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess1 | entry_id=entry1 | First | tags=[]",
            args=(),
            exc_info=None,
        )

        record2 = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess2 | entry_id=entry2 | Second | tags=[]",
            args=(),
            exc_info=None,
        )

        with patch.object(handler, "_create_bundled_issue_sync") as mock_sync:
            handler.emit(record1)
            handler.emit(record2)

            # Wait for background threads
            time.sleep(0.2)

            # Both should trigger flush (different sessions)
            assert mock_sync.call_count == 2

    def test_bundling_by_tags(self) -> None:
        """Test that entries with same tags are bundled."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo", rate_limit_seconds=0)

        # Manually add entries with different tags
        handler._buffers["sess123"] = [
            {
                "entry_id": "e1",
                "feedback": "Feedback 1",
                "tags": ["tag1"],
                "timestamp": "2024-01-01T00:00:00Z",
            },
            {
                "entry_id": "e2",
                "feedback": "Feedback 2",
                "tags": ["tag1"],
                "timestamp": "2024-01-01T00:01:00Z",
            },
            {
                "entry_id": "e3",
                "feedback": "Feedback 3",
                "tags": ["tag2"],
                "timestamp": "2024-01-01T00:02:00Z",
            },
        ]

        with patch.object(handler, "_create_bundled_issue_sync") as mock_sync:
            handler._flush_session("sess123")

            # Wait for background threads
            time.sleep(0.2)

            # Should create 2 issues (one for tag1, one for tag2)
            assert mock_sync.call_count == 2

    @respx.mock
    @pytest.mark.anyio
    async def test_successful_issue_creation(self) -> None:
        """Test successful GitHub issue creation."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        # Mock label check (label exists)
        label_route = respx.get("https://api.github.com/repos/owner/repo/labels/model-feedback").mock(
            return_value=httpx.Response(200)
        )

        # Mock issue creation
        issue_route = respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"html_url": "https://github.com/owner/repo/issues/42"})
        )

        url, error = await handler._create_github_issue("Test Title", "Test Body")

        assert url == "https://github.com/owner/repo/issues/42"
        assert error is None

        # Verify label check was called
        assert label_route.call_count == 1

        # Verify issue creation API call
        assert issue_route.call_count == 1
        request = issue_route.calls[0].request
        assert str(request.url) == "https://api.github.com/repos/owner/repo/issues"

    @respx.mock
    @pytest.mark.anyio
    async def test_api_error_handling(self) -> None:
        """Test handling of GitHub API errors."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        # Mock label check (label exists)
        respx.get("https://api.github.com/repos/owner/repo/labels/model-feedback").mock(
            return_value=httpx.Response(200)
        )

        # Mock issue creation failure
        respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(401, text="Bad credentials")
        )

        url, error = await handler._create_github_issue("Test Title", "Test Body")

        assert url is None
        assert "401" in error

    @respx.mock
    @pytest.mark.anyio
    async def test_network_error_handling(self) -> None:
        """Test handling of network errors."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        # Network error on label check
        respx.get("https://api.github.com/repos/owner/repo/labels/model-feedback").mock(
            side_effect=httpx.RequestError("Connection timeout")
        )

        url, error = await handler._create_github_issue("Test Title", "Test Body")

        assert url is None
        assert "Request failed" in error

    def test_get_last_result_default(self) -> None:
        """Test get_last_result returns default when no result exists."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        result = handler.get_last_result("unknown-session")

        assert result["issue_created"] is False
        assert result["issue_url"] is None
        assert result["issue_error"] is None

    @respx.mock
    @pytest.mark.anyio
    async def test_get_last_result_after_success(self) -> None:
        """Test get_last_result returns correct values after successful issue creation."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        # Mock label check (label exists)
        respx.get("https://api.github.com/repos/owner/repo/labels/model-feedback").mock(
            return_value=httpx.Response(200)
        )

        # Mock issue creation
        respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"html_url": "https://github.com/owner/repo/issues/99"})
        )

        # Test async method directly
        await handler._create_bundled_issue(
            "sess123",
            [],
            [{"entry_id": "e1", "feedback": "Test", "tags": [], "timestamp": "2024-01-01T00:00:00Z"}],
        )

        result = handler.get_last_result("sess123")
        assert result["issue_created"] is True
        assert result["issue_url"] == "https://github.com/owner/repo/issues/99"
        assert result["issue_error"] is None

    def test_bundled_issue_title_single_entry(self) -> None:
        """Test issue title format for single entry."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        entries = [
            {
                "entry_id": "e1",
                "feedback": "Short feedback",
                "tags": [],
                "timestamp": "2024-01-01T00:00:00Z",
            },
        ]

        title = handler._build_issue_title(entries, [])
        assert title == "Feedback: Short feedback"

    def test_bundled_issue_title_long_feedback(self) -> None:
        """Test issue title truncation for long feedback."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        long_feedback = "A" * 100  # 100 characters

        entries = [
            {
                "entry_id": "e1",
                "feedback": long_feedback,
                "tags": [],
                "timestamp": "2024-01-01T00:00:00Z",
            },
        ]

        title = handler._build_issue_title(entries, [])
        assert len(title) <= 75  # "Feedback: " + 60 chars + "..."
        assert title.endswith("...")

    def test_bundled_issue_title_multiple_entries(self) -> None:
        """Test issue title format for multiple entries."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        entries = [
            {
                "entry_id": "e1",
                "feedback": "Feedback 1",
                "tags": ["timing", "selector"],
                "timestamp": "2024-01-01T00:00:00Z",
            },
            {
                "entry_id": "e2",
                "feedback": "Feedback 2",
                "tags": ["timing", "selector"],
                "timestamp": "2024-01-01T00:01:00Z",
            },
        ]

        title = handler._build_issue_title(entries, ["selector", "timing"])
        assert "2 entries" in title
        # Tags should be in title
        assert "selector" in title
        assert "timing" in title

    @respx.mock
    @pytest.mark.anyio
    async def test_label_creation_when_missing(self) -> None:
        """Test that label is created when it doesn't exist."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        # Mock label check (label doesn't exist - 404)
        respx.get("https://api.github.com/repos/owner/repo/labels/model-feedback").mock(
            return_value=httpx.Response(404)
        )

        # Mock label creation
        label_create_route = respx.post("https://api.github.com/repos/owner/repo/labels").mock(
            return_value=httpx.Response(201)
        )

        # Mock issue creation
        respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"html_url": "https://github.com/owner/repo/issues/1"})
        )

        url, error = await handler._create_github_issue("Test Title", "Test Body")

        assert url == "https://github.com/owner/repo/issues/1"
        assert error is None
        # Verify label creation was attempted
        assert label_create_route.call_count == 1

    def test_emit_is_non_blocking(self) -> None:
        """Test that emit() returns immediately (non-blocking)."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="FEEDBACK | session=sess123 | entry_id=entry1 | Test | tags=[]",
            args=(),
            exc_info=None,
        )

        # Mock the sync wrapper to avoid actual HTTP calls
        with patch.object(handler, "_create_bundled_issue_sync"):
            start = time.monotonic()
            handler.emit(record)
            elapsed = time.monotonic() - start

            # emit() should return quickly (it just queues, doesn't wait for HTTP)
            # Use 200ms threshold to avoid flaky tests on slow/loaded machines
            assert elapsed < 0.2, f"emit() took {elapsed:.3f}s, should be < 0.2s"

    @respx.mock
    @pytest.mark.anyio
    async def test_issue_body_format(self) -> None:
        """Test that issue body contains expected fields."""
        handler = FeedbackIssueHandler(pat="test-pat", repo="owner/repo")

        # Mock label check
        respx.get("https://api.github.com/repos/owner/repo/labels/model-feedback").mock(
            return_value=httpx.Response(200)
        )

        # Mock issue creation - capture the request
        issue_route = respx.post("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=httpx.Response(201, json={"html_url": "https://github.com/owner/repo/issues/1"})
        )

        await handler._create_github_issue("Test Title", "**Session**: `test-session`\n## Entry 1")

        request_body = json.loads(issue_route.calls[0].request.content)
        assert "**Session**" in request_body["body"]
        assert request_body["labels"] == ["model-feedback"]
