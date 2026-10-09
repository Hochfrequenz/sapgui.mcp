"""Reading a columnar classic list (e.g. the SM37 job overview on SAP ERP 6.0) as a table."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sapguimcp.tools.classic_list_helpers import (
    read_classic_list_lines,
    read_classic_list_table,
    select_first_classic_list_entry,
)

_TITLES = ("Jobname", "Job name")
_USR = "/app/con[0]/ses[0]/wnd[0]/usr"


def _label(column: int, row: int, text: str) -> Any:
    return SimpleNamespace(id=f"{_USR}/lbl[{column},{row}]", text=text)


def _checkbox(row: int) -> Any:
    return SimpleNamespace(id=f"{_USR}/chk[1,{row}]", text="")


def _entry_row(row: int, name: str, status: str) -> list[Any]:
    return [
        _checkbox(row),
        _label(4, row, name),
        _label(37, row, ""),
        _label(51, row, "USER1"),
        _label(64, row, status),
    ]


def _header_row(row: int) -> list[Any]:
    return [
        _label(4, row, "Jobname"),
        _label(37, row, "Spool"),
        _label(51, row, "Job-Erstelle"),
        _label(64, row, "Status"),
    ]


class _Scrollbar:
    def __init__(self, maximum: int, page_size: int) -> None:
        self.maximum = maximum
        self.page_size = page_size
        self.position = 0


class _Usr:
    """The user area: ``pages`` maps a scroll position to the elements on screen there."""

    def __init__(self, pages: dict[int, list[Any]], scrollbar: _Scrollbar | None = None) -> None:
        self._pages = pages
        self.vertical_scrollbar = scrollbar

    def dump_tree(self) -> list[Any]:
        position = self.vertical_scrollbar.position if self.vertical_scrollbar is not None else 0
        return self._pages[position]


def _session(usr: _Usr) -> Any:
    return SimpleNamespace(find_by_id=lambda _element_id, **_: usr)


def test_reads_the_entries_below_the_header_by_column_and_skips_the_selection_and_summary_lines() -> None:
    elements = [
        _checkbox(5),  # the status selection above the header has checkboxes too
        _label(2, 5, "geplant"),
        *_header_row(10),
        *_entry_row(12, "JOB_A", "fertig"),
        *_entry_row(13, "JOB_B", "freigegeben"),
        _label(4, 36, "Zusammenfassung"),  # no checkbox: not an entry
    ]
    table = read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 200)
    assert table.headers == ["Jobname", "Spool", "Job-Erstelle", "Status"]
    assert [row.data for row in table.rows] == [
        {"Jobname": "JOB_A", "Spool": "", "Job-Erstelle": "USER1", "Status": "fertig"},
        {"Jobname": "JOB_B", "Spool": "", "Job-Erstelle": "USER1", "Status": "freigegeben"},
    ]
    assert table.total_rows == 2


def test_a_screen_without_a_list_header_is_an_empty_table() -> None:
    table = read_classic_list_table(_session(_Usr({0: [_label(0, 0, "Einfache Jobauswahl")]})), _TITLES, 200)
    assert table.headers == []
    assert table.rows == []


def test_the_header_is_recognised_ignoring_case() -> None:
    elements = [
        _label(4, 3, "JOB NAME"),
        _label(30, 3, "Status"),
        _checkbox(5),
        _label(4, 5, "JOB_A"),
        _label(30, 5, "x"),
    ]
    table = read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 200)
    assert [row.data for row in table.rows] == [{"JOB NAME": "JOB_A", "Status": "x"}]


def _tall_list_pages(
    first_entry_row: int, last_entry_row: int, visible_rows: int, positions: list[int]
) -> dict[int, Any]:
    """The pages of a list whose entries sit on the absolute rows ``first..last``, as seen at each scroll position.

    The window shows ``visible_rows`` rows, which can be fewer than the scrollbar's page size.
    """
    pages: dict[int, list[Any]] = {}
    for position in positions:
        elements: list[Any] = []
        if position == 0:
            elements += _header_row(2)
        for absolute in range(first_entry_row, last_entry_row + 1):
            row = absolute - position
            if 0 <= row < visible_rows:
                elements += _entry_row(row, f"JOB_{absolute}", "fertig")
        pages[position] = elements
    return pages


def test_a_list_taller_than_the_window_is_read_page_by_page_without_gaps_and_the_scrollbar_is_reset() -> None:
    # the scrollbar says 10 lines per page, the window shows 8 data rows: stepping by 10 would skip two lines
    scrollbar = _Scrollbar(maximum=14, page_size=10)
    pages = _tall_list_pages(4, 21, visible_rows=8, positions=[0, 6, 12, 14])
    table = read_classic_list_table(_session(_Usr(pages, scrollbar)), _TITLES, 200)
    assert [row.data["Jobname"] for row in table.rows] == [f"JOB_{i}" for i in range(4, 22)]
    assert scrollbar.position == 0


def test_at_most_max_rows_entries_are_returned() -> None:
    elements = [*_header_row(2), *(cell for row in range(4, 9) for cell in _entry_row(row, f"JOB_{row}", "fertig"))]
    table = read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 3)
    assert [row.data["Jobname"] for row in table.rows] == ["JOB_4", "JOB_5", "JOB_6"]


def test_a_list_that_starts_scrolled_is_read_from_its_top() -> None:
    scrollbar = _Scrollbar(maximum=10, page_size=10)
    scrollbar.position = 7  # the user left the list scrolled
    pages = {
        0: [*_header_row(2), *_entry_row(4, "JOB_1", "fertig")],
        6: [],
        7: [*_entry_row(4, "JOB_X", "fertig")],
        10: [*_entry_row(0, "JOB_2", "fertig")],
    }
    table = read_classic_list_table(_session(_Usr(pages, scrollbar)), _TITLES, 200)
    assert [row.data["Jobname"] for row in table.rows] == ["JOB_1", "JOB_2"]


def test_columns_with_the_same_title_are_kept_apart() -> None:
    elements = [
        _label(4, 2, "Jobname"),
        _label(20, 2, "Datum"),
        _label(35, 2, "Datum"),
        _checkbox(4),
        _label(4, 4, "JOB_A"),
        _label(20, 4, "01.10.2026"),
        _label(35, 4, "02.10.2026"),
    ]
    table = read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 200)
    assert table.headers == ["Jobname", "Datum", "Datum (2)"]
    assert table.rows[0].data == {"Jobname": "JOB_A", "Datum": "01.10.2026", "Datum (2)": "02.10.2026"}


def test_lines_are_read_cell_by_cell_joined_and_empty_ones_skipped() -> None:
    elements = [
        _label(0, 0, "Job-Log Uebersicht"),
        _label(0, 2, "08.10.2026"),
        _label(12, 2, "00:49:27"),
        _label(22, 2, "Job wurde gestartet"),
        _label(0, 3, "   "),  # only blanks: no line
    ]
    assert read_classic_list_lines(_session(_Usr({0: elements})), 100) == [
        "Job-Log Uebersicht",
        "08.10.2026 00:49:27 Job wurde gestartet",
    ]


def test_lines_of_a_tall_list_are_read_page_by_page_up_to_the_limit() -> None:
    def _pages() -> dict[int, list[Any]]:
        return {
            position: [
                _label(0, absolute - position, f"line {absolute}")
                for absolute in range(20)
                if 0 <= absolute - position < 8
            ]
            for position in (0, 6, 12, 14)
        }

    scrollbar = _Scrollbar(maximum=14, page_size=10)
    assert read_classic_list_lines(_session(_Usr(_pages(), scrollbar)), 100) == [f"line {i}" for i in range(20)]
    assert scrollbar.position == 0
    assert read_classic_list_lines(_session(_Usr(_pages(), _Scrollbar(maximum=14, page_size=10))), 3) == [
        "line 0",
        "line 1",
        "line 2",
    ]


def test_the_first_entry_below_the_header_is_ticked() -> None:
    ticked: list[str] = []

    class _Box:
        def __init__(self, element_id: str) -> None:
            self._id = element_id

        @property
        def selected(self) -> bool:
            return False

        @selected.setter
        def selected(self, _value: bool) -> None:
            ticked.append(self._id)

    elements = [
        _checkbox(5),  # above the header: the status selection
        _label(2, 5, "geplant"),
        *_header_row(10),
        *_entry_row(12, "JOB_A", "fertig"),
        *_entry_row(13, "JOB_B", "fertig"),
    ]
    usr = _Usr({0: elements})
    session = SimpleNamespace(
        find_by_id=lambda element_id, **_: usr if element_id == "wnd[0]/usr" else _Box(element_id)
    )
    assert select_first_classic_list_entry(session, _TITLES)
    assert ticked == [f"{_USR}/chk[1,12]"]
    assert not select_first_classic_list_entry(_session(_Usr({0: [_label(0, 0, "no list")]})), _TITLES)


def test_a_list_cut_at_the_row_limit_is_reported_as_truncated() -> None:
    scrollbar = _Scrollbar(maximum=14, page_size=10)
    pages = _tall_list_pages(4, 21, visible_rows=8, positions=[0, 6, 12, 14])
    table = read_classic_list_table(_session(_Usr(pages, scrollbar)), _TITLES, 5)
    assert len(table.rows) == 5
    assert table.truncated  # more pages (and more entries) were left unread


def test_a_list_that_fits_the_row_limit_is_not_truncated() -> None:
    elements = [*_header_row(2), *_entry_row(4, "JOB_1", "fertig"), *_entry_row(5, "JOB_2", "fertig")]
    assert not read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 2).truncated
    assert not read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 200).truncated


def test_a_page_with_more_entries_than_the_limit_is_truncated() -> None:
    elements = [*_header_row(2), *(cell for row in range(4, 9) for cell in _entry_row(row, f"JOB_{row}", "fertig"))]
    assert read_classic_list_table(_session(_Usr({0: elements})), _TITLES, 3).truncated


def test_a_multi_page_list_with_exactly_the_limit_ending_on_its_last_page_is_not_truncated() -> None:
    scrollbar = _Scrollbar(maximum=14, page_size=10)
    pages = _tall_list_pages(4, 21, visible_rows=8, positions=[0, 6, 12, 14])
    table = read_classic_list_table(_session(_Usr(pages, scrollbar)), _TITLES, 18)
    assert len(table.rows) == 18
    assert not table.truncated
