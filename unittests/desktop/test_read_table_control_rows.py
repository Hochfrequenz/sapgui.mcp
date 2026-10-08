"""Tests for reading a GuiTableControl (e.g. the methods table of SE24), which only holds its visible window."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sapguimcp.backend.desktop import _read_table_control, _table_control_headers

_HEADERS = ["Method", "Kind"]


class _Scrollbar:
    def __init__(self, position: int) -> None:
        self.Position = position
        self.writes = 0

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "Position" and hasattr(self, "writes"):
            self.writes += 1
        object.__setattr__(self, name, value)


class _Columns:
    def __init__(self, columns: list[tuple[str, str, str]]) -> None:
        self._columns = [SimpleNamespace(Title=title, Name=name2) for title, _, name2 in columns]
        self.Count = len(columns)

    def __call__(self, index: int) -> Any:
        return self._columns[index]


class _TableControl:
    """Fake table control: ``row_count`` rows, a window of ``visible`` rows starting at ``first``.

    Cells are ``txt...[col,row]`` elements; the window always has ``visible`` lines, those after the last row are
    empty, like on SAP GUI.
    """

    def __init__(self, row_count: int, visible: int = 20, first: int = 0, scrollbar: bool = True) -> None:
        self.RowCount = row_count
        self.VisibleRowCount = visible
        self._scrollbar = _Scrollbar(first)
        self._has_scrollbar = scrollbar
        self.com = self  # the reader unwraps ``.com``
        self.Columns = _Columns([(h, h, f"DY-{h.upper()}") for h in _HEADERS])
        self.cell_columns = list(range(len(_HEADERS)))  # which column index each cell id claims, per column

    @property
    def VerticalScrollbar(self) -> _Scrollbar:  # noqa: N802 - COM name
        if not self._has_scrollbar:
            raise RuntimeError("COM error")
        return self._scrollbar

    def dump_tree(self) -> list[Any]:
        elements = []
        for row in range(self.VisibleRowCount):
            index = self._scrollbar.Position + row
            for col, header in enumerate(_HEADERS):
                text = f"{header}{index}" if index < self.RowCount else ""
                field = f"DY-{header.upper()}"
                shown = self.cell_columns[col]
                elements.append(SimpleNamespace(id=f"/tbl/txt{field}[{shown},{row}]", text=text, children=[]))
        return elements


def _expected(start: int, end: int) -> list[dict[str, Any]]:
    return [{"row": i + 1, "data": {"Method": f"Method{i}", "Kind": f"Kind{i}"}} for i in range(start, end)]


def _read(tc: _TableControl, start: int, end: int) -> list[dict[str, Any]]:
    """The rows ``start`` to ``end`` (0-based, exclusive), as a caller asking for rows ``start + 1`` to ``end``."""
    return _read_table_control(tc, start + 1, end, 100)["rows"]  # type: ignore[no-any-return]


@pytest.mark.parametrize(("row_count", "visible"), [(5, 20), (20, 20), (1, 20)])
def test_a_table_that_fits_the_window_is_read_completely(row_count: int, visible: int) -> None:
    tc = _TableControl(row_count, visible, scrollbar=False)
    assert _read(tc, 0, row_count) == _expected(0, row_count)


def test_empty_lines_after_the_last_row_are_ignored() -> None:
    assert _read(_TableControl(3, 20), 0, 100) == _expected(0, 3)


def test_a_longer_table_returns_only_its_window() -> None:
    assert _read(_TableControl(32, 20), 0, 32) == _expected(0, 20)


def test_a_scrolled_window_is_indexed_from_its_first_row() -> None:
    assert _read(_TableControl(32, 20, first=12), 0, 32) == _expected(12, 32)


@pytest.mark.parametrize(("start", "end"), [(0, 3), (5, 10), (25, 30)])
def test_a_range_inside_the_window_is_returned(start: int, end: int) -> None:
    tc = _TableControl(32, 20, first=12 if start >= 12 else 0)
    assert _read(tc, start, end) == _expected(start, end)


def test_a_range_outside_the_window_returns_nothing() -> None:
    assert _read(_TableControl(32, 20), 25, 30) == []


def test_the_table_is_never_scrolled() -> None:
    tc = _TableControl(100, 20)
    _read(tc, 0, 100)
    assert tc._scrollbar.writes == 0


def test_an_unreadable_scrollbar_of_a_longer_table_is_an_error_not_wrong_row_numbers() -> None:
    with pytest.raises(RuntimeError, match="COM error"):
        _read(_TableControl(32, 20, scrollbar=False), 0, 32)


def test_the_table_data_fields_describe_the_rows_returned_and_the_real_total() -> None:
    data = _read_table_control(_TableControl(32, 20, first=12), 1, None, 100)
    assert data["headers"] == _HEADERS
    assert data["total_rows"] == 32
    assert (data["start_row"], data["end_row"]) == (13, 32)
    assert len(data["rows"]) == 20


def test_the_requested_range_limits_the_rows_and_max_rows_applies_without_an_end_row() -> None:
    tc = _TableControl(32, 20)
    assert [r["row"] for r in _read_table_control(tc, 3, 5, 100)["rows"]] == [3, 4, 5]
    assert [r["row"] for r in _read_table_control(tc, 3, None, 4)["rows"]] == [3, 4, 5, 6]


def test_nothing_in_the_window_keeps_the_requested_start_and_leaves_end_row_empty() -> None:
    data = _read_table_control(_TableControl(32, 20), 25, 30, 100)
    assert data["rows"] == []
    assert (data["start_row"], data["end_row"], data["total_rows"]) == (25, None, 32)


def test_cells_are_assigned_by_field_name_not_by_the_column_index_in_their_id() -> None:
    tc = _TableControl(3, 20)
    tc.cell_columns = [1, 0]  # the ids claim swapped column indexes (reordered or hidden columns)
    assert _read(tc, 0, 3) == _expected(0, 3)


def test_a_cell_without_a_known_field_name_falls_back_to_the_column_index() -> None:
    tc = _TableControl(2, 20)
    tc.Columns = _Columns([(h, h, "") for h in _HEADERS])
    assert _read(tc, 0, 2) == _expected(0, 2)


def test_headers_use_the_title_and_fall_back_to_the_name() -> None:
    columns = {
        0: SimpleNamespace(Title="Method", Name="DY-NAME"),
        1: SimpleNamespace(Title="", Name="DY-KIND"),
        2: SimpleNamespace(Title="", Name=""),
    }

    class _Columns:
        Count = 3

        def __call__(self, index: int) -> Any:
            return columns[index]

    raw = SimpleNamespace(Columns=_Columns())
    assert _table_control_headers(raw) == ["Method", "DY-KIND", "col2"]


def test_repeated_column_titles_get_a_counter_instead_of_overwriting_each_other() -> None:
    raw = SimpleNamespace(Columns=_Columns([("Text", "", "A"), ("Text", "", "B"), ("", "", "")]))
    assert _table_control_headers(raw) == ["Text", "Text (2)", "col2"]


def test_a_blank_last_line_of_the_window_is_dropped_but_not_blank_rows_in_between() -> None:
    tc = _TableControl(32, 20)
    original = tc.dump_tree

    def _blank(rows_to_blank: set[int]) -> list[Any]:
        elements = original()
        for element in elements:
            if int(element.id.rsplit(",", 1)[1].rstrip("]")) in rows_to_blank:
                element.text = ""
        return elements

    tc.dump_tree = lambda: _blank({19, 5})  # type: ignore[method-assign]
    rows = _read(tc, 0, 32)
    assert [r["row"] for r in rows] == list(range(1, 20))
    assert rows[5]["data"] == {"Method": "", "Kind": ""}


@pytest.mark.parametrize("partial_reads", [1, 2, 4])
def test_a_window_that_is_still_filling_is_read_again_until_it_is_complete(partial_reads: int) -> None:
    tc = _TableControl(32, 20)
    original = tc.dump_tree
    reads = [0]

    def _filling() -> list[Any]:
        elements = original()
        reads[0] += 1
        if reads[0] <= partial_reads:  # SAP GUI has only shown the first rows so far
            for element in elements:
                if int(element.id.rsplit(",", 1)[1].rstrip("]")) >= 3:
                    element.text = ""
        return elements

    tc.dump_tree = _filling  # type: ignore[method-assign]
    assert _read(tc, 0, 32) == _expected(0, 20)
