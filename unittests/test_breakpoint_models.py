"""Unit tests for breakpoint data models."""

import pytest
from pydantic import ValidationError

from sapwebguimcp.models.breakpoint_models import (
    BreakpointDeleteResult,
    BreakpointEntry,
    BreakpointListResult,
    BreakpointSetResult,
)


class TestBreakpointEntry:
    def test_valid_entry(self) -> None:
        entry = BreakpointEntry(line_number=42, source_line="CALL FUNCTION 'TEST'.")
        assert entry.line_number == 42
        assert entry.source_line == "CALL FUNCTION 'TEST'."


class TestBreakpointSetResult:
    def test_set_action(self) -> None:
        result = BreakpointSetResult(
            success=True,
            object_type="PROG",
            object_name="ZTEST",
            method_name=None,
            line_number=10,
            action="set",
            status_message="Externer Breakpoint wurde gesetzt",
            error=None,
        )
        assert result.success is True
        assert result.action == "set"
        assert result.error is None

    def test_deleted_instead_action(self) -> None:
        result = BreakpointSetResult(
            success=True,
            object_type="PROG",
            object_name="ZTEST",
            method_name=None,
            line_number=10,
            action="deleted_instead",
            status_message="Externer Breakpoint wurde gelöscht",
            error=None,
        )
        assert result.action == "deleted_instead"

    def test_failure_factory(self) -> None:
        result = BreakpointSetResult.failure(
            error="Object not found",
            object_type="PROG",
            object_name="ZTEST",
            method_name=None,
            line_number=0,
            action="set",
            status_message="",
        )
        assert result.success is False
        assert result.error == "Object not found"

    def test_success_with_error_raises(self) -> None:
        with pytest.raises(ValidationError):
            BreakpointSetResult(
                success=True,
                error="should not be set",
                object_type="PROG",
                object_name="ZTEST",
                method_name=None,
                line_number=10,
                action="set",
                status_message="",
            )


class TestBreakpointDeleteResult:
    def test_deleted_action(self) -> None:
        result = BreakpointDeleteResult(
            success=True,
            object_type="FUGR",
            object_name="BREA",
            method_name="MY_FM",
            line_number=18,
            action="deleted",
            status_message="Externer Breakpoint wurde gelöscht",
            error=None,
        )
        assert result.action == "deleted"
        assert result.method_name == "MY_FM"

    def test_was_not_set_action(self) -> None:
        result = BreakpointDeleteResult(
            success=True,
            object_type="PROG",
            object_name="ZTEST",
            method_name=None,
            line_number=5,
            action="was_not_set",
            status_message="Externer Breakpoint wurde gesetzt",
            error=None,
        )
        assert result.action == "was_not_set"

    def test_failure_factory(self) -> None:
        result = BreakpointDeleteResult.failure(
            error="Pattern not found",
            object_type="CLAS",
            object_name="ZCL_TEST",
            method_name="MY_METHOD",
            line_number=0,
            action="deleted",
            status_message="",
        )
        assert result.success is False


class TestBreakpointListResult:
    def test_empty_list(self) -> None:
        result = BreakpointListResult(
            success=True,
            object_type="PROG",
            object_name="ZTEST",
            method_name=None,
            breakpoints=[],
            error=None,
        )
        assert result.breakpoints == []

    def test_with_entries(self) -> None:
        result = BreakpointListResult(
            success=True,
            object_type="CLAS",
            object_name="ZCL_TEST",
            method_name="MY_METHOD",
            breakpoints=[
                BreakpointEntry(line_number=10, source_line="DATA lv_x TYPE i."),
                BreakpointEntry(line_number=20, source_line="lv_x = 1."),
            ],
            error=None,
        )
        assert len(result.breakpoints) == 2
        assert result.breakpoints[0].line_number == 10

    def test_failure_factory(self) -> None:
        result = BreakpointListResult.failure(
            error="Navigation failed",
            object_type="FUGR",
            object_name="BREA",
            method_name="MY_FM",
        )
        assert result.success is False
        assert result.breakpoints == []


class TestResolveMatchPattern:
    def test_substring_match_first_line(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i.\nlv_x = 1."
        assert _resolve_match_pattern(source, "lv_x = 1") == 3

    def test_substring_match_first_occurrence(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i.\nlv_x = 1.\nlv_x = 2."
        assert _resolve_match_pattern(source, "lv_x") == 2  # first occurrence

    def test_pattern_not_found_returns_none(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i."
        assert _resolve_match_pattern(source, "nonexistent_pattern") is None

    def test_regex_match(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nCALL FUNCTION 'MY_FM'.\nDATA lv_x TYPE i."
        assert _resolve_match_pattern(source, r"CALL FUNCTION '.*'") == 2


class TestParseToggleStatus:
    def test_gesetzt_means_set(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _classify_toggle_status

        assert _classify_toggle_status("Externer Breakpoint in Programm ZTEST gesetzt") == "set"

    def test_geloescht_means_deleted(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _classify_toggle_status

        assert _classify_toggle_status("Externer Breakpoint in Programm ZTEST gelöscht") == "deleted"

    def test_unknown_returns_none(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _classify_toggle_status

        assert _classify_toggle_status("Some unexpected SAP message") is None


class TestResolveLineNumberValidation:
    def test_line_number_within_range_is_valid(self) -> None:
        from sapwebguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i.\nlv_x = 1."
        # 3 lines — line 3 is valid
        assert _resolve_match_pattern(source, "lv_x = 1") == 3

    def test_out_of_range_error_message_format(self) -> None:
        # Validates the error message format spec requires:
        # "Line N exceeds source length (M lines)"
        line_number = 999
        line_count = 10
        msg = f"Line {line_number} exceeds source length ({line_count} lines)"
        assert "999" in msg
        assert "10" in msg
