"""SLG1 on the desktop backend: an empty grid without a 'no logs' status is a failure, not an empty result."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.models import TableData, TableRow
from sapguimcp.tools.slg1_tools import _slg1_lookup_desktop


def _backend(status_message: str, table: TableData) -> Any:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.fill_form = AsyncMock(return_value=SimpleNamespace(not_found=[], errors=[]))
    for name in ("wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=status_message))
    backend.read_table = AsyncMock(return_value=table)
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.require_session = MagicMock()
    backend.com = MagicMock()
    backend.com.run = AsyncMock(return_value=([], False))  # no log tree on screen
    return backend


async def _lookup(backend: Any) -> Any:
    config = MagicMock()
    config.get_default.return_value = SimpleNamespace(language="EN")
    with patch("sapguimcp.tools.slg1_tools.get_sap_config", return_value=config):
        return await _slg1_lookup_desktop(backend, "OBJ")


@pytest.mark.anyio
async def test_an_empty_grid_without_a_no_logs_status_is_a_failure() -> None:
    result = await _lookup(_backend("", TableData(success=True, headers=["Message"], rows=[])))
    assert not result.success
    assert result.logs == []


@pytest.mark.anyio
async def test_rows_that_are_no_logs_are_a_failure() -> None:
    """The grid next to the log tree holds the messages of a selected log, not logs."""
    table = TableData(success=True, headers=["Message"], rows=[TableRow(row=1, data={"Message": "text"})])
    result = await _lookup(_backend("", table))
    assert not result.success
    assert result.logs == []


@pytest.mark.anyio
async def test_rows_with_a_log_number_column_are_logs() -> None:
    table = TableData(
        success=True,
        headers=["Protokollnr."],
        rows=[TableRow(row=1, data={"Protokollnr.": "0000000042"})],
    )
    result = await _lookup(_backend("", table))
    assert result.success
    assert [log.log_number for log in result.logs] == ["0000000042"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    [
        "No application log found",
        "Es konnte kein Protokoll auf der Datenbank gefunden werden",
        "No log could be found in the database",
    ],
)
async def test_a_no_logs_status_is_still_an_empty_result(message: str) -> None:
    backend = _backend(message, TableData(success=True, headers=["Message"], rows=[]))
    result = await _lookup(backend)
    assert result.success
    assert result.logs == []
    backend.read_table.assert_not_called()
