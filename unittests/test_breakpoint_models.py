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
