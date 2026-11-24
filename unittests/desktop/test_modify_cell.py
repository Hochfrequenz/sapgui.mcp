"""Unit tests for sap_modify_cell on ALV grids (#1010), with a fake grid and session: no SAP."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.backend import desktop
from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import ModifyCellResult
from sapguimcp.tools.sap_tools import register_sap_tools

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_GRID_ID = "wnd[0]/usr/cntlGRID/shellcont/shell"


class _Grid:
    """Fake editable ALV grid. Rows outside ``loaded`` read blank until the grid is scrolled to them."""

    def __init__(
        self,
        rows: list[dict[str, str]],
        editable: frozenset[str] = frozenset({"PRICE", "SEATSMAX"}),
        loaded: set[int] | None = None,
        convert: Any = None,
        scroll_error: Exception | None = None,
    ) -> None:
        self.cells = [dict(r) for r in rows]
        self.row_count = len(rows)
        self.column_order = list(rows[0])
        self.editable = editable
        self.loaded = set(range(len(rows))) if loaded is None else loaded
        self.convert = convert or (lambda v: v)
        self.scroll_error = scroll_error
        self.writes: list[tuple[int, str, str]] = []
        self.on_write: Any = None
        self.write_error: Exception | None = None  # raised by modify_cell before the cell changes
        self.read_error: Exception | None = None  # raised by get_cell_value once set
        self.cell_types: dict[str, str] | None = {}  # None: GetCellType is not available
        self._first = 0

    @property
    def first_visible_row(self) -> int:
        return self._first

    @first_visible_row.setter
    def first_visible_row(self, value: int) -> None:
        if self.scroll_error is not None:
            raise self.scroll_error
        self._first = value
        self.loaded.update(range(value, value + 2))

    def get_cell_value(self, row: int, column: str) -> str:
        if self.read_error is not None:
            raise self.read_error
        return self.cells[row][column] if row in self.loaded else ""

    def get_cell_changeable(self, row: int, column: str) -> bool:
        return row in self.loaded and column in self.editable

    def get_cell_type(self, row: int, column: str) -> str:  # noqa: ARG002 - the COM signature
        if self.cell_types is None:
            raise AttributeError("GetCellType")
        return self.cell_types.get(column, "Normal")

    def modify_cell(self, row: int, column: str, value: str) -> None:
        self.writes.append((row, column, value))
        if self.write_error is not None:
            raise self.write_error
        self.cells[row][column] = self.convert(value)
        if self.on_write is not None:
            self.on_write()


def _rows(n: int = 3) -> list[dict[str, str]]:
    return [{"CARRID": "LH", "CONNID": f"{400 + i:04d}", "PRICE": f"{100 + i}.00", "SEATSMAX": "220"} for i in range(n)]


class _Session:
    def __init__(self, control: Any, type_number: int = 122) -> None:
        self.control = control
        self.popup = False
        self.sbar = SimpleNamespace(text="")
        elem = SimpleNamespace(type_as_number=type_number, id=_GRID_ID, children=[])
        self.wnd = SimpleNamespace(dump_tree=lambda: [elem])

    def find_by_id(self, element_id: str, raise_error: bool = True) -> Any:  # noqa: ARG002 - the COM signature
        routes = {"wnd[0]": self.wnd, "wnd[0]/sbar": self.sbar, _GRID_ID: self.control}
        if self.popup:
            routes["wnd[1]"] = SimpleNamespace(text="")
        return routes.get(element_id)


@pytest.fixture(autouse=True)
def _fake_grid_class(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop, "GuiGridView", _Grid)


async def _modify(session: _Session, *args: Any, **kwargs: Any) -> ModifyCellResult:
    backend = DesktopBackend.__new__(DesktopBackend)
    backend._session = session  # type: ignore[assignment]

    async def run(fn: Any, **_: Any) -> Any:
        return fn()

    backend.com = MagicMock()
    backend.com.run = run
    return await backend.modify_cell(*args, **kwargs)


def test_failure_needs_only_the_error() -> None:
    result = ModifyCellResult.failure("x")
    assert (result.success, result.written, result.row, result.value) == (False, False, 0, "")


@pytest.mark.anyio
async def test_writes_the_zero_based_row_and_reports_the_value_read_back() -> None:
    grid = _Grid(_rows())
    result = await _modify(_Session(grid), 2, "PRICE", "999.00")
    assert result.success, result.error
    assert grid.writes == [(1, "PRICE", "999.00")]
    assert (result.row, result.column, result.previous_value, result.value) == (2, "PRICE", "101.00", "999.00")
    assert result.written
    assert "Enter" in result.note


@pytest.mark.anyio
async def test_a_column_index_counts_displayed_columns_and_a_name_ignores_case() -> None:
    grid = _Grid(_rows())
    assert (await _modify(_Session(grid), 1, 3, "300")).column == "SEATSMAX"
    assert (await _modify(_Session(grid), 1, "price", "1.00")).column == "PRICE"
    assert grid.writes == [(0, "SEATSMAX", "300"), (0, "PRICE", "1.00")]


@pytest.mark.anyio
async def test_matching_expected_current_writes() -> None:
    grid = _Grid(_rows())
    result = await _modify(_Session(grid), 1, "PRICE", "5.00", expected_current=" 100.00 ")
    assert result.success, result.error
    assert grid.writes == [(0, "PRICE", "5.00")]


@pytest.mark.anyio
async def test_matching_expected_row_writes() -> None:
    grid = _Grid(_rows())
    result = await _modify(_Session(grid), 2, "PRICE", "5.00", expected_row={"carrid": "LH", "CONNID": " 0401 "})
    assert result.success, result.error
    assert grid.writes == [(1, "PRICE", "5.00")]


@pytest.mark.anyio
async def test_without_get_cell_type_a_cell_counts_as_text() -> None:
    grid = _Grid(_rows())
    grid.cell_types = None
    assert (await _modify(_Session(grid), 1, "PRICE", "5.00")).success


@pytest.mark.parametrize(
    ("row", "column", "kwargs", "message"),
    [
        (1, "PRICE", {"expected_current": "101.00"}, "PRICE holds '100.00', not '101.00'"),
        (1, "PRICE", {"expected_row": {"CONNID": "0401", "CARRID": "LH"}}, "CONNID holds '0400', not '0401'"),
        (1, "PRICE", {"expected_row": {"NOPE": "x"}}, "Column 'NOPE' not found"),
        (0, "PRICE", {}, "out of range"),
        (4, "PRICE", {}, "out of range"),
        (1, "CONNID", {}, "not editable"),
        (1, "NOPE", {}, "not found"),
        (1, "MANDT", {}, "not found"),  # a hidden column is not in column_order
        (1, 4, {}, "out of range"),
    ],
)
@pytest.mark.anyio
async def test_refusals_write_nothing(row: int, column: int | str, kwargs: dict[str, str], message: str) -> None:
    grid = _Grid(_rows())
    result = await _modify(_Session(grid), row, column, "1.00", **kwargs)
    assert not result.success
    assert not result.written
    assert message in (result.error or "")
    assert "No cell was modified" in (result.error or "")
    assert grid.writes == []


@pytest.mark.anyio
async def test_a_converted_value_is_a_failure_that_says_the_cell_changed() -> None:
    grid = _Grid(_rows(), convert=lambda _: "1.000,00")
    result = await _modify(_Session(grid), 1, "PRICE", "1000")
    assert not result.success
    assert result.written
    assert (result.previous_value, result.value) == ("100.00", "1.000,00")
    assert "'1.000,00'" in (result.error or "")


@pytest.mark.anyio
async def test_a_popup_after_the_write_is_reported() -> None:
    grid = _Grid(_rows())
    session = _Session(grid)
    grid.on_write = lambda: setattr(session, "popup", True)
    result = await _modify(session, 1, "PRICE", "7.00")
    assert result.success, result.error
    assert result.active_window == "wnd[1]"
    assert "wnd[1]" in result.note


@pytest.mark.anyio
async def test_a_new_status_message_after_the_write_is_reported() -> None:
    grid = _Grid(_rows())
    session = _Session(grid)
    grid.on_write = lambda: setattr(session.sbar, "text", "status-after-write")
    result = await _modify(session, 1, "PRICE", "7.00")
    assert result.success, result.error
    assert "status-after-write" in result.note


@pytest.mark.anyio
async def test_a_checkbox_cell_is_refused() -> None:
    grid = _Grid(_rows())
    grid.cell_types = {"PRICE": "CheckBox"}
    result = await _modify(_Session(grid), 1, "PRICE", "X")
    assert not result.success
    assert "CheckBox cell" in (result.error or "")
    assert grid.writes == []


@pytest.mark.anyio
async def test_a_value_sap_did_not_take_is_not_reported_as_written() -> None:
    grid = _Grid(_rows(), convert=lambda _: "100.00")
    result = await _modify(_Session(grid), 1, "PRICE", "abc")
    assert not result.success
    assert not result.written
    assert "still holds '100.00'" in (result.error or "")


@pytest.mark.anyio
async def test_a_failing_write_that_changed_the_cell_says_so() -> None:
    grid = _Grid(_rows())

    def _fail_after_the_change() -> None:
        raise OSError("rpc")

    grid.on_write = _fail_after_the_change
    result = await _modify(_Session(grid), 1, "PRICE", "5.00")
    assert not result.success
    assert result.written
    assert result.value == "5.00"
    assert "changed from '100.00' to '5.00'" in (result.error or "")


@pytest.mark.anyio
async def test_a_failing_write_that_left_the_cell_unchanged_does_not_claim_nothing_happened() -> None:
    grid = _Grid(_rows())
    grid.write_error = OSError("rpc")
    result = await _modify(_Session(grid), 1, "PRICE", "5.00")
    assert not result.success
    assert not result.written
    assert "unknown whether anything was written" in (result.error or "")
    assert "No cell was modified" not in (result.error or "")


@pytest.mark.anyio
async def test_a_failing_read_back_reports_the_cell_as_written() -> None:
    grid = _Grid(_rows())
    grid.on_write = lambda: setattr(grid, "read_error", OSError("gone"))
    result = await _modify(_Session(grid), 1, "PRICE", "5.00")
    assert not result.success
    assert result.written
    assert "could not be read back" in (result.error or "")


@pytest.mark.anyio
async def test_an_unloaded_row_is_scrolled_to_before_anything_is_read() -> None:
    grid = _Grid(_rows(), loaded={0})
    result = await _modify(_Session(grid), 3, "PRICE", "8.00", expected_current="102.00")
    assert result.success, result.error
    assert grid.first_visible_row == 2
    assert grid.writes == [(2, "PRICE", "8.00")]


@pytest.mark.anyio
async def test_a_failed_scroll_writes_nothing() -> None:
    grid = _Grid(_rows(), loaded={0}, scroll_error=OSError("busy"))
    result = await _modify(_Session(grid), 3, "PRICE", "8.00")
    assert not result.success
    assert "Could not scroll to row 3" in (result.error or "")
    assert grid.writes == []


@pytest.mark.anyio
async def test_a_table_control_is_refused() -> None:
    result = await _modify(_Session(object(), type_number=80), 1, 0, "x")
    assert not result.success
    assert "not supported yet" in (result.error or "")


@pytest.mark.anyio
async def test_no_grid_on_screen_is_refused() -> None:
    result = await _modify(_Session(object(), type_number=31), 1, 0, "x")
    assert not result.success
    assert "No ALV grid" in (result.error or "")


async def _call_tool(backend: Any) -> dict[str, Any]:
    server = FastMCP("t")
    register_sap_tools(server)
    with patch("sapguimcp.tools.sap_tools.get_backend", new=backend):
        async with Client(server) as client:
            raw = await client.call_tool(
                "sap_modify_cell", {"row": 2, "column": "PRICE", "value": "1"}, raise_on_error=False
            )
    return json.loads(raw.content[0].text)  # type: ignore[no-any-return]


@pytest.mark.anyio
async def test_the_tool_passes_its_arguments_to_the_backend() -> None:
    backend = MagicMock()
    backend.modify_cell = AsyncMock(return_value=ModifyCellResult(row=2, column="PRICE", value="1", written=True))
    data = await _call_tool(AsyncMock(return_value=backend))
    backend.modify_cell.assert_awaited_once_with(2, "PRICE", "1", None, None)
    assert data["success"] is True


@pytest.mark.anyio
async def test_the_tool_reports_a_backend_error_as_a_failure() -> None:
    backend = MagicMock()
    backend.modify_cell = AsyncMock(side_effect=RuntimeError("boom"))
    data = await _call_tool(AsyncMock(return_value=backend))
    assert data["success"] is False
    assert "boom" in data["error"]
    assert data["written"] is False


@pytest.mark.anyio
async def test_the_tool_reports_an_unknown_session_as_a_failure() -> None:
    data = await _call_tool(AsyncMock(side_effect=ValueError("no session s9")))
    assert data["success"] is False
    assert data["error"] == "no session s9"
