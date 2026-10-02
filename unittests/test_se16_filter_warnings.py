"""Unit tests for SE16 filter warning propagation."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.models import ScreenInfo, StatusBarInfo, TableData, TableRow, TransactionResult
from sapguimcp.models.se16_models import SE16Result, SE16Row
from sapguimcp.tools.se16_tools import (
    _empty_failure,
    _execute_se16_query_desktop,
    _filter_fill_failure,
    _FilterFillResult,
    _format_offered_fields,
    register_se16_tools,
)


def _make_desktop_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=TransactionResult(tcode="SE16N"))
    backend.wait_for_ready = AsyncMock()
    backend.wait = AsyncMock()
    backend.get_screen_info = AsyncMock(
        return_value=ScreenInfo(
            title="SE16N",
            url="sap://session",
            transaction="SE16N",
            program="SAPLSE16N",
        )
    )
    backend.focus_and_type = AsyncMock(side_effect=[True, True])
    backend.press_key = AsyncMock()
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    backend.read_table = AsyncMock(
        return_value=TableData(
            headers=["TCODE"],
            rows=[TableRow(row=1, data={"TCODE": "SE16"})],
            total_rows=1,
        )
    )
    backend.get_page_title = AsyncMock(return_value="SE16N: Display of Entries Found")
    return backend


class TestSE16ResultFilterWarnings:
    """Tests for the SE16 filter_warnings payload."""

    def test_defaults_to_empty_list(self) -> None:
        result = SE16Result(
            table="TSTC",
            total_hits=1,
            returned_rows=1,
            truncated=False,
            columns=["TCODE"],
            rows=[SE16Row(data={"TCODE": "SE16"})],
            retrieved_at=datetime.now(UTC),
        )

        assert result.filter_warnings == []

    def test_json_roundtrip(self) -> None:
        original = SE16Result(
            table="TSTC",
            total_hits=1,
            returned_rows=1,
            truncated=False,
            columns=["TCODE"],
            rows=[SE16Row(data={"TCODE": "SE16"})],
            filter_warnings=["Field 'ZZZFAKE' not found in SE16N selection criteria"],
            retrieved_at=datetime.now(UTC),
        )

        restored = SE16Result.model_validate_json(original.model_dump_json())

        assert restored.filter_warnings == original.filter_warnings


@pytest.mark.anyio
async def test_execute_se16_query_desktop_returns_filter_warnings() -> None:
    backend = _make_desktop_backend()
    warnings = [
        "Field 'ZZZFAKE' not found in SE16N selection criteria",
        "Field 'MANDT' could not be applied because the selection criteria table control was not found",
    ]

    with patch("sapguimcp.tools.se16_tools._fill_se16n_filters_desktop", new=AsyncMock(return_value=warnings)):
        result = await _execute_se16_query_desktop(
            backend,
            table="TSTC",
            filters={"ZZZFAKE": "X", "MANDT": "100"},
            max_hits=10,
            now=datetime.now(UTC),
        )

    assert result.success is True
    assert result.filter_warnings == warnings
    assert result.returned_rows == 1
    assert result.rows[0].data["TCODE"] == "SE16"
    assert backend.press_key.await_args_list[0].args == ("Enter",)
    assert backend.press_key.await_args_list[-1].args == ("F8",)


@pytest.mark.anyio
async def test_file_output_summary_carries_filter_warnings(tmp_path, monkeypatch) -> None:
    """With output_file, sap_se16_query returns an SE16FileSummary — it must still say which filters were skipped."""
    monkeypatch.chdir(tmp_path)  # output_file writes are sandboxed to the cwd (or OUTPUT_DIR)
    result = SE16Result(
        success=True,
        table="TSTC",
        total_hits=1,
        returned_rows=1,
        truncated=False,
        columns=["TCODE"],
        rows=[SE16Row(data={"TCODE": "SE16"})],
        filter_warnings=["TCODE: field not found on selection screen"],
        retrieved_at=datetime.now(UTC),
    )
    server = FastMCP("t")
    register_se16_tools(server)
    with (
        patch("sapguimcp.tools.se16_tools.get_backend", new=AsyncMock(return_value=AsyncMock())),
        patch("sapguimcp.tools.se16_tools._execute_se16_query", new=AsyncMock(return_value=result)),
    ):
        async with Client(server) as client:
            raw = await client.call_tool(
                "sap_se16_query", {"table": "TSTC", "filters": {"TCODE": "SE16"}, "output_file": "tstc.json"}
            )
    summary = json.loads(raw.content[0].text)
    assert summary["output_file"]
    assert summary["filter_warnings"] == ["TCODE: field not found on selection screen"]


class TestFilterFillResult:
    def test_defaults_are_empty_and_independent(self) -> None:
        first = _FilterFillResult()
        second = _FilterFillResult()
        first.unapplied_fields.append("X")

        assert first.unapplied_fields == ["X"]
        assert second.unapplied_fields == []
        assert second.other_errors == []
        assert second.offered_fields == []


class TestEmptyFailureFilterWarnings:
    def test_passes_filter_warnings_through(self) -> None:
        now = datetime.now(UTC)

        result = _empty_failure("boom", "T000", now, filter_warnings=["w1", "w2"])

        assert result.success is False
        assert result.error == "boom"
        assert result.filter_warnings == ["w1", "w2"]

    def test_defaults_to_no_warnings(self) -> None:
        result = _empty_failure("boom", "T000", datetime.now(UTC))

        assert result.filter_warnings == []


class TestFormatOfferedFields:
    def test_empty_returns_empty_string(self) -> None:
        assert _format_offered_fields([]) == ""

    def test_joins_names(self) -> None:
        assert _format_offered_fields(["A", "B", "C"]) == "A, B, C"

    def test_exactly_fifty_has_no_suffix(self) -> None:
        names = [f"F{i:02d}" for i in range(50)]

        text = _format_offered_fields(names)

        assert text == ", ".join(names)
        assert "more" not in text

    def test_more_than_fifty_is_capped_with_suffix(self) -> None:
        names = [f"F{i:02d}" for i in range(53)]

        text = _format_offered_fields(names)

        assert text == ", ".join(names[:50]) + ", … (+3 more)"
        assert "F50" not in text


class TestFilterFillFailure:
    def test_unapplied_fields_message_and_warnings(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["ZZZ1", "ZZZ2"], offered_fields=["MANDT", "MTEXT"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.success is False
        assert result.error == (
            "Filter field(s) 'ZZZ1', 'ZZZ2' not available as SE16N selection criteria for table T000. "
            "Offered fields: MANDT, MTEXT. "
            "A field can exist in the table without being an SE16N selection field; "
            "use sap-adt `run_query` if available."
        )
        assert result.filter_warnings == [
            "Field 'ZZZ1' not found in SE16N selection criteria",
            "Field 'ZZZ2' not found in SE16N selection criteria",
        ]
        assert result.total_hits == 0
        assert result.rows == []

    def test_empty_offered_list_omits_offered_sentence(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["ZZZ1"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.error is not None
        assert "Offered fields" not in result.error
        assert result.error.startswith(
            "Filter field(s) 'ZZZ1' not available as SE16N selection criteria for table T000."
        )

    def test_only_other_errors(self) -> None:
        fill = _FilterFillResult(other_errors=["SE16N selection criteria table control not found", "second"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.success is False
        assert result.error == "Could not apply filters: SE16N selection criteria table control not found; second"
        assert result.filter_warnings == ["SE16N selection criteria table control not found", "second"]

    def test_both_kinds_use_unapplied_error_and_append_other_errors_to_warnings(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["ZZZ1"], other_errors=["other"], offered_fields=["MANDT"])

        result = _filter_fill_failure(fill, "T000", datetime.now(UTC))

        assert result.error is not None
        assert result.error.startswith("Filter field(s) 'ZZZ1' not available")
        assert "other" not in result.error
        assert result.filter_warnings == ["Field 'ZZZ1' not found in SE16N selection criteria", "other"]
