"""Live tests for sap_modify_cell on an editable ALV grid and a table control (#1010).

Targets: SAP's demo reports BCALV_EDIT_01, an ALV grid over SFLIGHT that is ready for input, shown in a dialog
window (wnd[1]), and BCALV_EDIT_02, whose key column CARRID is always read-only. Neither report has a save function,
so the edits never reach the database; the tests leave them without saving.

DEMO_DYNPRO_TABCONT_LOOP_AT shows the table control FLIGHTS over the rows of SPFLI, held only in an internal table
(it has no save function either). Its columns are output only until the function code TOGGLE makes the city columns
ready for input; the tests trigger TOGGLE where they need an editable column, and never DELETE. It holds more rows
than its window, so a write below the window scrolls.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest

from sapguimcp.backend.desktop import _active_window_id, _locate_table, _table_control_columns
from unittests.desktop.conftest import go_home, skip_no_sap

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_REPORT = "BCALV_EDIT_01"
_READ_ONLY_REPORT = "BCALV_EDIT_02"  # CARRID is disabled in every row
_NUMERIC_COLUMNS = ("SEATSMAX", "SEATSOCC", "PRICE")
_TABLE_CONTROL_REPORT = "DEMO_DYNPRO_TABCONT_LOOP_AT"
_TEXT_FIELDS = ("GuiTextField", "GuiCTextField")


async def _changeable_columns(backend: Any, headers: list[str]) -> dict[str, bool]:
    session = backend.require_session()

    def _read() -> dict[str, bool]:
        found = _locate_table(session)
        assert found is not None
        return {col: bool(found[0].get_cell_changeable(0, col)) for col in headers}

    result: dict[str, bool] = await backend.com.run(_read)
    return result


@asynccontextmanager
async def _report_grid(backend: Any, report: str) -> AsyncIterator[Any]:
    """Start ``report`` and leave it afterwards (F3, then F12 for a dialog that stays open), never saving."""
    await backend.enter_transaction("SA38")
    assert await backend.focus_and_type("RS38M-PROGRAMM", report)
    await backend.press_key("F8")
    await backend.wait_for_ready()
    assert await backend.wait_for_condition(lambda s: _locate_table(s) is not None), f"{report} shows no grid"
    try:
        yield backend
    finally:
        await go_home(backend)
        session = backend.require_session()
        for _ in range(3):
            if await backend.com.run(lambda: _active_window_id(session)) == "wnd[0]":
                break
            await backend.press_key("F12")
        await backend.enter_transaction("/n")


@pytest.fixture
async def edit_grid(backend: Any) -> AsyncIterator[Any]:
    async with _report_grid(backend, _REPORT) as grid_backend:
        yield grid_backend


@skip_no_sap
@pytest.mark.anyio
async def test_edit_a_cell_read_it_back_and_refuse_a_stale_row(edit_grid: Any) -> None:
    backend = edit_grid
    table = await backend.read_table(max_rows=100)
    assert table.success, table.error
    assert table.total_rows >= 2
    changeable = await _changeable_columns(backend, table.headers)
    col = next((c for c in _NUMERIC_COLUMNS if changeable.get(c)), None)
    assert col is not None, f"none of {_NUMERIC_COLUMNS} is editable in row 1: {changeable}"
    before = table.rows[0].data[col].strip()
    other_row_value = table.rows[1].data[col].strip()
    new = "123" if before != "123" else "124"

    # A value read from another row (or a stale read) refuses the write and changes nothing.
    stale = other_row_value if other_row_value != before else before + "9"
    refused = await backend.modify_cell(1, col, new, expected_current=stale)
    assert not refused.success
    assert not refused.written
    assert (await backend.read_table(max_rows=1)).rows[0].data[col].strip() == before

    # The key columns of another row (a row that moved) refuse the write as well.
    keys = ("CARRID", "CONNID", "FLDATE")
    row2_keys = {k: table.rows[1].data[k] for k in keys}
    refused = await backend.modify_cell(1, col, new, expected_row=row2_keys)
    assert not refused.success
    assert not refused.written

    row1_keys = {k: table.rows[0].data[k] for k in keys}
    result = await backend.modify_cell(1, col, new, expected_current=before, expected_row=row1_keys)
    assert result.success, result.error
    assert result.written
    assert (result.previous_value, result.value, result.column) == (before, new, col)

    after = await backend.read_table(max_rows=100)
    assert after.rows[0].data[col].strip() == new
    assert [r.data for r in after.rows[1:]] == [r.data for r in table.rows[1:]], "another row changed"

    out_of_range = await backend.modify_cell(table.total_rows + 1, col, new)
    assert not out_of_range.success
    assert not out_of_range.written


@skip_no_sap
@pytest.mark.anyio
async def test_a_cell_that_is_not_editable_is_refused(backend: Any) -> None:
    async with _report_grid(backend, _READ_ONLY_REPORT):
        table = await backend.read_table(max_rows=1)
        assert table.success, table.error
        col = "CARRID"
        assert (await _changeable_columns(backend, [col]))[col] is False
        before = table.rows[0].data[col]

        result = await backend.modify_cell(1, col, "X")
        assert not result.success
        assert not result.written
        assert "not editable" in (result.error or "")
        assert (await backend.read_table(max_rows=1)).rows[0].data[col] == before


def _raw_table_control(session: Any) -> Any:
    found = _locate_table(session)
    assert found is not None
    assert found[1] == "GuiTableControl", f"{_TABLE_CONTROL_REPORT} shows a {found[1]}"
    return getattr(found[0], "com", getattr(found[0], "_com", found[0]))


async def _table_control_columns_live(backend: Any) -> tuple[list[tuple[str, str, bool]], int]:
    """``(header, cell type, changeable)`` of each column on the window's first line, and ``VisibleRowCount``."""
    session = backend.require_session()

    def _read() -> tuple[list[tuple[str, str, bool]], int]:
        raw = _raw_table_control(session)
        columns = _table_control_columns(raw)
        cells = [raw.GetCell(0, i) for i in range(len(columns))]
        described = [(h, str(c.Type), bool(c.Changeable)) for (h, _), c in zip(columns, cells, strict=True)]
        return described, int(raw.VisibleRowCount)

    result: tuple[list[tuple[str, str, bool]], int] = await backend.com.run(_read)
    return result


