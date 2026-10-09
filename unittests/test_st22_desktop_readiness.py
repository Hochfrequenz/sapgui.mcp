"""Tests for the ST22 desktop detail read: readiness waits instead of fixed waits (#928)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import TableData
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo, TableRow
from sapguimcp.tools.st22_tools import _st22_lookup_desktop


def _backend() -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.wait = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.get_screen_info = AsyncMock(return_value=ScreenInfo(title="ABAP Runtime Errors", url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    return backend


@pytest.mark.anyio
async def test_detail_waits_for_the_detail_screen_not_a_fixed_time() -> None:
    backend = _backend()
    row = TableRow(row=1, data={"Datum": "01.01.2026", "Uhrzeit": "10:00:00", "Programm": "ZPROG"})
    backend.read_table = AsyncMock(
        return_value=TableData(success=True, headers=["Datum", "Uhrzeit", "Programm"], rows=[row])
    )
    with (
        patch("sapguimcp.tools.st22_tools._navigate_to_st22", AsyncMock(return_value=None)),
        patch("sapguimcp.tools.st22_tools._execute_search", AsyncMock(return_value=None)),
        patch("sapguimcp.tools.st22_tools._select_dump_by_index", AsyncMock(return_value=None)),
        patch(
            "sapguimcp.tools.st22_tools._capture_desktop_detail",
            AsyncMock(return_value=["What happened?", "something"]),
        ),
    ):
        result = await _st22_lookup_desktop(backend, None, 0)
    assert result.success
    backend.wait.assert_not_awaited()
    backend.wait_for_condition.assert_awaited_once()
    assert backend.wait_for_condition.await_args.kwargs["timeout_ms"] <= 1000
    # the screen was read before the dump was opened, so the predicate can tell the detail screen from the list
    assert backend.get_screen_info.await_count == 1
