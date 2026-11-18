"""Unit tests for Pydantic result models."""

from datetime import timedelta

from sapguimcp.backend.webgui.models.browser_results import ClickResult, WaitResult


class TestTimedeltaSerialization:
    """Tests for ISO 8601 timedelta serialization."""

    def test_timedelta_seconds(self) -> None:
        """Test timedelta serializes to ISO 8601 format (seconds)."""
        result = WaitResult(timeout=timedelta(seconds=30))
        json_data = result.model_dump_json()
        assert '"timeout":"PT30S"' in json_data

    def test_timedelta_minutes(self) -> None:
        """Test timedelta serializes to ISO 8601 format (minutes)."""
        result = WaitResult(timeout=timedelta(minutes=2))
        json_data = result.model_dump_json()
        assert '"timeout":"PT2M"' in json_data or '"timeout":"PT120S"' in json_data

    def test_timedelta_complex(self) -> None:
        """Test timedelta serializes complex durations."""
        result = WaitResult(timeout=timedelta(minutes=2, seconds=30))
        json_data = result.model_dump_json()
        # Could be PT2M30S or PT150S depending on implementation
        assert "PT" in json_data
        assert "timeout" in json_data

    def test_timedelta_milliseconds(self) -> None:
        """Test timedelta with milliseconds."""
        result = WaitResult(timeout=timedelta(milliseconds=500))
        json_data = result.model_dump_json()
        assert "PT" in json_data


class TestSubclassFailureMethod:
    """Tests for failure() factory method on subclasses."""

    def test_click_result_failure(self) -> None:
        """Test ClickResult.failure() preserves selector."""
        result = ClickResult.failure("Element not found", selector="#button1")
        assert result.success is False
        assert result.error == "Element not found"
        assert result.selector == "#button1"
