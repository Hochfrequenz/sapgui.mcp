"""Tests for reading a GuiTableControl (e.g. the methods table of SE24), which only holds its visible window."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.backend.desktop import (
    DesktopBackend,
    _maximized_main_window,
    _read_table_control,
    _table_control_headers,
)

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


def test_truncated_is_set_only_if_requested_rows_are_missing_from_the_window() -> None:
    assert _read_table_control(_TableControl(32, 20), 1, None, 100)["truncated"] is True
    assert _read_table_control(_TableControl(32, 20), 1, 10, 100)["truncated"] is False
    assert _read_table_control(_TableControl(32, 20), 25, 30, 100)["truncated"] is True
    assert _read_table_control(_TableControl(5, 20, scrollbar=False), 1, None, 100)["truncated"] is False


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


def test_a_generated_header_never_clashes_with_a_title_that_looks_like_one() -> None:
    raw = SimpleNamespace(Columns=_Columns([("Text", "", "A"), ("Text", "", "B"), ("Text (2)", "", "C")]))
    headers = _table_control_headers(raw)
    assert len(set(headers)) == 3
    assert headers[:2] == ["Text", "Text (2)"]


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


class _Session:
    """Fake session with one window that holds the table control (``find_by_id`` of a modal window finds nothing)."""

    def __init__(self, table_control: _TableControl) -> None:
        self._table_control = table_control

    def find_by_id(self, element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            element = SimpleNamespace(id="/wnd[0]/usr/tbl", type_as_number=80, children=[])
            return SimpleNamespace(dump_tree=lambda: [element])
        if element_id == "/wnd[0]/usr/tbl":
            return self._table_control
        return None


@pytest.mark.anyio
async def test_read_table_returns_the_window_of_a_table_control_as_table_data() -> None:
    backend = DesktopBackend(com_thread=MagicMock())

    async def _run(function: Any, **_: Any) -> Any:
        return function()

    backend.com.run = _run  # type: ignore[method-assign]
    with patch.object(DesktopBackend, "require_session", return_value=_Session(_TableControl(32, 20, first=12))):
        data = await backend.read_table(start_row=1, max_rows=500)
    assert data.success
    assert data.headers == _HEADERS
    assert data.total_rows == 32
    assert (data.start_row, data.end_row) == (13, 32)
    assert [row.row for row in data.rows] == list(range(13, 33))
    assert data.rows[0].data == {"Method": "Method12", "Kind": "Kind12"}


@pytest.mark.anyio
async def test_read_table_of_a_range_outside_the_window_is_valid_table_data() -> None:
    backend = DesktopBackend(com_thread=MagicMock())

    async def _run(function: Any, **_: Any) -> Any:
        return function()

    backend.com.run = _run  # type: ignore[method-assign]
    with patch.object(DesktopBackend, "require_session", return_value=_Session(_TableControl(32, 20))):
        data = await backend.read_table(start_row=25, end_row=30)
    assert data.rows == []
    assert (data.start_row, data.end_row, data.total_rows) == (25, None, 32)


def test_a_blank_row_that_only_ends_the_requested_range_is_kept() -> None:
    tc = _TableControl(32, 20)
    original = tc.dump_tree

    def _blank_row_5() -> list[Any]:
        elements = original()
        for element in elements:
            if element.id.endswith(",4]"):
                element.text = ""
        return elements

    tc.dump_tree = _blank_row_5  # type: ignore[method-assign]
    rows = _read(tc, 0, 5)  # rows 1 to 5; row 5 is blank but not the end of the window
    assert [r["row"] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[4]["data"] == {"Method": "", "Kind": ""}


def test_the_final_row_of_a_table_that_fits_the_window_is_waited_for() -> None:
    tc = _TableControl(5, 20, scrollbar=False)
    original = tc.dump_tree
    reads = [0]

    def _last_row_late() -> list[Any]:
        elements = original()
        reads[0] += 1
        if reads[0] <= 2:  # the first reads show all but the final row
            for element in elements:
                if element.id.endswith(",4]"):
                    element.text = ""
        return elements

    tc.dump_tree = _last_row_late  # type: ignore[method-assign]
    assert _read(tc, 0, 5) == _expected(0, 5)


class _Window:
    def __init__(self, maximized: bool = False, fail: bool = False) -> None:
        self.Width, self.Height = (2576, 1408) if maximized else (1045, 901)
        self.fail = fail
        self.calls: list[str] = []

    def maximize(self) -> None:
        if self.fail:
            raise RuntimeError("COM error")
        self.calls.append("maximize")
        self.Width, self.Height = 2576, 1408

    def restore(self) -> None:
        self.calls.append("restore")
        self.Width, self.Height = 1045, 901


class _WindowSession:
    busy = False

    def __init__(self, window: _Window, grows: bool = True) -> None:
        self._window = window
        self._grows = grows

    def find_by_id(self, element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return self._window
        return SimpleNamespace(VisibleRowCount=40 if self._grows and self._window.Width > 2000 else 20)


_TABLE = "/app/con[0]/ses[0]/wnd[0]/usr/tbl"


def test_the_main_window_is_maximized_while_reading_and_restored_afterwards() -> None:
    window = _Window()
    with _maximized_main_window(_WindowSession(window), _TABLE):
        assert window.calls == ["maximize"]
    assert window.calls == ["maximize", "restore"]


def test_the_main_window_is_restored_if_reading_fails() -> None:
    window = _Window()
    with pytest.raises(ValueError, match="boom"), _maximized_main_window(_WindowSession(window), _TABLE):
        raise ValueError("boom")
    assert window.calls == ["maximize", "restore"]


def test_an_already_maximized_window_is_left_alone() -> None:
    window = _Window(maximized=True)
    with _maximized_main_window(_WindowSession(window), _TABLE):
        pass
    assert window.calls == ["maximize"]  # a no-op for SAP GUI: no restore, or the user's window would shrink


def test_a_popup_is_left_alone() -> None:
    window = _Window()
    with _maximized_main_window(_WindowSession(window), "/app/con[0]/ses[0]/wnd[1]/usr/tbl"):
        pass
    assert window.calls == []


def test_a_window_that_cannot_be_maximized_does_not_stop_reading_and_is_not_restored() -> None:
    window = _Window(fail=True)
    with _maximized_main_window(_WindowSession(window), _TABLE):
        pass
    assert window.calls == []


def test_a_control_that_does_not_grow_does_not_wait_for_the_full_timeout() -> None:
    window = _Window()
    started = time.monotonic()
    with _maximized_main_window(_WindowSession(window, grows=False), _TABLE):
        pass
    assert time.monotonic() - started < 1.5
    assert window.calls == ["maximize", "restore"]


def test_a_failing_restore_is_swallowed() -> None:
    window = _Window()
    window.restore = MagicMock(side_effect=RuntimeError("COM error"))  # type: ignore[method-assign]
    with _maximized_main_window(_WindowSession(window), _TABLE):
        pass


def test_a_window_is_restored_if_waiting_for_the_resize_fails_after_maximizing() -> None:
    window = _Window()
    session = _WindowSession(window)
    original = session.find_by_id
    calls = [0]

    def _find(element_id: str, **kwargs: Any) -> Any:
        if element_id == _TABLE:
            calls[0] += 1
            if calls[0] > 1:  # the first lookup is before maximizing, the one while waiting fails
                raise RuntimeError("COM error")
        return original(element_id, **kwargs)

    session.find_by_id = _find  # type: ignore[method-assign]
    with _maximized_main_window(session, _TABLE):
        pass
    assert window.calls == ["maximize", "restore"]


def test_restoring_waits_until_the_control_shows_its_former_number_of_lines() -> None:
    window = _Window()
    session = _WindowSession(window)
    original = session.find_by_id
    lines_after_restore = [40, 40, 20]  # the control is laid out again only after some polls
    reads: list[int] = []

    def _find(element_id: str, **kwargs: Any) -> Any:
        if element_id == _TABLE and window.calls[-1:] == ["restore"]:
            reads.append(1)
            return SimpleNamespace(VisibleRowCount=lines_after_restore[min(len(reads), 3) - 1])
        return original(element_id, **kwargs)

    session.find_by_id = _find  # type: ignore[method-assign]
    with _maximized_main_window(session, _TABLE):
        pass
    assert len(reads) == 3  # polled until the former number of lines showed, and not any more


def test_restoring_does_not_wait_for_the_full_timeout_if_the_control_shows_another_number_of_lines() -> None:
    window = _Window()
    session = _WindowSession(window)
    original = session.find_by_id

    def _find(element_id: str, **kwargs: Any) -> Any:
        if element_id == _TABLE and window.calls[-1:] == ["restore"]:
            return SimpleNamespace(VisibleRowCount=18)  # e.g. a snapped window: not the 20 lines of before
        return original(element_id, **kwargs)

    session.find_by_id = _find  # type: ignore[method-assign]
    started = time.monotonic()
    with _maximized_main_window(session, _TABLE):
        pass
    assert time.monotonic() - started < 1.5


def test_a_failing_layout_wait_after_a_successful_restore_is_logged_as_such(caplog: pytest.LogCaptureFixture) -> None:
    window = _Window()
    session = _WindowSession(window)
    original = session.find_by_id

    def _find(element_id: str, **kwargs: Any) -> Any:
        if element_id == _TABLE and window.calls[-1:] == ["restore"]:
            raise RuntimeError("COM error")
        return original(element_id, **kwargs)

    session.find_by_id = _find  # type: ignore[method-assign]
    with caplog.at_level("WARNING"), _maximized_main_window(session, _TABLE):
        pass
    assert window.calls == ["maximize", "restore"]
    assert "layout after restoring" in caplog.text
    assert "could not be restored" not in caplog.text
