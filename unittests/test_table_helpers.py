"""Unit tests for table_helpers — scroll-with-re-find logic for desktop table controls."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from sapguimcp.tools.table_helpers import (
    _find_table_control_info,
    _read_visible_page,
    _read_visible_page_from_tree,
    read_table_control,
    read_table_control_all_rows,
)

# ---------------------------------------------------------------------------
# _read_visible_page
# ---------------------------------------------------------------------------


class TestReadVisiblePage:
    def test_reads_rows(self) -> None:
        raw = MagicMock()
        raw.GetCell.return_value.Text = "val"
        rows = _read_visible_page(raw, ["Col1", "Col2"], 2)
        assert len(rows) == 2
        assert rows[0] == {"Col1": "val", "Col2": "val"}

    def test_exception_skipped(self) -> None:
        raw = MagicMock()
        raw.GetCell.side_effect = OSError("COM error")
        rows = _read_visible_page(raw, ["Col1"], 1)
        assert rows == [{}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(
    *,
    row_count: int = 5,
    visible_count: int = 3,
    col_names: list[str] | None = None,
) -> tuple[MagicMock, Any]:
    """Build a mock session + flatten_fn that simulates a GuiTableControl."""
    col_names = col_names or ["Name", "Type"]

    # Table control COM mock
    raw_tc = MagicMock()
    raw_tc.RowCount = row_count
    raw_tc.VisibleRowCount = visible_count
    raw_tc.Columns.Count = len(col_names)
    raw_tc.Columns.side_effect = lambda idx, _names=col_names: type(
        "Col", (), {"Title": _names[idx], "Name": _names[idx]}
    )()
    raw_tc.GetCell = lambda r, c: type("Cell", (), {"Text": f"r{r}c{c}"})()
    raw_tc.VerticalScrollbar = MagicMock()
    raw_tc.VerticalScrollbar.Position = 0

    # Wrap in a tc object that has a _com attribute but no .com
    tc_wrapper = MagicMock(spec=[])
    tc_wrapper._com = raw_tc

    # Element that represents a GuiTableControl (type 80)
    elem = MagicMock()
    elem.type_as_number = 80
    elem.id = "wnd[0]/usr/tblTABLE"

    # Session mock
    session = MagicMock()
    wnd = MagicMock()
    wnd.dump_tree.return_value = "tree"
    session.find_by_id.side_effect = lambda path: wnd if path == "wnd[0]" else tc_wrapper

    flatten_fn = MagicMock(return_value=[elem])
    return session, flatten_fn


# ---------------------------------------------------------------------------
# _find_table_control_info
# ---------------------------------------------------------------------------


class TestFindTableControlInfo:
    def test_finds_table(self) -> None:
        session, flatten_fn = _make_mock_session(row_count=5, visible_count=3)
        result = _find_table_control_info(session, flatten_fn)
        assert result is not None
        element_id, col_titles, total, visible = result
        assert element_id == "wnd[0]/usr/tblTABLE"
        assert col_titles == ["Name", "Type"]
        assert total == 5
        assert visible == 3

    def test_no_table(self) -> None:
        session = MagicMock()
        wnd = MagicMock()
        wnd.dump_tree.return_value = "tree"
        session.find_by_id.return_value = wnd
        elem = MagicMock()
        elem.type_as_number = 42
        flatten_fn = MagicMock(return_value=[elem])
        assert _find_table_control_info(session, flatten_fn) is None


# ---------------------------------------------------------------------------
# read_table_control (visible-only, sync)
# ---------------------------------------------------------------------------


class TestReadTableControl:
    def test_reads_visible_rows(self) -> None:
        session, flatten_fn = _make_mock_session(row_count=5, visible_count=3)
        rows = read_table_control(session, flatten_fn)
        assert len(rows) == 3

    def test_returns_empty_when_no_table(self) -> None:
        session = MagicMock()
        wnd = MagicMock()
        wnd.dump_tree.return_value = "tree"
        session.find_by_id.return_value = wnd
        elem = MagicMock()
        elem.type_as_number = 42
        flatten_fn = MagicMock(return_value=[elem])
        assert read_table_control(session, flatten_fn) == []


# ---------------------------------------------------------------------------
# read_table_control_all_rows (with scrolling + re-find)
# ---------------------------------------------------------------------------


class TestReadTableControlAllRows:
    def test_reads_all_rows_with_scrolling(self) -> None:
        """Table with 5 rows and 3 visible should scroll once and read all 5."""
        session, flatten_fn = _make_mock_session(row_count=5, visible_count=3)
        rows = read_table_control_all_rows(session, flatten_fn)
        assert len(rows) == 5

    def test_no_scroll_when_all_visible(self) -> None:
        session, flatten_fn = _make_mock_session(row_count=3, visible_count=5)
        rows = read_table_control_all_rows(session, flatten_fn)
        assert len(rows) == 3

    def test_returns_empty_when_no_table(self) -> None:
        session = MagicMock()
        wnd = MagicMock()
        wnd.dump_tree.return_value = "tree"
        session.find_by_id.return_value = wnd
        elem = MagicMock()
        elem.type_as_number = 42
        flatten_fn = MagicMock(return_value=[elem])
        assert read_table_control_all_rows(session, flatten_fn) == []

    def test_re_finds_table_after_scroll(self) -> None:
        """Verify session.find_by_id is called multiple times (re-find pattern)."""
        session, flatten_fn = _make_mock_session(row_count=10, visible_count=3)
        read_table_control_all_rows(session, flatten_fn)
        # find_by_id should be called: 1 (wnd[0]) + 1 (initial find_table_control_info)
        # + N (re-finds after scroll) + 1 (scroll back to top)
        find_calls = [c for c in session.find_by_id.call_args_list if c.args[0] != "wnd[0]"]
        # At least 4 re-finds: initial + after scroll to 3 + after scroll to 6 + after scroll to 9 + scroll back
        assert len(find_calls) >= 4

    def test_scroll_error_stops_gracefully(self) -> None:
        """If scrollbar raises, we stop and return what we have."""
        session, flatten_fn = _make_mock_session(row_count=10, visible_count=3)

        # Make a tc_wrapper where scrollbar raises on set
        tc_wrapper = MagicMock(spec=[])
        raw_tc = MagicMock()
        raw_tc.RowCount = 10
        raw_tc.VisibleRowCount = 3
        raw_tc.Columns.Count = 1
        raw_tc.Columns.side_effect = lambda idx: type("Col", (), {"Title": "Name", "Name": "Name"})()
        raw_tc.GetCell = lambda r, c: type("Cell", (), {"Text": f"r{r}c{c}"})()
        type(raw_tc.VerticalScrollbar).Position = PropertyMock(side_effect=OSError("scroll failed"))
        tc_wrapper._com = raw_tc

        elem = MagicMock()
        elem.type_as_number = 80
        elem.id = "wnd[0]/usr/tbl"
        wnd = MagicMock()
        wnd.dump_tree.return_value = "tree"
        session.find_by_id.side_effect = lambda path: wnd if path == "wnd[0]" else tc_wrapper
        flatten_fn.return_value = [elem]

        rows = read_table_control_all_rows(session, flatten_fn)
        # Should have the first page (3 rows) before scroll failed
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# Tree-based page reading (one dump_tree() call per page instead of two COM calls per cell, #928)
# ---------------------------------------------------------------------------


def _cell(column: int, row: int, text: str) -> Any:
    return SimpleNamespace(id=f"wnd[0]/usr/tblTABLE/txtFIELD[{column},{row}]", text=text, children=[])


def _tc_element(cells: list[Any], extra: list[Any] | None = None) -> Any:
    return SimpleNamespace(id="wnd[0]/usr/tblTABLE", text="", children=[*(extra or []), *cells], type_as_number=80)


def _flatten(tree: list[Any]) -> list[Any]:
    result: list[Any] = []
    for elem in tree:
        result.append(elem)
        result.extend(_flatten(elem.children))
    return result


class TestReadVisiblePageFromTree:
    def test_builds_rows_from_cell_id_suffixes(self) -> None:
        cells = [_cell(1, 0, "b0"), _cell(0, 0, "a0"), _cell(0, 1, "a1"), _cell(1, 1, "b1")]
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = cells
        rows = _read_visible_page_from_tree(session, "wnd[0]/usr/tblTABLE", ["A", "B"], 2, _flatten)
        assert rows == [{"A": "a0", "B": "b0"}, {"A": "a1", "B": "b1"}]
        session.find_by_id.return_value.dump_tree.assert_called_once()

    def test_ignores_elements_without_a_cell_suffix(self) -> None:
        column_header = SimpleNamespace(id="wnd[0]/usr/tblTABLE/col[0]", text="Header", children=[])
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = [column_header, _cell(0, 0, "x")]
        rows = _read_visible_page_from_tree(session, "tbl", ["A"], 1, _flatten)
        assert rows == [{"A": "x"}]

    def test_missing_cell_leaves_the_column_out_like_the_cell_reader(self) -> None:
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = [_cell(0, 0, "a0"), _cell(0, 1, "a1")]
        rows = _read_visible_page_from_tree(session, "tbl", ["A", "B"], 2, _flatten)
        assert rows == [{"A": "a0"}, {"A": "a1"}]

    def test_keeps_empty_texts(self) -> None:
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = [_cell(0, 0, "")]
        assert _read_visible_page_from_tree(session, "tbl", ["A"], 1, _flatten) == [{"A": ""}]

    def test_returns_none_without_cells_so_the_caller_can_fall_back(self) -> None:
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = []
        assert _read_visible_page_from_tree(session, "tbl", ["A"], 1, _flatten) is None

    def test_returns_none_when_the_dump_fails(self) -> None:
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.side_effect = OSError("COM error")
        assert _read_visible_page_from_tree(session, "tbl", ["A"], 1, _flatten) is None


class _FakeScrollingTable:
    """Fake table control: serves the cells of the current page through dump_tree(), refuses per-cell COM reads."""

    def __init__(
        self,
        row_count: int,
        visible: int,
        columns: int = 2,
        *,
        allow_cell_reads: bool = False,
        failing_dump_call: int | None = None,
    ) -> None:
        self.allow_cell_reads = allow_cell_reads
        self.failing_dump_call = failing_dump_call
        self.row_count = row_count
        self.visible = visible
        self.columns = columns
        self.position = 0
        self.dump_calls = 0
        self.positions_set: list[int] = []

    # --- the sapsucker-style element the reader finds by id
    def dump_tree(self) -> list[Any]:
        self.dump_calls += 1
        if self.dump_calls == self.failing_dump_call:
            raise OSError("dump failed")
        shown = min(self.visible, self.row_count - self.position)
        return [_cell(c, r, f"r{self.position + r}c{c}") for r in range(shown) for c in range(self.columns)]

    # --- the raw COM object behind it (``.com``)
    @property
    def com(self) -> Any:
        raw = MagicMock()
        raw.RowCount = self.row_count
        raw.VisibleRowCount = self.visible
        raw.Columns.Count = self.columns
        raw.Columns.side_effect = lambda idx: SimpleNamespace(Title=f"C{idx}", Name=f"C{idx}")
        if self.allow_cell_reads:
            raw.GetCell = lambda r, c: SimpleNamespace(Text=f"r{self.position + r}c{c}")
        else:
            raw.GetCell.side_effect = AssertionError("per-cell COM read although the tree has the cells")
        table = self

        class _Scrollbar:
            @property
            def Position(self) -> int:  # noqa: N802 -- COM property name
                return table.position

            @Position.setter
            def Position(self, value: int) -> None:  # noqa: N802
                table.position = value
                table.positions_set.append(value)

        raw.VerticalScrollbar = _Scrollbar()
        return raw


def _session_for(table: _FakeScrollingTable) -> tuple[Any, Any]:
    element = SimpleNamespace(type_as_number=80, id="wnd[0]/usr/tblTABLE", text="", children=[])
    wnd = SimpleNamespace(dump_tree=lambda: [element])
    session = SimpleNamespace(find_by_id=lambda path: wnd if path == "wnd[0]" else table)
    return session, _flatten


class TestTreePathInReaders:
    def test_all_rows_reads_each_page_with_one_dump_and_no_cell_reads(self) -> None:
        table = _FakeScrollingTable(row_count=7, visible=3)
        session, flatten = _session_for(table)
        rows = read_table_control_all_rows(session, flatten)
        assert [r["C0"] for r in rows] == [f"r{i}c0" for i in range(7)]
        assert [r["C1"] for r in rows] == [f"r{i}c1" for i in range(7)]
        assert table.dump_calls == 3  # pages starting at row 0, 3 and 6
        assert table.positions_set == [3, 6, 0]  # scrolled down page by page, then back to the top

    def test_all_rows_single_page(self) -> None:
        table = _FakeScrollingTable(row_count=2, visible=5)
        session, flatten = _session_for(table)
        rows = read_table_control_all_rows(session, flatten)
        assert rows == [{"C0": "r0c0", "C1": "r0c1"}, {"C0": "r1c0", "C1": "r1c1"}]
        assert table.dump_calls == 1

    def test_read_table_control_reads_only_the_visible_page(self) -> None:
        table = _FakeScrollingTable(row_count=7, visible=3)
        session, flatten = _session_for(table)
        rows = read_table_control(session, flatten)
        assert [r["C0"] for r in rows] == ["r0c0", "r1c0", "r2c0"]
        assert table.positions_set == []

    def test_falls_back_to_cell_reads_when_the_tree_has_no_cells(self) -> None:
        session, flatten_fn = _make_mock_session(row_count=3, visible_count=5)
        # The plain mock table control has no dump_tree(), so the reader falls back to GetCell
        rows = read_table_control_all_rows(session, flatten_fn)
        assert rows[0] == {"Name": "r0c0", "Type": "r0c1"}


class TestTreePathRobustness:
    def test_falls_back_when_the_dump_has_fewer_rows_than_expected(self) -> None:
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = [_cell(0, 0, "a0")]  # page not repainted yet
        assert _read_visible_page_from_tree(session, "tbl", ["A"], 3, _flatten) is None

    def test_extra_dump_rows_beyond_count_are_dropped(self) -> None:
        session = MagicMock()
        session.find_by_id.return_value.dump_tree.return_value = [_cell(0, r, f"a{r}") for r in range(5)]
        rows = _read_visible_page_from_tree(session, "tbl", ["A"], 2, _flatten)
        assert rows == [{"A": "a0"}, {"A": "a1"}]

    def test_a_lost_com_connection_is_not_swallowed(self) -> None:
        class _DisconnectedError(Exception):
            hresult = -2147417848  # RPC_E_DISCONNECTED

        session = MagicMock()
        session.find_by_id.return_value.dump_tree.side_effect = _DisconnectedError("disconnected")
        with pytest.raises(_DisconnectedError):
            _read_visible_page_from_tree(session, "tbl", ["A"], 1, _flatten)

    def test_a_failing_dump_mid_scroll_falls_back_for_that_page_only(self) -> None:
        table = _FakeScrollingTable(row_count=6, visible=3, allow_cell_reads=True, failing_dump_call=2)
        session, flatten = _session_for(table)
        rows = read_table_control_all_rows(session, flatten)
        assert [r["C0"] for r in rows] == [f"r{i}c0" for i in range(6)]
        assert [r["C1"] for r in rows] == [f"r{i}c1" for i in range(6)]
        assert table.dump_calls == 2  # page one via the tree, page two failed and was read cell by cell
