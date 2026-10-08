"""Tests for the SE38 edit tool on the desktop: readiness waits instead of a fixed wait after F6 (#928)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.base import PopupInfo
from sapguimcp.models.sap_results import ScreenInfo, StatusBarInfo
from sapguimcp.tools.desktop_wait_predicates import editor_loaded_or_popup_open
from sapguimcp.tools.se38_edit_tools import _navigate_and_open_editor_desktop


def _backend(*, title_after_f6: str, status: str = "", condition_results: list[bool] | None = None) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    for name in ("enter_transaction", "wait", "wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.wait_for_condition = AsyncMock(side_effect=condition_results or [True, True])
    titles = iter(["ABAP Editor: Einstieg", title_after_f6])
    backend.get_screen_info = AsyncMock(side_effect=lambda: ScreenInfo(title=next(titles), url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=status))
    backend.check_popup = AsyncMock(return_value=None)
    return backend


@pytest.mark.anyio
async def test_open_report_waits_for_state_changes_not_a_fixed_time() -> None:
    backend = _backend(title_after_f6="ABAP Editor: Programm ZTEST aendern")
    assert await _navigate_and_open_editor_desktop(backend, "ztest") is None
    backend.wait.assert_not_awaited()
    backend.press_key.assert_awaited_once_with("F6")
    # first the screen after F6, then the editor control; both bounded
    assert backend.wait_for_condition.await_count == 2
    first_predicate = backend.wait_for_condition.await_args_list[0].args[0]
    assert first_predicate is not editor_loaded_or_popup_open
    assert backend.wait_for_condition.await_args_list[1].args[0] is editor_loaded_or_popup_open
    assert all(call.kwargs["timeout_ms"] <= 5000 for call in backend.wait_for_condition.await_args_list)


@pytest.mark.anyio
async def test_open_report_that_stays_on_the_initial_screen_reports_the_status_text() -> None:
    backend = _backend(title_after_f6="ABAP Editor: Einstieg", status="Das Programm ZTEST ist nicht vorhanden")
    backend.get_status_bar = AsyncMock(
        side_effect=[StatusBarInfo(type="S", message=""), StatusBarInfo(type="E", message="Programm fehlt")]
    )
    assert await _navigate_and_open_editor_desktop(backend, "ZTEST") == "Programm fehlt"
    assert backend.wait_for_condition.await_count == 1  # no editor to wait for


@pytest.mark.anyio
async def test_open_report_fails_when_the_editor_does_not_appear() -> None:
    backend = _backend(title_after_f6="ABAP Editor: Programm ZTEST aendern", condition_results=[True, False])
    error = await _navigate_and_open_editor_desktop(backend, "ZTEST")
    assert error == "The editor of 'ZTEST' did not open within 5 s"


@pytest.mark.anyio
async def test_open_report_needs_a_desktop_backend() -> None:
    assert await _navigate_and_open_editor_desktop(MagicMock(), "ZTEST") == "Requires DesktopBackend"


@pytest.mark.anyio
async def test_open_report_reports_a_popup_instead_of_waiting_for_the_editor() -> None:
    backend = _backend(title_after_f6="ABAP Editor: Programm ZTEST aendern")
    backend.check_popup = AsyncMock(return_value=PopupInfo(message="Program is locked by another user", buttons=[]))
    error = await _navigate_and_open_editor_desktop(backend, "ZTEST")
    assert error == "Unexpected popup while opening 'ZTEST': Program is locked by another user"
    assert backend.wait_for_condition.await_count == 1  # only the screen wait, not the editor wait


@pytest.mark.anyio
async def test_a_popup_over_the_unchanged_initial_screen_is_reported_as_a_popup() -> None:
    backend = _backend(title_after_f6="ABAP Editor: Einstieg")
    backend.check_popup = AsyncMock(return_value=PopupInfo(message="Program is locked by another user", buttons=[]))
    error = await _navigate_and_open_editor_desktop(backend, "ZTEST")
    assert error == "Unexpected popup while opening 'ZTEST': Program is locked by another user"


@pytest.mark.anyio
async def test_a_popup_that_opens_while_the_editor_is_built_is_reported_as_a_popup() -> None:
    backend = _backend(title_after_f6="ABAP Editor: Programm ZTEST aendern", condition_results=[True, True])
    popup = PopupInfo(message="Program is locked by another user", buttons=[])
    backend.check_popup = AsyncMock(side_effect=[None, popup])  # none at the first check, one by the editor wait
    error = await _navigate_and_open_editor_desktop(backend, "ZTEST")
    assert error == "Unexpected popup while opening 'ZTEST': Program is locked by another user"


@pytest.mark.anyio
async def test_a_popup_ends_the_editor_wait_early() -> None:
    popup_session = SimpleNamespace(find_by_id=lambda _element_id, **_: object())
    assert editor_loaded_or_popup_open(popup_session)
    no_popup_session = SimpleNamespace(find_by_id=lambda _element_id, **_: None)
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=None):
        assert not editor_loaded_or_popup_open(no_popup_session)
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=(object(), "AbapEditor")):
        assert editor_loaded_or_popup_open(no_popup_session)
