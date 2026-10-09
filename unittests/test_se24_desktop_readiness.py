"""Tests for the SE24 desktop lookup: readiness waits instead of fixed waits (#928)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo
from sapguimcp.tools.se24_tools import SE24Entry, SE24Error, _click_tab_bilingual, _lookup_class_desktop, _read_tab_rows

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


def _screen_session(title: str, status: str, popup: bool = False) -> Any:
    elements = {"wnd[0]": SimpleNamespace(text=title), "wnd[0]/sbar": SimpleNamespace(text=status)}
    if popup:
        elements["wnd[1]"] = SimpleNamespace(text="Language")
    return SimpleNamespace(find_by_id=lambda element_id, **_kwargs: elements.get(element_id))


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
async def test_click_tab_desktop_falls_back_to_the_english_label() -> None:
    backend = _desktop_backend()
    backend.click_tab = AsyncMock(side_effect=[ValueError("no DE tab"), None])
    assert await _click_tab_bilingual(backend, "Attribute", "Attributes") == "Attributes"


@pytest.mark.anyio
async def test_click_tab_desktop_reports_a_missing_tab_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    backend = _desktop_backend()
    backend.click_tab = AsyncMock(side_effect=ValueError("no tab"))
    with caplog.at_level(logging.WARNING):
        assert await _click_tab_bilingual(backend, "Attribute", "Attributes") is None
    assert "Tab not found: Attribute / Attributes" in caplog.text


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


def _lookup_backend(popup: Any) -> Any:
    backend = _desktop_backend()
    backend.fill_field = AsyncMock()
    backend.press_key = AsyncMock()
    titles = iter(["Initial"])
    backend.get_screen_info = AsyncMock(
        side_effect=lambda: ScreenInfo(title=next(titles, "Display CL_X"), url="sap://s")
    )
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=" Old "))
    backend.check_popup = AsyncMock(return_value=popup)
    backend.discover_fields = AsyncMock(return_value=[SimpleNamespace(name="SEOCLASS-DESCRIPT", value="A class")])
    return backend


@pytest.mark.anyio
async def test_lookup_class_without_popup_waits_for_the_state_change_and_presses_no_enter() -> None:
    backend = _lookup_backend(popup=None)
    events = _record_calls(backend, "press_key", "wait_for_ready", "wait_for_condition")
    with patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", return_value=[]):
        result = await _lookup_class_desktop(backend, "CL_X")
    assert isinstance(result, SE24Entry)
    backend.wait.assert_not_awaited()
    f7 = events.index("press_key")
    assert events[f7 : f7 + 3] == ["press_key", "wait_for_ready", "wait_for_condition"]
    assert events.count("press_key") == 1  # only F7: Enter is for a language popup, none is open
    predicate = backend.wait_for_condition.await_args_list[0].args[0]
    assert predicate.__qualname__.startswith("screen_changed.")
    # Bounded: a lookup whose screen never changes may not cost more than the former fixed waits (3 s).
    assert backend.wait_for_condition.await_args_list[0].kwargs == {"timeout_ms": 3000}
    # Built from the pre-F7 snapshot: unchanged title and stale status are not ready, a new title is.
    assert not predicate(_screen_session("Initial", "Old"))
    assert predicate(_screen_session("Display CL_X", "Old"))


@pytest.mark.anyio
async def test_lookup_class_with_a_popup_confirms_it_and_waits_again() -> None:
    backend = _lookup_backend(popup=SimpleNamespace(title="Language"))
    events = _record_calls(backend, "press_key", "wait_for_ready", "wait_for_condition")
    with patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", return_value=[]):
        result = await _lookup_class_desktop(backend, "CL_X")
    assert isinstance(result, SE24Entry)
    f7 = events.index("press_key")
    # F7 and Enter are each followed by a ready wait and a state-change wait
    assert events[f7 : f7 + 3] == ["press_key", "wait_for_ready", "wait_for_condition"]
    assert events[f7 + 3 : f7 + 6] == ["press_key", "wait_for_ready", "wait_for_condition"]
    assert [c.kwargs for c in backend.wait_for_condition.await_args_list[:2]] == [{"timeout_ms": 3000}] * 2
    after_enter = backend.wait_for_condition.await_args_list[1].args[0]
    assert after_enter.__qualname__.startswith("popup_closed_and_screen_changed.")
    # the popup that is being dismissed must not satisfy the wait, even though the screen behind it changed
    assert not after_enter(_screen_session("Display CL_X", "Old", popup=True))
    assert after_enter(_screen_session("Display CL_X", "Old"))


@pytest.mark.anyio
async def test_lookup_class_requires_the_desktop_backend_before_touching_the_screen() -> None:
    backend = MagicMock()  # not a DesktopBackend
    backend.fill_field = AsyncMock()
    result = await _lookup_class_desktop(backend, "CL_X")
    assert not isinstance(result, SE24Entry)
    assert result.error == "Requires DesktopBackend"
    backend.fill_field.assert_not_awaited()


@pytest.mark.anyio
async def test_lookup_class_not_found_reports_the_generic_text_not_sap_s_own_message() -> None:
    """The former unconditional Enter cleared SAP's message, so callers always saw this text; keep it."""
    backend = _lookup_backend(popup=None)
    backend.get_screen_info = AsyncMock(return_value=ScreenInfo(title="Class Builder: Einstieg", url="sap://s"))
    backend.get_status_bar = AsyncMock(
        return_value=StatusBarInfo(type="S", message="Objekttyp CL_X ist nicht vorhanden")
    )
    result = await _lookup_class_desktop(backend, "CL_X")
    assert isinstance(result, SE24Error)
    assert result.error == "Class/interface 'CL_X' not found"


@pytest.mark.anyio
async def test_lookup_class_opens_the_properties_tab_last_and_returns_its_header_data() -> None:
    backend = _lookup_backend(popup=None)
    header = {
        "description": "An example class",
        "package": "ZPACKAGE",
        "superclass": "ZCL_BASE",
        "is_abstract": True,
        "is_final": False,
    }
    clicked: list[str] = []
    backend.click_tab = AsyncMock(side_effect=clicked.append)
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    with (
        patch("sapguimcp.tools.se24_tools.read_table_control_all_rows", return_value=[]),
        patch("sapguimcp.tools.se24_tools._read_se24_header", return_value=header),
    ):
        result = await _lookup_class_desktop(backend, "CL_X")
    assert isinstance(result, SE24Entry)
    assert clicked[-1] == "Eigenschaften"  # last: the properties tab has a table control that is no method list
    assert (result.description, result.package, result.superclass, result.is_abstract, result.is_final) == (
        "An example class",
        "ZPACKAGE",
        "ZCL_BASE",
        True,
        False,
    )
