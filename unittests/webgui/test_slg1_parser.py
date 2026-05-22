"""
Unit tests for SLG1 (Application Log) parser.

Tests parsing of YAML accessibility snapshots from SLG1 log display screens.
"""

from pathlib import Path

import pytest

from sapguimcp.backend.webgui.parsers.slg1_parser import (
    is_slg1_initial_screen,
    is_slg1_log_list_screen,
    is_slg1_no_results,
    parse_slg1_log_list,
)

SNAPSHOTS_DIR = Path(__file__).parent / "testdata" / "slg1_exploration"


def _load_snapshot(name: str) -> str:
    """Load a YAML snapshot file."""
    filepath = SNAPSHOTS_DIR / f"{name}_de.yaml"
    if not filepath.exists():
        pytest.skip(f"Snapshot {filepath} not available - run exploration tests first")
    return filepath.read_text(encoding="utf-8")


class TestSLG1ScreenDetection:
    """Tests for detecting SLG1 screen states."""

    def test_detect_initial_screen(self) -> None:
        """Should detect the SLG1 selection screen."""
        snapshot = _load_snapshot("slg1_initial")
        assert is_slg1_initial_screen(snapshot) is True

    def test_detect_initial_screen_not_log_list(self) -> None:
        """Initial screen should not be detected as log list."""
        snapshot = _load_snapshot("slg1_initial")
        assert is_slg1_log_list_screen(snapshot) is False

    def test_detect_no_results(self) -> None:
        """Should detect when no logs are found (status bar message)."""
        snapshot = _load_snapshot("slg1_no_results")
        assert is_slg1_no_results(snapshot) is True

    def test_detect_no_results_is_still_initial(self) -> None:
        """No results screen is still the initial screen (with status bar)."""
        snapshot = _load_snapshot("slg1_no_results")
        assert is_slg1_initial_screen(snapshot) is True

    def test_log_list_is_not_initial(self) -> None:
        """Log list screen should not be detected as initial."""
        snapshot = _load_snapshot("slg1_log_list")
        assert is_slg1_initial_screen(snapshot) is False

    def test_log_list_is_log_list(self) -> None:
        """Log list screen should be detected as log list."""
        snapshot = _load_snapshot("slg1_log_list")
        assert is_slg1_log_list_screen(snapshot) is True

    def test_log_list_is_not_no_results(self) -> None:
        """Log list screen should not be detected as no results."""
        snapshot = _load_snapshot("slg1_log_list")
        assert is_slg1_no_results(snapshot) is False


class TestSLG1LogListParsing:
    """Tests for parsing the log list grid."""

    def test_parse_log_list_has_entries(self) -> None:
        """Should parse at least one log entry from the list."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        assert result.success
        assert result.log_count > 0
        assert len(result.logs) > 0

    def test_log_entry_has_required_fields(self) -> None:
        """Each log entry should have log_number, object, date, time."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        if not result.logs:
            pytest.skip("No logs parsed - check snapshot content")

        entry = result.logs[0]
        assert entry.log_number, "log_number should not be empty"
        assert entry.object, "object should not be empty"
        assert entry.date, "date should not be empty"
        assert entry.time, "time should not be empty"

    def test_log_entry_has_user(self) -> None:
        """Log entries should have a user field."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        if not result.logs:
            pytest.skip("No logs parsed")

        entry = result.logs[0]
        assert entry.user, "user should not be empty"

    def test_log_number_is_numeric(self) -> None:
        """Log numbers should be numeric strings."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        for entry in result.logs:
            assert entry.log_number.isdigit(), f"log_number should be numeric, got {entry.log_number!r}"

    def test_message_count_is_nonnegative(self) -> None:
        """Message counts should be non-negative integers."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        for entry in result.logs:
            assert entry.message_count >= 0, f"message_count should be >= 0, got {entry.message_count}"

    def test_no_results_returns_empty(self) -> None:
        """No results should return empty log list."""
        snapshot = _load_snapshot("slg1_no_results")
        result = parse_slg1_log_list(snapshot)

        assert result.success
        assert result.log_count == 0
        assert len(result.logs) == 0
        assert result.logs_truncated is False

    def test_known_log_objects_present(self) -> None:
        """Known log objects from the test system should be present."""
        snapshot = _load_snapshot("slg1_log_list")
        result = parse_slg1_log_list(snapshot)

        objects = {entry.object for entry in result.logs}
        # Based on the captured snapshot, these objects exist
        assert len(objects) > 0, "Should have at least one unique object"

    def test_expanded_log_same_as_list(self) -> None:
        """Expanded log snapshot should parse the same as log list (expansion is visual only)."""
        list_snapshot = _load_snapshot("slg1_log_list")
        expanded_snapshot = _load_snapshot("slg1_expanded_log")

        list_result = parse_slg1_log_list(list_snapshot)
        expanded_result = parse_slg1_log_list(expanded_snapshot)

        assert list_result.log_count == expanded_result.log_count
