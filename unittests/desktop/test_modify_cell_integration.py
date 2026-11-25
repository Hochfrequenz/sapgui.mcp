"""Live tests for sap_modify_cell on an editable ALV grid (#1010).

Targets: SAP's demo reports BCALV_EDIT_01, an ALV grid over SFLIGHT that is ready for input, shown in a dialog
window (wnd[1]), and BCALV_EDIT_02, whose key column CARRID is always read-only. Neither report has a save function,
so the edits never reach the database; the tests leave them without saving.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest

from sapguimcp.backend.desktop import _active_window_id, _locate_table
from unittests.desktop.conftest import go_home, skip_no_sap

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_REPORT = "BCALV_EDIT_01"
_READ_ONLY_REPORT = "BCALV_EDIT_02"  # CARRID is disabled in every row
_NUMERIC_COLUMNS = ("SEATSMAX", "SEATSOCC", "PRICE")


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
