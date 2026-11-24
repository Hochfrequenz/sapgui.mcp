"""Unit tests for sap_modify_cell on a classic table control (#1010, part 1b), with a fake control: no SAP."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from sapguimcp.backend import desktop
from sapguimcp.backend.desktop import (
    DesktopBackend,
    _cell_header,
    _resolve_table_control_column,
    _table_control_row_total,
)

if TYPE_CHECKING:
    from sapguimcp.models import ModifyCellResult

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

_TC_ID = "wnd[0]/usr/tblDEMOFLIGHTS"
# (title, technical name, cell type)
_COLUMNS = [
    ("Mark", "DEMO-MARK", "GuiCheckBox"),
    ("Airline", "DEMO-CARRID", "GuiCTextField"),
    ("Flight", "DEMO-CONNID", "GuiTextField"),
    ("From", "DEMO-CITYFROM", "GuiTextField"),
]


class _Scrollbar:
    def __init__(self, tc: _TableControl) -> None:
        self._tc = tc
        self.writes: list[int] = []

    @property
    def Position(self) -> int:  # noqa: N802 - COM name
        return self._tc.top

    @Position.setter
    def Position(self, value: int) -> None:  # noqa: N802 - COM name
        self.writes.append(value)
        if self._tc.scroll_error is not None:
            raise self._tc.scroll_error
        self._tc.top = self._tc.shown_top(value)
        self._tc.generation += 1  # SAP GUI rebuilds the control: references taken before are dead
        self._tc.on_scroll()

    @property
    def Maximum(self) -> int:  # noqa: N802 - COM name
        return self._tc.RowCount - self._tc.VisibleRowCount


class _Cell:
    def __init__(self, tc: _TableControl, row0: int, col: int, line: int) -> None:
        self._tc, self._row0, self._col = tc, row0, col
        claimed_col, claimed_line = tc.id_override.get((col, line), (col, line))
        field = _COLUMNS[claimed_col][1]
        self.Id = f"/app/con[0]/ses[0]/{_TC_ID}/txt{field}[{claimed_col},{claimed_line}]"
        self.Type = _COLUMNS[col][2]
        self.Changeable = _COLUMNS[col][1] in tc.editable

    @property
    def Text(self) -> str:  # noqa: N802 - COM name
        return self._tc.text(self._row0, self._col)

    @Text.setter
    def Text(self, value: str) -> None:  # noqa: N802 - COM name
        self._tc.writes.append((self._row0, _COLUMNS[self._col][1], value))
        while len(self._tc.data) <= self._row0:
            self._tc.data.append(dict.fromkeys((name for _, name, _ in _COLUMNS), ""))
        self._tc.data[self._row0][_COLUMNS[self._col][1]] = self._tc.convert(value)


class _TableControl:
    """Fake padded table control (RowCount = rows + VisibleRowCount - 1) whose window starts at ``top``."""

    def __init__(self, rows: int = 12, visible: int = 5) -> None:
        self.data = [
            {"DEMO-MARK": "", "DEMO-CARRID": "LH", "DEMO-CONNID": f"{400 + i:04d}", "DEMO-CITYFROM": f"CITY{i}"}
            for i in range(rows)
        ]
        self.RowCount = rows + visible - 1
        self.VisibleRowCount = visible
        self.top = 0
        self.generation = 0
        self.VerticalScrollbar = _Scrollbar(self)
        self.Columns = _Columns(self)
        self.convert: Any = lambda value: value  # what SAP GUI makes of a value written into a cell
        self.editable = {"DEMO-MARK", "DEMO-CARRID", "DEMO-CONNID"}
        self.writes: list[tuple[int, str, str]] = []
        self.scroll_error: Exception | None = None
        self.shown_top = lambda requested: min(requested, self.RowCount - self.VisibleRowCount)
        self.on_scroll: Any = lambda: None
        self.id_override: dict[tuple[int, int], tuple[int, int]] = {}  # (col, line) -> (col, line) the cell id claims
        self.last_line_partly_visible = False
        self.on_dump: Any = lambda: None  # e.g. SAP correcting the scroll position while the window settles
        self.on_get_cell: Any = lambda _line, _col: None

    def column(self, index: int) -> Any:
        title, name, _ = _COLUMNS[index]
        return SimpleNamespace(Title=title, Name=name)

    def text(self, row0: int, col: int) -> str:
        return self.data[row0][_COLUMNS[col][1]] if row0 < len(self.data) else ""

    def dump_tree(self) -> list[Any]:
        self.on_dump()
        elements = []
        for line in range(self.VisibleRowCount):
            partly = self.last_line_partly_visible and line == self.VisibleRowCount - 1
            for col, (_, name, _) in enumerate(_COLUMNS):
                text = "" if partly else self.text(self.top + line, col)
                elements.append(SimpleNamespace(id=f"{_TC_ID}/txt{name}[{col},{line}]", text=text, children=[]))
        return elements

    def GetCell(self, line: int, col: int) -> _Cell:  # noqa: N802 - COM name
        self.on_get_cell(line, col)
        return _Cell(self, self.top + line, col, line)


class _Handle:
    """What ``find_by_id`` returns: a reference that dies when the control is rebuilt by a scroll."""

    def __init__(self, tc: _TableControl) -> None:
        self._tc = tc
        self._generation = tc.generation
        self.com = self

    def __getattr__(self, name: str) -> Any:
        if self._generation != self._tc.generation:
            raise OSError("stale reference to the table control")
        return getattr(self._tc, name)


class _Columns:
    def __init__(self, tc: _TableControl) -> None:
        self._tc = tc
        self.Count = len(_COLUMNS)

    def __call__(self, index: int) -> Any:
        return self._tc.column(index)


class _Session:
    def __init__(self, tc: _TableControl) -> None:
        self.tc = tc
        self.busy = False
        self.popup = False
        self.sbar = SimpleNamespace(text="")
        elem = SimpleNamespace(type_as_number=80, id=_TC_ID, children=[])
        self.wnd = SimpleNamespace(dump_tree=lambda: [elem])

    def find_by_id(self, element_id: str, raise_error: bool = True) -> Any:  # noqa: ARG002 - the COM signature
        if element_id == _TC_ID:
            return _Handle(self.tc)
        routes = {"wnd[0]": self.wnd, "wnd[0]/sbar": self.sbar}
        if self.popup:
            routes["wnd[1]"] = SimpleNamespace(text="")
        return routes.get(element_id)


async def _modify(session: _Session, *args: Any, **kwargs: Any) -> ModifyCellResult:
    backend = DesktopBackend.__new__(DesktopBackend)
    backend._session = session  # type: ignore[assignment]

    async def run(fn: Any, **_: Any) -> Any:
        return fn()

    backend.com = MagicMock()
    backend.com.run = run
    return await backend.modify_cell(*args, **kwargs)


def _refused(result: ModifyCellResult, tc: _TableControl, message: str) -> None:
    assert not result.success
    assert not result.written
    assert message in (result.error or ""), result.error
    assert "No cell was modified" in (result.error or "")
    assert tc.writes == []


@pytest.mark.anyio
async def test_a_row_in_the_window_is_written_without_scrolling() -> None:
    tc = _TableControl()
    result = await _modify(_Session(tc), 3, "Airline", "UA")
    assert result.success, result.error
    assert tc.VerticalScrollbar.writes == []
    assert tc.writes == [(2, "DEMO-CARRID", "UA")]
    assert (result.table_type, result.scrolled, result.column) == ("GuiTableControl", False, "Airline")
    assert (result.previous_value, result.value) == ("LH", "UA")
    assert "Enter" in result.note


@pytest.mark.anyio
async def test_a_row_below_the_window_is_scrolled_to_the_top_and_written() -> None:
    tc = _TableControl()
    result = await _modify(_Session(tc), 9, "DEMO-CONNID", "0999", expected_current="0408")
    assert result.success, result.error
    assert tc.VerticalScrollbar.writes == [8]
    assert tc.writes == [(8, "DEMO-CONNID", "0999")]
    assert result.scrolled
    assert [row["DEMO-CONNID"] for row in tc.data] == [f"{400 + i:04d}" for i in range(8)] + ["0999"] + [
        f"{400 + i:04d}" for i in range(9, 12)
    ]


@pytest.mark.anyio
async def test_the_window_line_comes_from_the_position_read_after_the_scroll() -> None:
    tc = _TableControl()
    tc.shown_top = lambda _: 6  # the application puts row 7 on top, not the requested row 9
    result = await _modify(_Session(tc), 9, "Airline", "UA")
    assert result.success, result.error
    assert tc.writes == [(8, "DEMO-CARRID", "UA")]


@pytest.mark.anyio
async def test_a_row_still_outside_the_window_after_the_scroll_is_refused() -> None:
    tc = _TableControl()
    tc.shown_top = lambda _: 2  # rows 3 to 7 are shown, row 9 is not
    result = await _modify(_Session(tc), 9, "Airline", "UA")
    _refused(result, tc, "could not be brought into view; the table control now shows rows 3 to 7")
    assert result.scrolled


@pytest.mark.anyio
async def test_the_status_bar_explains_a_row_the_scroll_did_not_reach() -> None:
    tc = _TableControl()
    session = _Session(tc)
    tc.shown_top = lambda _: 0  # an input check of the screen stopped the scroll

    def _blocked() -> None:
        session.sbar.text = "input-check-error"

    tc.on_scroll = _blocked
    _refused(await _modify(session, 9, "Airline", "UA"), tc, "Status bar: input-check-error")


@pytest.mark.anyio
async def test_the_scroll_position_changing_while_the_window_settles_is_refused() -> None:
    tc = _TableControl()
    reads = []

    def _move_on_second_read() -> None:
        reads.append(1)
        if len(reads) == 2:
            tc.top = 1  # GetCell(line 2) would now address row 4, not row 3

    tc.on_dump = _move_on_second_read
    _refused(await _modify(_Session(tc), 3, "Airline", "UA"), tc, "moved from row 1 to row 2")


@pytest.mark.anyio
async def test_the_scroll_position_changing_before_the_write_is_refused() -> None:
    tc = _TableControl()

    def _move_after_the_cell_was_found(_line: int, _col: int) -> None:
        tc.top = 1

    tc.on_get_cell = _move_after_the_cell_was_found
    _refused(await _modify(_Session(tc), 3, "Airline", "UA"), tc, "moved from row 1 to row 2")


@pytest.mark.anyio
async def test_a_row_that_is_an_empty_line_after_the_scroll_is_refused() -> None:
    tc = _TableControl()

    def _rows_removed() -> None:  # the screen's processing removed rows: row 10 is an empty line now
        del tc.data[8:]
        tc.RowCount = 8 + tc.VisibleRowCount - 1
        tc.top = min(tc.top, 7)  # the last row can be scrolled to the top, no further

    tc.on_scroll = _rows_removed
    result = await _modify(_Session(tc), 10, "Airline", "UA")
    _refused(result, tc, "Row 10 is an empty line after the table control's last row (8)")
    assert result.scrolled


@pytest.mark.anyio
async def test_an_expected_column_without_a_cell_is_refused() -> None:
    tc = _TableControl()

    def _no_cell_in_from(_line: int, col: int) -> None:
        if col == 3:
            raise OSError("DISP_E_EXCEPTION")

    tc.on_get_cell = _no_cell_in_from
    result = await _modify(_Session(tc), 2, "Airline", "UA", expected_row={"From": ""})
    _refused(result, tc, "Column From has no cell in row 2")


@pytest.mark.anyio
async def test_a_failing_scroll_is_not_retried_and_writes_nothing() -> None:
    tc = _TableControl()
    tc.scroll_error = OSError("RPC_E_SERVERFAULT")
    result = await _modify(_Session(tc), 9, "Airline", "UA")
    _refused(result, tc, "Could not scroll the table control to row 9")
    assert tc.VerticalScrollbar.writes == [8]
    assert result.scrolled  # the scroll may have reached SAP before the error


@pytest.mark.anyio
async def test_a_popup_opened_by_the_scroll_stops_the_write() -> None:
    tc = _TableControl()
    session = _Session(tc)
    tc.on_scroll = lambda: setattr(session, "popup", True)
    _refused(await _modify(session, 9, "Airline", "UA"), tc, "opened window wnd[1]")


@pytest.mark.anyio
async def test_a_session_still_busy_after_the_scroll_stops_the_write(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop, "_SCROLL_IDLE_TIMEOUT_S", 0.05)
    tc = _TableControl()
    session = _Session(tc)
    tc.on_scroll = lambda: setattr(session, "busy", True)
    _refused(await _modify(session, 9, "Airline", "UA"), tc, "still busy")


@pytest.mark.anyio
async def test_a_blank_last_window_line_is_scrolled_to_the_top_first() -> None:
    tc = _TableControl()
    tc.last_line_partly_visible = True  # row 5 is on the last line and reads blank
    result = await _modify(_Session(tc), 5, "Airline", "UA")
    assert result.success, result.error
    assert tc.VerticalScrollbar.writes == [4]
    assert tc.writes == [(4, "DEMO-CARRID", "UA")]


@pytest.mark.anyio
async def test_an_empty_line_after_the_last_row_needs_allow_empty_row() -> None:
    tc = _TableControl()
    _refused(await _modify(_Session(tc), 13, "Airline", "UA"), tc, "allow_empty_row=True")
    result = await _modify(_Session(tc), 13, "Airline", "UA", allow_empty_row=True)
    assert result.success, result.error
    assert tc.writes == [(12, "DEMO-CARRID", "UA")]


@pytest.mark.parametrize(
    ("row", "column", "kwargs", "message"),
    [
        (0, "Airline", {}, "out of range"),
        (17, "Airline", {"allow_empty_row": True}, "out of range: the table control has 12 row(s)"),
        (2, "Mark", {}, "is a GuiCheckBox; only text fields"),
        (2, "From", {}, "not editable"),
        (2, "Nope", {}, "Column 'Nope' not found"),
        (2, 4, {}, "Column index 4 is out of range"),
        (2, "Airline", {"expected_current": "UA"}, "Airline holds 'LH', not 'UA'"),
        (2, "Airline", {"expected_row": {"Flight": "0400"}}, "Flight holds '0401', not '0400'"),
        (9, "Airline", {"expected_row": {"demo-connid": "0400"}}, "Flight holds '0408', not '0400'"),
    ],
)
@pytest.mark.anyio
async def test_refusals_write_nothing(row: int, column: int | str, kwargs: dict[str, Any], message: str) -> None:
    tc = _TableControl()
    _refused(await _modify(_Session(tc), row, column, "UA", **kwargs), tc, message)


@pytest.mark.anyio
async def test_a_cell_whose_id_names_another_line_is_refused() -> None:
    tc = _TableControl()
    tc.id_override[(1, 2)] = (1, 3)
    _refused(await _modify(_Session(tc), 3, "Airline", "UA"), tc, "another one")


@pytest.mark.anyio
async def test_a_cell_whose_id_names_another_column_is_refused() -> None:
    tc = _TableControl()
    tc.id_override[(1, 2)] = (2, 2)
    _refused(await _modify(_Session(tc), 3, "Airline", "UA"), tc, "another one")


@pytest.mark.anyio
async def test_a_value_sap_reformats_is_a_failure_that_says_the_cell_changed() -> None:
    tc = _TableControl()
    tc.convert = lambda value: value.zfill(4)
    result = await _modify(_Session(tc), 2, "Flight", "8")
    assert not result.success
    assert result.written
    assert (result.previous_value, result.value) == ("0401", "0008")
    assert "changed from '0401' to '0008'" in (result.error or "")


def test_column_names_resolve_to_one_column() -> None:
    columns = [("Airline", "DEMO-CARRID"), ("DEMO-CARRID", "DEMO-X"), ("Flight", "DEMO-CONNID")]
    assert _resolve_table_control_column(columns, " flight ") == (2, "Flight")
    assert _resolve_table_control_column(columns, "demo-connid") == (2, "Flight")
    assert _resolve_table_control_column(columns, 1) == (1, "DEMO-CARRID")
    with pytest.raises(ValueError, match="fits several columns, pass its index"):
        _resolve_table_control_column(columns, "DEMO-CARRID")


def test_contract_of_the_shared_table_control_helpers() -> None:
    """The read helpers behave as modify_cell relies on (#1010): a change here must fail here, not live."""
    columns = [("Airline", "DEMO-CARRID"), ("Flight", "DEMO-CONNID")]
    # The field name in the id wins over the column number in it.
    assert _cell_header("/app/con[0]/ses[0]/wnd[0]/usr/tblT/txtDEMO-CONNID[0,3]", 0, columns) == "Flight"
    # A padded control reports rows + VisibleRowCount - 1.
    assert _table_control_row_total(row_count=26, visible=5, shown=5) == 22
    assert _table_control_row_total(row_count=3, visible=5, shown=2) == 2
