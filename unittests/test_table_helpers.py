"""Unit tests for table_helpers — scroll-with-re-find logic for desktop table controls."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from sapguimcp.tools.table_helpers import (
    _find_table_control_info,
    _read_visible_page,
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
