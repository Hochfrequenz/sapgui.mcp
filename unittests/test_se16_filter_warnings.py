"""Unit tests for SE16 filter warning propagation."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import ScreenInfo, StatusBarInfo, TableData, TableRow, TransactionResult
from sapguimcp.models.se16_models import SE16Result, SE16Row
from sapguimcp.tools.se16_tools import (
    _empty_failure,
    _execute_se16_query_desktop,
    _fill_se16n_filters_desktop,
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


async def _run_desktop_query_with_fill(
    fill: _FilterFillResult, backend: AsyncMock | None = None
) -> tuple[SE16Result, AsyncMock]:
    backend = backend or _make_desktop_backend()
    with patch("sapguimcp.tools.se16_tools._fill_se16n_filters_desktop", new=AsyncMock(return_value=fill)):
        result = await _execute_se16_query_desktop(
            backend,
            table="TSTC",
            filters={"ZZZFAKE": "X", "TCODE": "SE16"},
            max_hits=10,
            now=datetime.now(UTC),
        )
    return result, backend


def _pressed_keys(backend: AsyncMock) -> list[str]:
    return [call.args[0] for call in backend.press_key.await_args_list]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_unapplied_field_fails_before_f8() -> None:
    fill = _FilterFillResult(unapplied_fields=["ZZZFAKE"], offered_fields=["TCODE", "PGMNA"])

    result, backend = await _run_desktop_query_with_fill(fill)

    assert result.success is False
    assert result.error is not None
    assert "'ZZZFAKE'" in result.error
    assert "Offered fields: TCODE, PGMNA." in result.error
    assert result.filter_warnings == ["Field 'ZZZFAKE' not found in SE16N selection criteria"]
    assert result.returned_rows == 0
    assert result.rows == []
    assert _pressed_keys(backend) == ["Enter"]  # F8 never pressed
    backend.read_table.assert_not_awaited()
    backend.get_status_bar.assert_not_awaited()


@pytest.mark.anyio
async def test_execute_se16_query_desktop_only_other_errors_fails_before_f8() -> None:
    fill = _FilterFillResult(other_errors=["SE16N selection criteria table control not found"])

    result, backend = await _run_desktop_query_with_fill(fill)

    assert result.success is False
    assert result.error == "Could not apply filters: SE16N selection criteria table control not found"
    assert result.filter_warnings == ["SE16N selection criteria table control not found"]
    assert _pressed_keys(backend) == ["Enter"]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_both_error_kinds_fails_with_unapplied_error() -> None:
    fill = _FilterFillResult(unapplied_fields=["ZZZFAKE"], other_errors=["other problem"], offered_fields=["TCODE"])

    result, backend = await _run_desktop_query_with_fill(fill)

    assert result.success is False
    assert result.error is not None
    assert result.error.startswith(
        "Filter field(s) 'ZZZFAKE' not available as SE16N selection criteria for table TSTC."
    )
    assert "other problem" not in result.error
    assert result.filter_warnings == ["Field 'ZZZFAKE' not found in SE16N selection criteria", "other problem"]
    assert _pressed_keys(backend) == ["Enter"]


@pytest.mark.anyio
async def test_execute_se16_query_desktop_clean_fill_runs_query_unchanged() -> None:
    result, backend = await _run_desktop_query_with_fill(_FilterFillResult())

    assert result.success is True
    assert result.filter_warnings == []
    assert result.returned_rows == 1
    assert result.rows[0].data["TCODE"] == "SE16"
    assert _pressed_keys(backend) == ["Enter", "F8"]


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


class _ValueCell:
    def __init__(self, grid: "_FakeGrid", name: str) -> None:
        self._grid = grid
        self._name = name

    @property
    def Text(self) -> str:  # noqa: N802  (mirrors the SAP GUI COM attribute)
        return self._grid.values.get(self._name, "")

    @Text.setter
    def Text(self, value: str) -> None:  # noqa: N802
        self._grid.values[self._name] = value


class _NameCell:
    def __init__(self, text: str) -> None:
        self.Text = text


class _Scrollbar:
    def __init__(self, maximum: int) -> None:
        self.Maximum = maximum
        self._position = 0
        self.position_writes = 0

    @property
    def Position(self) -> int:  # noqa: N802
        return self._position

    @Position.setter
    def Position(self, value: int) -> None:  # noqa: N802
        self.position_writes += 1
        self._position = value


class _FakeGrid:
    """Minimal stand-in for the SE16N GuiTableControl: column 6 = field name, column 2 = From-value."""

    def __init__(self, names: list[str], visible: int) -> None:
        self._names = names
        self.RowCount = len(names)
        self.VisibleRowCount = visible
        self.VerticalScrollbar = _Scrollbar(max(0, len(names) - visible))
        self.values: dict[str, str] = {}

    def GetCell(self, row: int, col: int) -> Any:  # noqa: N802
        idx = self.VerticalScrollbar.Position + row
        name = self._names[idx] if idx < len(self._names) else ""
        if col == 6:
            return _NameCell(name)
        return _ValueCell(self, name)


def _desktop_backend_with_grid(grid: _FakeGrid | None) -> MagicMock:
    backend = MagicMock(spec=DesktopBackend)
    session = MagicMock()
    if grid is None:
        session.find_by_id.side_effect = RuntimeError("not found")
    else:
        session.find_by_id.return_value = SimpleNamespace(com=grid)
    backend.require_session.return_value = session

    async def _run(fn: Any) -> Any:
        return fn()

    backend.com = SimpleNamespace(run=_run)
    return backend


@pytest.mark.anyio
async def test_fill_all_fields_found_collects_no_offered_fields() -> None:
    grid = _FakeGrid(["MANDT", "MTEXT", "ORT01"], visible=5)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"mtext": "Foo"})

    assert result == _FilterFillResult()
    assert grid.values == {"MTEXT": "Foo"}


@pytest.mark.anyio
async def test_fill_unknown_field_within_visible_rows_lists_visible_names_only() -> None:
    # row_count (3) <= visible (5): no scrolling, offered names come from the visible rows only
    grid = _FakeGrid(["MANDT", "", "MTEXT"], visible=5)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert result.other_errors == []
    assert result.offered_fields == ["MANDT", "MTEXT"]  # blank padding row skipped
    assert grid.VerticalScrollbar.position_writes == 0  # never scrolled


@pytest.mark.anyio
async def test_fill_unknown_field_walks_scrolled_grid_dedupes_and_keeps_order() -> None:
    names = ["MANDT", "MTEXT", "ORT01", "MTEXT", "MWAER", "", "ADRNR"]  # MTEXT repeated, one blank
    grid = _FakeGrid(names, visible=3)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert result.offered_fields == ["MANDT", "MTEXT", "ORT01", "MWAER", "ADRNR"]
    assert grid.VerticalScrollbar.Position == 0  # scrolled back to top


@pytest.mark.anyio
async def test_fill_later_field_still_set_after_an_unapplied_one_and_found_field_adds_no_offered() -> None:
    grid = _FakeGrid(["MANDT", "MTEXT", "ORT01", "MWAER", "ADRNR"], visible=2)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZFAKE": "X", "ADRNR": "1"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert grid.values == {"ADRNR": "1"}  # field after the unapplied one was still searched and set
    assert result.offered_fields == ["MANDT", "MTEXT", "ORT01", "MWAER", "ADRNR"]


@pytest.mark.anyio
async def test_fill_two_unapplied_fields_dedupes_offered_across_scans() -> None:
    grid = _FakeGrid(["MANDT", "MTEXT", "ORT01", "MWAER"], visible=2)

    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(grid), {"ZZZ1": "X", "ZZZ2": "Y"})

    assert result.unapplied_fields == ["ZZZ1", "ZZZ2"]
    assert result.offered_fields == ["MANDT", "MTEXT", "ORT01", "MWAER"]


@pytest.mark.anyio
async def test_fill_table_control_missing_is_other_error() -> None:
    result = await _fill_se16n_filters_desktop(_desktop_backend_with_grid(None), {"MANDT": "1"})

    assert result.unapplied_fields == []
    assert result.other_errors == ["SE16N selection criteria table control not found"]
    assert result.offered_fields == []


@pytest.mark.anyio
async def test_fill_non_desktop_backend_is_other_error() -> None:
    result = await _fill_se16n_filters_desktop(MagicMock(), {"MANDT": "1"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert result.other_errors[0].startswith("Filter filling requires DesktopBackend")


@pytest.mark.anyio
async def test_tool_description_documents_strict_filter_fields() -> None:
    server = FastMCP("t")
    register_se16_tools(server)
    async with Client(server) as client:
        tools = {t.name: t for t in await client.list_tools()}
    description = tools["sap_se16_query"].description or ""
    assert "desktop" in description.lower()
    assert "not offered by SE16N" in description
    assert "fails before running the query" in description
    assert "selection fields" in description
