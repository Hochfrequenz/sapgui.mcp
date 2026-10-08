"""Tests for the ST22 desktop detail read: readiness waits instead of fixed waits (#928)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models import TableData
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo, TableRow
from sapguimcp.tools.st22_tools import _capture_desktop_detail, _st22_lookup_desktop


def _backend(pages: list[str]) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    for name in ("press_key", "wait", "wait_for_ready"):
        setattr(backend, name, AsyncMock())
    backend.wait_for_condition = AsyncMock(return_value=True)
    texts = iter(pages)
    backend.get_screen_text = AsyncMock(side_effect=lambda: SimpleNamespace(full_text=next(texts)))
    backend.get_screen_info = AsyncMock(return_value=ScreenInfo(title="ABAP Runtime Errors", url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    return backend


@pytest.mark.anyio
async def test_capture_scrolls_until_the_page_stays_the_same_and_waits_for_idle_not_a_fixed_time() -> None:
    backend = _backend(["page 1", "page 2", "page 2", "page 2", "page 2"])
    with patch("sapguimcp.tools.st22_tools.asyncio.sleep", AsyncMock()):
        text = await _capture_desktop_detail(backend)
    assert text == "page 1\npage 2"
    assert backend.press_key.await_count == 2  # PageDown twice: the second one shows the same page
    assert backend.wait_for_ready.await_count == 4  # one per PageDown, two more for the confirming reads
    backend.wait.assert_not_awaited()


@pytest.mark.anyio
async def test_capture_keeps_polling_a_repeated_page_until_the_scroll_is_painted() -> None:
    """A scroll that is not painted yet shows the old page for a while; that must not end the capture."""
    backend = _backend(["page 1", "page 1", "page 1", "page 2", "page 2", "page 2", "page 2"])
    with patch("sapguimcp.tools.st22_tools.asyncio.sleep", AsyncMock()):
        assert await _capture_desktop_detail(backend) == "page 1\npage 2"


@pytest.mark.anyio
async def test_detail_waits_for_the_detail_screen_not_a_fixed_time() -> None:
    backend = _backend([])
    row = TableRow(row=1, data={"Datum": "01.01.2026", "Uhrzeit": "10:00:00", "Programm": "ZPROG"})
    backend.read_table = AsyncMock(
        return_value=TableData(success=True, headers=["Datum", "Uhrzeit", "Programm"], rows=[row])
    )
    with (
        patch("sapguimcp.tools.st22_tools._navigate_to_st22", AsyncMock(return_value=None)),
        patch("sapguimcp.tools.st22_tools._execute_search", AsyncMock(return_value=None)),
        patch("sapguimcp.tools.st22_tools._select_dump_by_index", AsyncMock(return_value=None)),
        patch("sapguimcp.tools.st22_tools._capture_desktop_detail", AsyncMock(return_value="What happened\nsomething")),
    ):
        result = await _st22_lookup_desktop(backend, None, 0)
    assert result.success
    backend.wait.assert_not_awaited()
    backend.wait_for_condition.assert_awaited_once()
    assert backend.wait_for_condition.await_args.kwargs["timeout_ms"] <= 1000
    # the screen was read before the dump was opened, so the predicate can tell the detail screen from the list
    assert backend.get_screen_info.await_count == 1
