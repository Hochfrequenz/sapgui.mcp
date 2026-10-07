"""Tests for the SE24 desktop lookup: readiness waits instead of fixed waits (#928)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo
from sapguimcp.tools.se24_tools import SE24Entry, _click_tab_bilingual, _lookup_class_desktop, _read_tab_rows

_ROW_A = [{"Attribut": "A"}]
_ROW_B = [{"Attribut": "B"}]


def _desktop_backend() -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.click_tab = AsyncMock()
    backend.wait = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


def _record_calls(backend: Any, *names: str) -> list[str]:
    """Replace the named async backend methods by recorders and return the shared, ordered event list."""
    events: list[str] = []

    def _recorder(name: str) -> AsyncMock:
        async def _record(*_args: Any, **_kwargs: Any) -> None:
            events.append(name)

        return AsyncMock(side_effect=_record)

    for name in names:
        setattr(backend, name, _recorder(name))
    return events


# --- _click_tab_bilingual -----------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_click_tab_desktop_only_waits_for_ready_and_returns_the_label() -> None:
    backend = _desktop_backend()
    assert await _click_tab_bilingual(backend, "Attribute", "Attributes") == "Attribute"
    backend.wait_for_ready.assert_awaited_once()
    backend.wait.assert_not_awaited()


@pytest.mark.anyio
async def test_click_tab_desktop_falls_back_to_the_english_label_and_reports_a_miss() -> None:
    backend = _desktop_backend()
    backend.click_tab = AsyncMock(side_effect=[ValueError("no DE tab"), None])
    assert await _click_tab_bilingual(backend, "Attribute", "Attributes") == "Attributes"
    backend.click_tab = AsyncMock(side_effect=ValueError("no tab"))
    assert await _click_tab_bilingual(backend, "Attribute", "Attributes") is None


@pytest.mark.anyio
async def test_click_tab_webgui_keeps_the_fixed_wait() -> None:
    backend = MagicMock()  # not a DesktopBackend
    backend.click_tab = AsyncMock()
    backend.wait = AsyncMock()
    assert await _click_tab_bilingual(backend, "Attribute", "Attributes") == "Attribute"
    backend.wait.assert_awaited_once_with(500)


# --- _read_tab_rows -----------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_read_tab_rows_populated_tab_costs_no_extra_wait() -> None:
    backend = _desktop_backend()
    with patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", return_value=_ROW_B):
        rows = await _read_tab_rows(backend, "Attribute", "Attributes", previous_rows=_ROW_A)
    assert rows == _ROW_B
    backend.wait_for_condition.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("first_read", [[], _ROW_A])
async def test_read_tab_rows_waits_for_the_tabs_table_control_when_empty_or_unchanged(
    first_read: list[dict[str, str]],
) -> None:
    backend = _desktop_backend()
    with patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", side_effect=[first_read, _ROW_B]):
        rows = await _read_tab_rows(backend, "Attribute", "Attributes", previous_rows=_ROW_A)
    assert rows == _ROW_B
    backend.wait_for_condition.assert_awaited_once()
    assert backend.wait_for_condition.await_args.args[0].__qualname__.startswith("tab_table_control_loaded.")
    assert backend.wait_for_condition.await_args.kwargs == {"timeout_ms": 3000, "poll_ms": 250}


@pytest.mark.anyio
async def test_read_tab_rows_unknown_tab_does_not_wait_for_a_control() -> None:
    backend = _desktop_backend()
    backend.click_tab = AsyncMock(side_effect=ValueError("no tab"))
    with patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", return_value=[]):
        rows = await _read_tab_rows(backend, "Attribute", "Attributes", previous_rows=[])
    assert rows == []
    backend.wait_for_condition.assert_not_awaited()


# --- _lookup_class_desktop wiring ---------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_lookup_class_waits_for_state_changes_instead_of_fixed_times() -> None:
    backend = _desktop_backend()
    backend.fill_field = AsyncMock()
    backend.press_key = AsyncMock()
    backend.get_screen_info = AsyncMock(
        side_effect=[ScreenInfo(title="Initial", url="sap://s"), ScreenInfo(title="Display CL_X", url="sap://s")]
    )
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.discover_fields = AsyncMock(return_value=[SimpleNamespace(name="SEOCLASS-DESCRIPT", value="A class")])
    events = _record_calls(backend, "press_key", "wait_for_ready", "wait_for_condition")
    with patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", return_value=[]):
        result = await _lookup_class_desktop(backend, "CL_X")
    assert isinstance(result, SE24Entry)
    backend.wait.assert_not_awaited()
    f7 = events.index("press_key")
    # F7 and Enter are each followed by a ready wait and a state-change wait
    assert events[f7 : f7 + 3] == ["press_key", "wait_for_ready", "wait_for_condition"]
    assert events[f7 + 3 : f7 + 6] == ["press_key", "wait_for_ready", "wait_for_condition"]
    predicate = backend.wait_for_condition.await_args_list[0].args[0]
    assert predicate.__qualname__.startswith("screen_changed.")


@pytest.mark.anyio
async def test_lookup_class_requires_the_desktop_backend_before_touching_the_screen() -> None:
    backend = MagicMock()  # not a DesktopBackend
    backend.fill_field = AsyncMock()
    result = await _lookup_class_desktop(backend, "CL_X")
    assert not isinstance(result, SE24Entry)
    assert result.error == "Requires DesktopBackend"
    backend.fill_field.assert_not_awaited()
