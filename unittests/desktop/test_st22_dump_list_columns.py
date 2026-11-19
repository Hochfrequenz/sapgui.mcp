"""ST22 desktop dump list: the ALV grid is keyed by technical column names (#1154)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp import lang
from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import TableData
from sapguimcp.models.sap_results import StatusBarInfo, TableRow
from sapguimcp.tools.st22_tools import _st22_lookup_desktop

# The headers read_table returns for the ST22 dump list on SAP S/4HANA 2025 (German logon)
_TECHNICAL_HEADERS = ["DATUM", "UZEIT", "AHOST", "UNAME", "MANDT", "XHOLD", "ERRORID", "REXCEPTION", "GPROGRAM"]


def _row(n: int, time: str, user: str, error: str, program: str) -> TableRow:
    data = dict.fromkeys(_TECHNICAL_HEADERS, "")
    data.update({"DATUM": "18.11.2026", "UZEIT": time, "UNAME": user, "ERRORID": error, "GPROGRAM": program})
    return TableRow(row=n, data=data)


async def _lookup(table: TableData, language: str = "DE") -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    backend.read_table = AsyncMock(return_value=table)
    with (
        patch("sapguimcp.tools.st22_tools._navigate_to_st22", AsyncMock(return_value=None)),
        patch("sapguimcp.tools.st22_tools._execute_search", AsyncMock(return_value=None)),
    ):
        return await _st22_lookup_desktop(backend, lang.view_for(language), "2026-11-18", None)


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["DE", "EN"])
async def test_fields_are_read_from_the_technical_columns(language: str) -> None:
    rows = [
        _row(1, "09:15:00", "USER01", "MESSAGE_TYPE_X", "SAPLZTEST"),
        _row(2, "17:40:12", "USER02", "COMPUTE_INT_ZERODIVIDE", "ZREPORT"),
    ]
    result = await _lookup(TableData(success=True, headers=_TECHNICAL_HEADERS, rows=rows), language)
    assert result.success
    assert result.dump_count == 2
    # sorted by time, latest first
    first, second = result.dumps
    assert (first.time, first.user, first.error_type, first.program) == (
        "17:40:12",
        "USER02",
        "COMPUTE_INT_ZERODIVIDE",
        "ZREPORT",
    )
    assert (second.time, second.user, second.error_type, second.program) == (
        "09:15:00",
        "USER01",
        "MESSAGE_TYPE_X",
        "SAPLZTEST",
    )


@pytest.mark.anyio
async def test_title_keyed_list_still_works() -> None:
    row = TableRow(row=1, data={"Uhrzeit": "10:00:00", "Programm": "ZPROG", "Laufzeitfehler": "RAISE_EXCEPTION"})
    result = await _lookup(TableData(success=True, headers=["Uhrzeit", "Programm", "Laufzeitfehler"], rows=[row]))
    assert result.success
    assert (result.dumps[0].time, result.dumps[0].program, result.dumps[0].error_type) == (
        "10:00:00",
        "ZPROG",
        "RAISE_EXCEPTION",
    )


@pytest.mark.anyio
async def test_unknown_columns_are_an_error_not_empty_dumps() -> None:
    row = TableRow(row=1, data={"FOO": "1", "BAR": "2"})
    result = await _lookup(TableData(success=True, headers=["FOO", "BAR"], rows=[row]))
    assert not result.success
    assert "FOO" in (result.error or "")
    assert result.dumps == []
