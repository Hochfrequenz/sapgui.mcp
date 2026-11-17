"""Desktop SE16N filter filling must survive the stale GuiTableControl proxy after a scroll (#988)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.tools.se16_tools import _fill_se16n_filters_desktop, _filter_fill_failure, _FilterFillResult

if TYPE_CHECKING:
    from collections.abc import Iterator

_HRESULT_STALE = -2147417851  # 0x80010105 (RPC_E_SERVERFAULT): what a stale proxy raised live; waiting never helps
_HRESULT_BUSY = -2147417846  # 0x8001010A (RPC_E_SERVERCALL_RETRYLATER)
_HRESULT_INVALID_ARGUMENT = -2147352567  # DISP_E_EXCEPTION: GetCell on a row beyond the data


class _ComError(Exception):
    def __init__(self, hresult: int) -> None:
        super().__init__(hresult, "com error")
        self.hresult = hresult


class _StaleAwareGrid:
    """Shared state of the SE16N selection grid; ``find_by_id`` hands out a new proxy per call.

    A proxy fetched before the last scroll raises on every access, as the live control does. After a scroll the
    first ``retrylater_reads`` name reads raise RETRYLATER, then ``partial_reads`` window reads come back
    half-refreshed (only the first row filled). A position beyond ``Maximum`` is ignored, as live.
    """

    def __init__(self, names: list[str], visible: int, start: int = 0, padding: int = 0) -> None:
        self.names = names
        self.row_count = len(names) + padding  # live: RowCount exceeds the data rows; those rows are unreadable
        self.visible = visible
        self.maximum = max(0, self.row_count - visible)
        self.position = start
        self.generation = 0
        self.values: dict[str, str] = {}
        self.position_writes: list[int] = []
        self.fail_scroll_at: int | None = None  # a write of this position raises
        self.fail_reset = False  # a write of position 0 raises
        self.retrylater_reads = 0
        self.settle_error_code = _HRESULT_BUSY
        self.partial_reads = 0
        self.broken_rows: set[int] = set()  # absolute rows whose name cell raises (not busy)
        self.blank_window_at: int | None = None  # every name read at this position raises (not busy)
        self.busy_writes = 0  # the first N value writes raise busy, without storing the value
        self.name_read_error: int | None = None  # a name read at name_read_error_at raises this code
        self.name_read_error_at: int | None = None
        self.landed_writes = 0  # the first N value writes store the value, then raise a server fault
        self.position_read_fails = False
        self.maximum_override: int | None = None
        self.transient_write_errors = 0  # the first N value writes raise DISP_E_EXCEPTION without storing
        self.ambiguous: set[str] = set()  # writes raise DISP_E_EXCEPTION although the cell is changeable
        self.flaky_row: int | None = None  # this absolute row raises DISP_E_EXCEPTION on its first reads ...
        self.flaky_reads = 0  # ... this many times, then reads normally
        self.unfillable: set[str] = set()  # listed by SE16N, but not offered for selection
        self._settle_reads = 0

    def find_by_id(self, _element_id: str, **_kwargs: Any) -> Any:
        return SimpleNamespace(com=_Proxy(self, self.generation))

    def read_name(self, row: int) -> str:
        idx = self.position + row
        if self.name_read_error is not None and self.position == self.name_read_error_at:
            raise _ComError(self.name_read_error)
        if idx == self.flaky_row and self.flaky_reads:
            self.flaky_reads -= 1
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        if idx in self.broken_rows or self.position == self.blank_window_at:
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        if idx >= len(self.names) and self.row_count > len(self.names):
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        name = self.names[idx] if idx < len(self.names) else ""
        if not self.generation:
            return name
        if self._settle_reads < self.retrylater_reads:
            self._settle_reads += 1
            raise _ComError(self.settle_error_code)
        if self._settle_reads < self.retrylater_reads + self.partial_reads:
            if row == self.visible - 1:
                self._settle_reads += 1
            return name if row == 0 else ""
        return name


class _Scrollbar:
    def __init__(self, proxy: _Proxy) -> None:
        self._proxy = proxy

    @property
    def Maximum(self) -> int:  # noqa: N802
        self._proxy.check()
        grid = self._proxy.grid
        return grid.maximum if grid.maximum_override is None else grid.maximum_override

    @property
    def Position(self) -> int:  # noqa: N802  (mirrors the SAP GUI COM attribute)
        self._proxy.check()
        if self._proxy.grid.position_read_fails:
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        return self._proxy.grid.position

    @Position.setter
    def Position(self, value: int) -> None:  # noqa: N802
        self._proxy.check()
        grid = self._proxy.grid
        grid.position_writes.append(value)
        if grid.fail_scroll_at == value or (value == 0 and grid.fail_reset):
            raise _ComError(_HRESULT_STALE)
        if 0 <= value <= grid.maximum and value != grid.position:
            grid.position = value
            grid.generation += 1
            grid._settle_reads = 0  # pylint: disable=protected-access


class _Cell:
    def __init__(self, proxy: _Proxy, name: str, text: str) -> None:
        self._proxy = proxy
        self._name = name
        self._text = text

    @property
    def Text(self) -> str:  # noqa: N802
        return self._text

    @property
    def Changeable(self) -> bool:  # noqa: N802
        self._proxy.check()
        return self._name not in self._proxy.grid.unfillable

    @Text.setter
    def Text(self, value: str) -> None:  # noqa: N802
        self._proxy.check()
        grid = self._proxy.grid
        if grid.busy_writes:
            grid.busy_writes -= 1
            raise _ComError(_HRESULT_BUSY)
        if grid.landed_writes:
            grid.landed_writes -= 1
            grid.values[self._name] = value
            raise _ComError(_HRESULT_STALE)
        if grid.transient_write_errors:
            grid.transient_write_errors -= 1
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        if self._name in grid.ambiguous:
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        if self._name in grid.unfillable:
            raise _ComError(_HRESULT_INVALID_ARGUMENT)
        self._proxy.grid.values[self._name] = value


class _Proxy:
    def __init__(self, grid: _StaleAwareGrid, generation: int) -> None:
        self.grid = grid
        self._generation = generation
        self.VerticalScrollbar = _Scrollbar(self)

    def check(self) -> None:
        if self._generation != self.grid.generation:
            raise _ComError(_HRESULT_STALE)

    @property
    def RowCount(self) -> int:  # noqa: N802
        self.check()
        return self.grid.row_count

    @property
    def VisibleRowCount(self) -> int:  # noqa: N802
        self.check()
        return self.grid.visible

    def GetCell(self, row: int, col: int) -> Any:  # noqa: N802
        self.check()
        if col == 6:
            name = self.grid.read_name(row)
            return _Cell(self, name, name)
        idx = self.grid.position + row
        name = self.grid.names[idx] if idx < len(self.grid.names) else ""
        return _Cell(self, name, self.grid.values.get(name, ""))


def _backend(grid: _StaleAwareGrid) -> MagicMock:
    backend = MagicMock(spec=DesktopBackend)
    session = MagicMock()
    session.find_by_id.side_effect = grid.find_by_id
    backend.require_session.return_value = session

    async def _run(fn: Any) -> Any:
        return fn()

    backend.com = SimpleNamespace(run=_run)
    return backend


@pytest.fixture(autouse=True)
def _no_sleep() -> Iterator[None]:
    with patch("sapguimcp.tools.se16_tools.time.sleep"):
        yield


_NAMES = [f"FLD{i:03d}" for i in range(97)]


@pytest.mark.anyio
async def test_field_below_the_fold_is_set_on_its_row() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)

    result = await _fill_se16n_filters_desktop(_backend(grid), {"fld090": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD090": "X"}
    assert grid.position == 0


@pytest.mark.anyio
async def test_not_found_lists_every_grid_name_and_resets_the_grid() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)

    result = await _fill_se16n_filters_desktop(_backend(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert result.other_errors == []
    assert result.offered_fields == _NAMES  # first and last name, not one window
    assert grid.position == 0


@pytest.mark.anyio
async def test_two_filters_top_and_below_the_fold_in_one_call() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD002": "A", "FLD080": "B", "FLD050": "C"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD002": "A", "FLD080": "B", "FLD050": "C"}
    assert grid.position == 0


@pytest.mark.anyio
async def test_scan_steps_by_pages_and_reaches_the_last_partial_page() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)  # maximum 91, not a multiple of 6

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD096": "X"})  # the last row

    assert result == _FilterFillResult()
    assert grid.values == {"FLD096": "X"}
    assert 91 in grid.position_writes
    assert len(grid.position_writes) <= 20  # about one write per page plus the reset, not one per row


@pytest.mark.anyio
async def test_scroll_error_is_reported_not_called_unapplied_and_the_grid_is_reset() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.fail_scroll_at = 18

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert "Scrolling the SE16N selection grid failed at position 18" in result.other_errors[0]
    assert grid.position == 0
    failure = _filter_fill_failure(result, "T", datetime.now(UTC))
    assert failure.error is not None
    assert "not available as SE16N selection criteria" not in failure.error
    assert "without being an SE16N selection field" not in failure.error


@pytest.mark.anyio
async def test_failed_reset_is_reported_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.fail_reset = True

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert grid.values == {"FLD090": "X"}  # the filter itself was applied
    assert result.unapplied_fields == []
    assert any("top" in e for e in result.other_errors)
    assert any(r.levelname == "WARNING" for r in caplog.records)


@pytest.mark.anyio
async def test_retrylater_after_a_scroll_is_retried() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.retrylater_reads = 3

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD090": "X"}


@pytest.mark.anyio
async def test_half_refreshed_window_is_waited_out() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.partial_reads = 3  # first row new, the rest still empty for the first reads after a scroll

    result = await _fill_se16n_filters_desktop(_backend(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == ["ZZZFAKE"]
    assert result.offered_fields == _NAMES  # no gaps from half-empty windows


@pytest.mark.anyio
async def test_window_that_never_settles_is_a_scan_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.retrylater_reads = 100_000

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert grid.position == 0


@pytest.mark.anyio
async def test_leaked_start_position_is_reset_first() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6, start=3)

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD001": "X"})  # above the leaked window

    assert result == _FilterFillResult()
    assert grid.values == {"FLD001": "X"}
    assert grid.position == 0


@pytest.mark.anyio
async def test_rows_beyond_the_data_are_not_an_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6, padding=14)  # live: RowCount 130 for 115 data rows

    found = await _fill_se16n_filters_desktop(_backend(grid), {"FLD096": "X"})
    missing = await _fill_se16n_filters_desktop(_backend(grid), {"ZZZFAKE": "X"})

    assert found == _FilterFillResult()
    assert grid.values == {"FLD096": "X"}
    assert missing.other_errors == []
    assert missing.offered_fields == _NAMES
    assert grid.position == 0


@pytest.mark.anyio
async def test_listed_field_that_takes_no_value_is_reported_as_not_offered() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.unfillable = {"FLD060"}

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD060": "X"})

    assert result.unapplied_fields == ["FLD060"]
    assert result.other_errors == []
    assert result.offered_fields == _NAMES
    assert grid.position == 0


@pytest.mark.anyio
async def test_unreadable_row_inside_the_data_is_a_scan_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.broken_rows = {50}

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert "cannot be read" in result.other_errors[0]
    assert grid.position == 0


@pytest.mark.anyio
async def test_window_unreadable_before_the_known_end_of_the_data_is_a_scan_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)  # last page at 91 overlaps the page at 90
    grid.blank_window_at = 91

    result = await _fill_se16n_filters_desktop(_backend(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == []  # the scan did not complete: no "not a selection field"
    assert len(result.other_errors) == 1
    assert grid.position == 0


@pytest.mark.anyio
async def test_failed_value_write_is_repeated_once_on_a_fresh_control() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.busy_writes = 1

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD090": "X"}


@pytest.mark.anyio
async def test_value_write_that_raised_but_landed_counts_as_applied() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.landed_writes = 1

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD090": "X"}
    assert grid.landed_writes == 0  # written once, not repeated


@pytest.mark.anyio
async def test_non_row_error_on_a_name_read_is_not_taken_for_the_end_of_the_data() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.name_read_error = -2147417848  # RPC_E_DISCONNECTED on the first row of a later window
    grid.name_read_error_at = 12

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert grid.position == 0


@pytest.mark.anyio
async def test_value_write_that_never_succeeds_is_an_error_not_an_unoffered_field() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.busy_writes = 100_000

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert "FLD090" in result.other_errors[0]


@pytest.mark.anyio
async def test_fully_visible_grid_never_reads_the_scroll_position() -> None:
    grid = _StaleAwareGrid(["MANDT", "MTEXT", "ORT01"], visible=8)
    grid.position_read_fails = True

    result = await _fill_se16n_filters_desktop(_backend(grid), {"MTEXT": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"MTEXT": "X"}


@pytest.mark.anyio
async def test_unreadable_scroll_position_of_a_scrollable_grid_is_a_scan_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.position_read_fails = True

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD001": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) >= 1
    assert "scroll position" in result.other_errors[0]


@pytest.mark.anyio
async def test_scrollable_grid_without_scroll_range_is_a_scan_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.maximum_override = 0

    result = await _fill_se16n_filters_desktop(_backend(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == []
    assert result.offered_fields == []
    assert "no scroll range" in result.other_errors[0]


@pytest.mark.anyio
async def test_window_with_a_blank_first_name_still_settles() -> None:
    names = list(_NAMES)
    names[48] = ""  # first row of the window at position 48
    grid = _StaleAwareGrid(names, visible=6)

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD060": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD060": "X"}


@pytest.mark.anyio
async def test_stale_proxy_error_retry_does_not_depend_on_the_com_thread_retry_set() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.retrylater_reads = 3
    grid.settle_error_code = _HRESULT_STALE

    with patch("sapguimcp.backend.desktop._com_thread.RETRYABLE_COM_ERRORS", frozenset()):
        result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD090": "X"}


@pytest.mark.anyio
async def test_transient_generic_write_error_is_retried_and_applied() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.transient_write_errors = 1

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD090": "X"}


@pytest.mark.anyio
async def test_generic_write_error_on_a_changeable_cell_is_an_error_not_an_unoffered_field() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.ambiguous = {"FLD090"}

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert "FLD090" in result.other_errors[0]
    assert grid.position == 0


@pytest.mark.anyio
async def test_read_back_tolerates_case_and_padding() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.landed_writes = 1

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD090": " x "})

    assert result == _FilterFillResult()


@pytest.mark.anyio
async def test_tail_that_is_only_transiently_unreadable_is_read_again() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6, padding=14)
    grid.flaky_row = 97 - 1 + 0  # the last data row: first window read says "unreadable", the re-read works
    grid.flaky_reads = 1

    result = await _fill_se16n_filters_desktop(_backend(grid), {"FLD096": "X"})

    assert result == _FilterFillResult()
    assert grid.values == {"FLD096": "X"}


@pytest.mark.anyio
async def test_unreadable_maximum_is_a_scan_error() -> None:
    grid = _StaleAwareGrid(_NAMES, visible=6)
    grid.maximum_override = "not a number"  # type: ignore[assignment]

    result = await _fill_se16n_filters_desktop(_backend(grid), {"ZZZFAKE": "X"})

    assert result.unapplied_fields == []
    assert len(result.other_errors) == 1
    assert "scroll maximum" in result.other_errors[0]
    assert grid.position == 0
