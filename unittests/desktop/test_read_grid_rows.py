"""Tests for reading ALV grid rows when SAP GUI has only transferred part of the result to the frontend (#928)."""

from __future__ import annotations

import pytest

from sapguimcp.backend.desktop import _read_grid_rows, _row_not_fully_loaded

_HEADERS = ["TCODE", "PGMNA"]


class _WindowedGrid:
    """Fake ALV grid: a fresh grid holds the first ``initial`` rows; after scrolling it holds ``window`` rows from the
    first visible row on. Cells outside read as blank, silently, like on SAP GUI (sapsucker#91). Rows in ``blank_rows``
    are genuinely blank."""

    def __init__(
        self,
        row_count: int,
        initial: int = 100,
        window: int = 80,
        blank_rows: frozenset[int] = frozenset(),
        partial_rows: frozenset[int] = frozenset(),
    ):
        self.row_count = row_count
        self.partial_rows = partial_rows
        self.initial = initial
        self.window = window
        self.blank_rows = blank_rows
        self.first_visible_row = 0
        self.scrolled_to: list[int] = []
        self._loaded: set[int] = set(range(min(initial, row_count)))

    def get_cell_value(self, row: int, column: str) -> str:
        if row in self.blank_rows:
            return ""
        if row not in self._loaded:
            if row in self.partial_rows:
                if column == _HEADERS[0]:
                    return f"{column}-{row}"  # the first column is already real
                return f"{' ' * 23}{row + 1:010d}{' ' * 40}"  # what SAP GUI returns for a cell it has not transferred
            return ""
        return f"{column}-{row}"

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if name == "first_visible_row" and "scrolled_to" in self.__dict__:
            self.scrolled_to.append(int(value))  # type: ignore[call-overload]
            # rows that were already transferred stay available
            self._loaded.update(range(int(value), min(int(value) + self.window, self.row_count)))  # type: ignore[call-overload]


def _expected(start: int, end: int) -> list[dict[str, object]]:
    return [{"row": r + 1, "data": {h: f"{h}-{r}" for h in _HEADERS}} for r in range(start, end)]


@pytest.mark.parametrize(
    ("initial", "window"),
    [(100, 50), (100, 60), (100, 78), (100, 80), (100, 100), (100, 130), (50, 30), (50, 20), (30, 10), (100, 1)],
)
def test_every_row_of_a_large_grid_is_read_whatever_the_loaded_window_size(initial: int, window: int) -> None:
    # (50, 30) and the like are the shape of a wide result: far fewer rows are loaded than for a narrow one (measured
    # live with a 30 column table). Assuming a fixed window size gave wrong rows there.
    grid = _WindowedGrid(row_count=1000, initial=initial, window=window)
    assert _read_grid_rows(grid, _HEADERS, 0, 1000) == _expected(0, 1000)


def test_a_grid_that_is_fully_loaded_is_not_scrolled() -> None:
    grid = _WindowedGrid(row_count=60, initial=100)
    assert _read_grid_rows(grid, _HEADERS, 0, 60) == _expected(0, 60)
    assert grid.scrolled_to == []


def test_the_first_miss_scrolls_to_exactly_that_row_and_the_rows_after_it_are_loaded_again() -> None:
    grid = _WindowedGrid(row_count=300, initial=100, window=80)
    _read_grid_rows(grid, _HEADERS, 0, 300)
    # a miss at row 100 scrolls there, the next one at 180 and 260; then the scroll position is restored
    assert grid.scrolled_to == [100, 180, 260, 0]


def test_a_subset_of_rows_is_read_with_one_based_row_numbers() -> None:
    grid = _WindowedGrid(row_count=1000)
    assert _read_grid_rows(grid, _HEADERS, 250, 260) == _expected(250, 260)


def test_a_genuinely_blank_row_stays_blank_and_does_not_stop_the_read() -> None:
    grid = _WindowedGrid(row_count=300, blank_rows=frozenset({150}))
    rows = _read_grid_rows(grid, _HEADERS, 0, 300)
    assert rows[150] == {"row": 151, "data": {"TCODE": "", "PGMNA": ""}}
    assert rows[:150] == _expected(0, 150)
    assert rows[151:] == _expected(151, 300)


def test_the_original_scroll_position_is_restored() -> None:
    grid = _WindowedGrid(row_count=400)
    grid.first_visible_row = 7
    _read_grid_rows(grid, _HEADERS, 0, 400)
    assert grid.first_visible_row == 7


def test_a_failing_restore_does_not_lose_the_rows() -> None:
    grid = _WindowedGrid(row_count=300)
    original_setattr = _WindowedGrid.__setattr__
    calls = {"n": 0}

    def _setattr(self: _WindowedGrid, name: str, value: object) -> None:
        if name == "first_visible_row":
            calls["n"] += 1
            if value == 0 and calls["n"] > 1:
                raise OSError("cannot scroll back")
        original_setattr(self, name, value)

    _WindowedGrid.__setattr__ = _setattr  # type: ignore[method-assign,assignment]
    try:
        assert _read_grid_rows(grid, _HEADERS, 0, 300) == _expected(0, 300)
    finally:
        _WindowedGrid.__setattr__ = original_setattr  # type: ignore[method-assign]


def test_a_grid_without_columns_does_not_scroll() -> None:
    grid = _WindowedGrid(row_count=5)
    assert _read_grid_rows(grid, [], 0, 5) == [{"row": r + 1, "data": {}} for r in range(5)]
    assert grid.scrolled_to == []