async def _table_control_round_trip(backend: Any, action: Any) -> None:
    """Run ``action(session, raw control)`` on the COM thread, then wait until SAP is idle again."""
    session = backend.require_session()
    await backend.com.run(lambda: action(session, _raw_table_control(session)))
    await backend.wait_for_ready()


def _scroll_to_top(_: Any, raw: Any) -> None:
    raw.VerticalScrollbar.Position = 0


@pytest.fixture
async def flights(backend: Any) -> AsyncIterator[Any]:
    async with _report_grid(backend, _TABLE_CONTROL_REPORT) as tc_backend:
        yield tc_backend


def _toggle_input(session: Any, _: Any) -> None:
    session.find_by_id("wnd[0]/tbar[0]/okcd").text = "TOGGLE"  # lang-ok: function code of the demo report
    session.find_by_id("wnd[0]").send_v_key(0)


async def _editable_text_column(backend: Any) -> tuple[str, int]:
    """Make the demo's city columns ready for input (TOGGLE), then return the first editable text column."""
    await _table_control_round_trip(backend, _toggle_input)
    columns, visible = await _table_control_columns_live(backend)
    header = next((h for h, kind, changeable in columns if changeable and kind in _TEXT_FIELDS), None)
    assert header is not None, f"no editable text column: {columns}"
    return header, visible


