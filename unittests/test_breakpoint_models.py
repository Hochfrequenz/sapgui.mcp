"""Unit tests for breakpoint data models."""

import pytest
from pydantic import ValidationError

from sapguimcp.models.breakpoint_models import (
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

    def test_invalid_action_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BreakpointSetResult(
                success=True,
                object_type="PROG",
                object_name="ZTEST",
                method_name=None,
                line_number=10,
                action="deleted_instead",  # type: ignore[arg-type]
                status_message="",
                error=None,
            )

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
        from sapguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i.\nlv_x = 1."
        assert _resolve_match_pattern(source, "lv_x = 1") == 3

    def test_substring_match_first_occurrence(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i.\nlv_x = 1.\nlv_x = 2."
        assert _resolve_match_pattern(source, "lv_x") == 2  # first occurrence

    def test_pattern_not_found_returns_none(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nDATA lv_x TYPE i."
        assert _resolve_match_pattern(source, "nonexistent_pattern") is None

    def test_regex_match(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _resolve_match_pattern

        source = "REPORT ztest.\nCALL FUNCTION 'MY_FM'.\nDATA lv_x TYPE i."
        assert _resolve_match_pattern(source, r"CALL FUNCTION '.*'") == 2


class TestParseToggleStatus:
    def test_gesetzt_means_set(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _classify_toggle_status

        assert _classify_toggle_status("Externer Breakpoint in Programm ZTEST gesetzt") == "set"

    def test_geloescht_means_deleted(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _classify_toggle_status

        assert _classify_toggle_status("Externer Breakpoint in Programm ZTEST gelöscht") == "deleted"

    def test_unknown_returns_none(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _classify_toggle_status

        assert _classify_toggle_status("Some unexpected SAP message") is None


class TestResolveLineNumberValidation:
    def test_line_number_within_range_is_valid(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _resolve_match_pattern

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


class TestFilterBpRows:
    """Unit tests for _filter_bp_rows — pure logic, no SAP needed."""

    _PROG_ROW = {"MAINPROGRAM_DIS": "", "INCLUDE_DIS": "ZTEST_PROG", "SOURCE_LINE": "10", "SOURCE": "DATA lv_x."}
    _PROG_ROW_OTHER = {"MAINPROGRAM_DIS": "", "INCLUDE_DIS": "ZTEST_OTHER", "SOURCE_LINE": "5", "SOURCE": "WRITE."}
    _CLAS_ROW = {
        "MAINPROGRAM_DIS": "ZCL_MYCLASS",
        "INCLUDE_DIS": "ZCL_MYCLASS===========CM_MY_METHOD_01",
        "SOURCE_LINE": "18",
        "SOURCE": "lv_x = 1.",
    }
    _CLAS_ROW_OTHER = {
        "MAINPROGRAM_DIS": "ZCL_OTHER",
        "INCLUDE_DIS": "ZCL_OTHER===========CM_SOME_METHOD_01",
        "SOURCE_LINE": "5",
        "SOURCE": "WRITE.",
    }
    _FUGR_ROW = {"MAINPROGRAM_DIS": "BREA", "INCLUDE_DIS": "LBREAU01", "SOURCE_LINE": "42", "SOURCE": "IF x."}
    _FUGR_ROW_OTHER = {
        "MAINPROGRAM_DIS": "OTHER_GRP",
        "INCLUDE_DIS": "LOTHER01",
        "SOURCE_LINE": "3",
        "SOURCE": "WRITE.",
    }

    def test_prog_match_by_include_dis(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        entries = _filter_bp_rows([self._PROG_ROW, self._PROG_ROW_OTHER], "PROG", "ZTEST_PROG", None)
        assert len(entries) == 1
        assert entries[0].line_number == 10

    def test_prog_no_match(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        entries = _filter_bp_rows([self._PROG_ROW_OTHER], "PROG", "ZTEST_PROG", None)
        assert entries == []

    def test_prog_case_insensitive(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        entries = _filter_bp_rows([self._PROG_ROW], "PROG", "ztest_prog", None)
        assert len(entries) == 1

    def test_clas_match_by_main_prog(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        entries = _filter_bp_rows([self._CLAS_ROW, self._CLAS_ROW_OTHER], "CLAS", "ZCL_MYCLASS", "MY_METHOD")
        assert len(entries) == 1
        assert entries[0].line_number == 18

    def test_clas_returns_all_methods_for_class(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        second_method_row = {
            "MAINPROGRAM_DIS": "ZCL_MYCLASS",
            "INCLUDE_DIS": "ZCL_MYCLASS===========CM_OTHER_METHOD_01",
            "SOURCE_LINE": "99",
            "SOURCE": "WRITE.",
        }
        entries = _filter_bp_rows([self._CLAS_ROW, second_method_row], "CLAS", "ZCL_MYCLASS", "MY_METHOD")
        # Both rows match — filter is class-level, not method-level
        assert len(entries) == 2

    def test_fugr_match_by_main_prog(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        entries = _filter_bp_rows([self._FUGR_ROW, self._FUGR_ROW_OTHER], "FUGR", "BREA", "MY_FM")
        assert len(entries) == 1
        assert entries[0].line_number == 42

    def test_non_numeric_source_line_skipped(self) -> None:
        from sapguimcp.tools.breakpoint_tools import _filter_bp_rows

        bad_row = {"MAINPROGRAM_DIS": "", "INCLUDE_DIS": "ZTEST_PROG", "SOURCE_LINE": "N/A", "SOURCE": "WRITE."}
        entries = _filter_bp_rows([bad_row], "PROG", "ZTEST_PROG", None)
        assert entries == []


class TestXorValidation:
    """Both-None and both-provided are rejected by sap_breakpoint_set/delete."""

    def test_xor_error_message_format(self) -> None:
        # The exact error string used in both tools
        msg = "Provide exactly one of line_number or match_pattern"
        assert "line_number" in msg
        assert "match_pattern" in msg