def test_rows_that_are_only_partially_loaded_show_a_row_number_placeholder_and_are_read_again() -> None:
    # The first rows after a loaded block come back with real first columns but placeholders in the later ones.
    grid = _WindowedGrid(row_count=300, partial_rows=frozenset({100, 180, 260}))
    assert _read_grid_rows(grid, _HEADERS, 0, 300) == _expected(0, 300)
    assert grid.scrolled_to[:3] == [100, 180, 260]


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"A": "", "B": ""}, True),  # nothing transferred
        ({"A": "  ", "B": "   "}, True),
        ({"A": "x", "B": f"{' ' * 23}{103:010d}{' ' * 40}"}, True),  # later column is the placeholder of row index 102
        ({"A": "x", "B": f"{103:010d}"}, True),
        ({"A": "x", "B": ""}, False),  # a genuinely empty cell next to real data
        ({"A": "x", "B": "0000000104"}, False),  # a number, but not this row's
        ({"A": "x", "B": "y"}, False),
    ],
)
def test_row_not_fully_loaded(data: dict[str, str], expected: bool) -> None:
    assert _row_not_fully_loaded(data, row_index=102) is expected


def test_genuine_data_that_equals_the_placeholder_is_returned_after_one_re_read() -> None:
    grid = _WindowedGrid(row_count=5)
    original = grid.get_cell_value
    grid.get_cell_value = lambda row, column: "0000000003" if (row, column) == (2, "PGMNA") else original(row, column)  # type: ignore[method-assign]
    rows = _read_grid_rows(grid, _HEADERS, 0, 5)
    assert rows[2]["data"]["PGMNA"] == "0000000003"
    assert grid.scrolled_to == [2, 0]  # one scroll to the row (one re-read, no loop), then the restore


class _ScrollFailsGrid(_WindowedGrid):
    """Scrolling to the given rows raises, like a COM error while the grid refreshes."""

    def __init__(self, *args: object, fail_scroll_to: frozenset[int] = frozenset(), **kwargs: object) -> None:
        self.fail_scroll_to = fail_scroll_to
        self.attempted_failing_scrolls: list[int] = []
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def __setattr__(self, name: str, value: object) -> None:
        if name == "first_visible_row" and "fail_scroll_to" in self.__dict__ and value in self.fail_scroll_to:
            self.attempted_failing_scrolls.append(int(value))  # type: ignore[call-overload]
            raise OSError("scroll failed")
        super().__setattr__(name, value)


def test_a_failing_scroll_keeps_the_first_read_and_the_read_goes_on() -> None:
    grid = _ScrollFailsGrid(row_count=300, fail_scroll_to=frozenset({100}))
    rows = _read_grid_rows(grid, _HEADERS, 0, 300)
    assert len(rows) == 300  # no exception, every row is returned
    assert rows[:100] == _expected(0, 100)
    assert rows[100] == {"row": 101, "data": {"TCODE": "", "PGMNA": ""}}  # the first read, as before the fix
    # the next row is scrolled to successfully: it and the rows after it are read correctly again
    assert rows[101:] == _expected(101, 300)
    assert 100 not in grid.scrolled_to  # the failed scroll was not recorded as done


def test_the_scroll_position_is_restored_when_reading_a_cell_fails_midway() -> None:
    class _CellFailsGrid(_WindowedGrid):
        def get_cell_value(self, row: int, column: str) -> str:
            if row == 150:
                raise OSError("COM error")
            return super().get_cell_value(row, column)

    grid = _CellFailsGrid(row_count=300)
    grid.first_visible_row = 7
    with pytest.raises(OSError, match="COM error"):
        _read_grid_rows(grid, _HEADERS, 0, 300)
    assert grid.first_visible_row == 7  # a scroll happened at row 100, the finally block put it back


def test_an_unreadable_scroll_position_does_not_stop_the_read() -> None:
    class _NoGetterGrid(_WindowedGrid):
        @property  # type: ignore[override]
        def first_visible_row(self) -> int:
            raise ValueError("not available")

        @first_visible_row.setter
        def first_visible_row(self, value: int) -> None:
            pass  # recording and loading happen in the base class' __setattr__

    grid = _NoGetterGrid.__new__(_NoGetterGrid)
    grid.__dict__.update(
        row_count=300, initial=100, window=80, blank_rows=frozenset(), partial_rows=frozenset(), scrolled_to=[]
    )
    grid.__dict__["_loaded"] = set(range(100))
    assert _read_grid_rows(grid, _HEADERS, 0, 300) == _expected(0, 300)
    assert grid.scrolled_to == [100, 180, 260]  # no restore, the position was never readable


def test_genuinely_blank_rows_each_cost_one_scroll_and_are_still_returned() -> None:
    # No row is assumed to be loaded just because it follows a scroll target: the cost is one scroll per blank row.
    grid = _WindowedGrid(row_count=130, blank_rows=frozenset(range(100, 130)))
    rows = _read_grid_rows(grid, _HEADERS, 0, 130)
    assert rows[:100] == _expected(0, 100)
    assert all(not any(row["data"].values()) for row in rows[100:])
    assert grid.scrolled_to == [*range(100, 130), 0]


def test_a_negative_start_row_is_never_scrolled_to() -> None:
    grid = _WindowedGrid(row_count=300)
    _read_grid_rows(grid, _HEADERS, -1, 2)
    assert -1 not in grid.scrolled_to


def test_scrolling_is_given_up_after_repeated_failures() -> None:
    grid = _ScrollFailsGrid(row_count=400, fail_scroll_to=frozenset(range(100, 400)))
    rows = _read_grid_rows(grid, _HEADERS, 0, 400)
    assert len(rows) == 400  # the read still returns every row (blank ones as read)
    assert grid.scrolled_to == []  # no scroll ever succeeded, nothing to restore
    assert grid.attempted_failing_scrolls == [100, 101, 102]  # three failed attempts, then no more