@skip_no_sap
@pytest.mark.anyio
async def test_table_control_write_below_the_window_changes_only_that_row(flights: Any) -> None:
    backend = flights
    col, visible = await _editable_text_column(backend)
    top = await backend.read_table(max_rows=100)
    assert top.success, top.error
    target = min(top.total_rows, visible + 3)
    assert target > visible, f"the control holds {top.total_rows} rows, not more than its {visible}-line window"

    def _scroll_to(position: int) -> Any:
        def _scroll(_: Any, raw: Any) -> None:
            raw.VerticalScrollbar.Position = position

        return _scroll

    # Read the target row's window (read_table numbers rows absolutely), then go back to the top.
    await _table_control_round_trip(backend, _scroll_to(target - 1))
    below = await backend.read_table(max_rows=100)
    assert below.success, below.error
    target_data = next(r.data for r in below.rows if r.row == target)
    await _table_control_round_trip(backend, _scroll_to(0))

    old = target_data[col].strip()
    # A value another row holds passes the field's input checks when the screen is processed again.
    new = next(r.data[col].strip() for r in top.rows if r.data[col].strip() not in ("", old))

    result = await backend.modify_cell(target, col, new, expected_row=dict(target_data))
    assert result.success, result.error
    assert result.written
    assert result.scrolled
    assert result.table_type == "GuiTableControl"
    assert (result.column, result.previous_value, result.value) == (col, old, new)

    after_below = {r.row: r.data for r in (await backend.read_table(max_rows=100)).rows}
    assert after_below[target][col].strip() == new
    changed = [r.row for r in below.rows if r.row != target and r.row in after_below and after_below[r.row] != r.data]
    assert changed == [], f"other rows changed: {changed}"
    await _table_control_round_trip(backend, _scroll_to(0))
    assert [r.data for r in (await backend.read_table(max_rows=100)).rows] == [r.data for r in top.rows]


@skip_no_sap
@pytest.mark.anyio
async def test_table_control_refuses_a_moved_row_an_empty_line_and_a_row_out_of_range(flights: Any) -> None:
    backend = flights
    col, _ = await _editable_text_column(backend)
    columns, _ = await _table_control_columns_live(backend)
    before = await backend.read_table(max_rows=100)
    assert before.success, before.error
    first = dict(before.rows[0].data)

    # SORT_DOWN sorts the rows descending by the selected column: row 1 then holds another record.
    col_index = [h for h, _, _ in columns].index(col)

    def _sort_down(session: Any, raw: Any) -> None:
        raw.Columns(col_index).Selected = True
        session.find_by_id("wnd[0]/tbar[0]/okcd").text = "SORT_DOWN"  # lang-ok: function code
        session.find_by_id("wnd[0]").send_v_key(0)

    await _table_control_round_trip(backend, _sort_down)
    sorted_table = await backend.read_table(max_rows=100)
    assert sorted_table.success, sorted_table.error
    assert sorted_table.rows[0].data != first, "SORT_DOWN did not move row 1: the test cannot check a moved row"

    refused = await backend.modify_cell(1, col, first[col].strip(), expected_row=first)
    assert not refused.success
    assert not refused.written
    assert "not the expected row" in (refused.error or "")

    empty_line = await backend.modify_cell(sorted_table.total_rows + 1, col, "X")
    assert not empty_line.success
    assert not empty_line.written
    assert "empty line" in (empty_line.error or "") or "out of range" in (empty_line.error or "")

    out_of_range = await backend.modify_cell(10_000, col, "X", allow_empty_row=True)
    assert not out_of_range.success
    assert not out_of_range.written
    assert "out of range" in (out_of_range.error or "")

    # None of the refusals scrolled (the empty line is refused before scrolling) or changed a row.
    assert [r.data for r in (await backend.read_table(max_rows=100)).rows] == [r.data for r in sorted_table.rows]


@skip_no_sap
@pytest.mark.anyio
async def test_table_control_refuses_a_read_only_cell(flights: Any) -> None:
    backend = flights
    columns, _ = await _table_control_columns_live(backend)
    col = next((h for h, kind, changeable in columns if not changeable and kind in _TEXT_FIELDS), None)
    assert col is not None, f"no read-only text column: {columns}"
    before = await backend.read_table(max_rows=1)

    result = await backend.modify_cell(1, col, "X")
    assert not result.success
    assert not result.written
    assert "not editable" in (result.error or "")
    assert (await backend.read_table(max_rows=1)).rows[0].data == before.rows[0].data
