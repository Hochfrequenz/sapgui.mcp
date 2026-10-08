"""Tests for the SE24 edit tool on the desktop: readiness waits instead of fixed waits (#928)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.sap_results import PopupInfo, ScreenInfo, StatusBarInfo
from sapguimcp.tools.desktop_wait_predicates import editor_loaded, editor_loaded_after, window_title_changed
from sapguimcp.tools.se24_edit_tools import (
    _open_class_in_change_mode_desktop,
    _select_method_and_open_source_desktop,
)


def _backend(*, titles: list[str], popup: PopupInfo | None = None) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    for name in ("enter_transaction", "wait", "wait_for_ready", "press_key", "click_tab", "click_button"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.wait_for_condition = AsyncMock(return_value=True)
    iterator = iter(titles)
    backend.get_screen_info = AsyncMock(side_effect=lambda: ScreenInfo(title=next(iterator, titles[-1]), url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    backend.check_popup = AsyncMock(return_value=popup)
    session = SimpleNamespace(find_by_id=lambda _element_id, **_: SimpleNamespace(text="Class Builder"))
    backend.require_session = MagicMock(return_value=session)
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


@pytest.mark.anyio
async def test_open_class_waits_for_state_changes_not_fixed_times() -> None:
    backend = _backend(titles=["Class Builder: Einstieg", "Class Builder: Klasse CL_X anzeigen"])
    assert await _open_class_in_change_mode_desktop(backend, "cl_x") is None
    backend.wait.assert_not_awaited()
    # F7 (display) and Ctrl+F1 (change mode) are each followed by a wait for a state change
    assert [call.args[0] for call in backend.press_key.await_args_list] == ["F7", "Ctrl+F1"]
    assert backend.wait_for_condition.await_count == 2
    assert all(call.kwargs["timeout_ms"] <= 3000 for call in backend.wait_for_condition.await_args_list)


@pytest.mark.anyio
async def test_open_class_presses_enter_only_when_a_popup_is_open() -> None:
    backend = _backend(titles=["Class Builder: Einstieg", "Class Builder: Klasse CL_X anzeigen"])
    await _open_class_in_change_mode_desktop(backend, "CL_X")
    assert "Enter" not in [call.args[0] for call in backend.press_key.await_args_list]

    popup = PopupInfo(title="Language", text="Different original and logon languages", buttons=[])
    backend = _backend(titles=["Class Builder: Einstieg", "Class Builder: Klasse CL_X anzeigen"], popup=popup)
    await _open_class_in_change_mode_desktop(backend, "CL_X")
    assert [call.args[0] for call in backend.press_key.await_args_list] == ["F7", "Enter", "Ctrl+F1"]
    # F7, popup gone after Enter, Ctrl+F1
    assert backend.wait_for_condition.await_count == 3


@pytest.mark.anyio
async def test_open_class_that_stays_on_the_initial_screen_reports_the_status_text() -> None:
    backend = _backend(titles=["Class Builder: Einstieg"])
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="E", message="Class CL_X does not exist"))
    assert await _open_class_in_change_mode_desktop(backend, "CL_X") == "Class CL_X does not exist"
    assert "Ctrl+F1" not in [call.args[0] for call in backend.press_key.await_args_list]


@pytest.mark.anyio
async def test_open_class_needs_a_desktop_backend() -> None:
    assert await _open_class_in_change_mode_desktop(MagicMock(), "CL_X") == "Requires DesktopBackend"


def _method_table_session(method_names: list[str]) -> Any:
    """Session with one table control whose 'Methode' column lists ``method_names``."""

    class _Raw:
        RowCount = VisibleRowCount = len(method_names)

        def __init__(self) -> None:
            self.focused: list[int] = []
            self.Columns = _Columns()

        def GetCell(self, row: int, _column: int) -> Any:  # noqa: N802 (COM name)
            return SimpleNamespace(Text=method_names[row], SetFocus=lambda: self.focused.append(row))

    class _Columns:
        Count = 1

        def __call__(self, _index: int) -> Any:
            return SimpleNamespace(Title="Methode", Name="METHOD")

    raw = _Raw()
    element = SimpleNamespace(id="/wnd[0]/usr/tbl", type_as_number=80, children=[])

    def _find(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return SimpleNamespace(dump_tree=lambda: [element])
        return SimpleNamespace(com=raw)

    return SimpleNamespace(find_by_id=_find, raw=raw)


@pytest.fixture(autouse=True)
def _no_editor_before_the_click() -> Any:
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=None):
        yield


def _method_backend(session: Any) -> Any:
    backend = _backend(titles=["Class Builder"])
    backend.require_session = MagicMock(return_value=session)
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


@pytest.mark.anyio
async def test_select_method_waits_for_the_editor_instead_of_a_fixed_time() -> None:
    session = _method_table_session(["OTHER", "DO_SOMETHING"])
    backend = _method_backend(session)
    assert await _select_method_and_open_source_desktop(backend, "CL_X", "do_something") is None
    backend.wait.assert_not_awaited()
    assert session.raw.focused == [1]
    backend.click_button.assert_awaited_once_with("Quelltext")
    # the last wait is for the editor to exist, which is a bounded wait
    assert backend.wait_for_condition.await_count == 2  # the Methods tab, then the editor
    assert backend.wait_for_condition.await_args_list[-1].kwargs["timeout_ms"] <= 5000


@pytest.mark.anyio
async def test_a_failing_wait_after_the_click_does_not_click_the_next_button() -> None:
    backend = _method_backend(_method_table_session(["DO_SOMETHING"]))
    backend.wait_for_condition = AsyncMock(side_effect=[True, RuntimeError("connection lost")])
    with pytest.raises(RuntimeError, match="connection lost"):
        await _select_method_and_open_source_desktop(backend, "CL_X", "DO_SOMETHING")
    backend.click_button.assert_awaited_once_with("Quelltext")


@pytest.mark.anyio
async def test_select_method_reports_a_method_that_is_not_in_the_table() -> None:
    backend = _method_backend(_method_table_session(["OTHER"]))
    error = await _select_method_and_open_source_desktop(backend, "CL_X", "DO_SOMETHING")
    assert error == "Method 'DO_SOMETHING' not found in class 'CL_X' methods table"
    backend.click_button.assert_not_awaited()


def test_editor_loaded_is_true_once_the_window_has_an_editor() -> None:
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=(object(), "AbapEditor")):
        assert editor_loaded(MagicMock())
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=None):
        assert not editor_loaded(MagicMock())


def _editor_session(title: str, *, editor: bool) -> Any:
    return SimpleNamespace(find_by_id=lambda _element_id, **_: SimpleNamespace(text=title), editor=editor)


def test_editor_loaded_after_without_an_earlier_editor_needs_just_the_editor() -> None:
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=(object(), "AbapEditor")):
        assert editor_loaded_after(None)(_editor_session("Class Builder", editor=True))
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=None):
        assert not editor_loaded_after(None)(_editor_session("Class Builder", editor=False))


def test_editor_loaded_after_with_an_earlier_editor_also_needs_a_new_title() -> None:
    with patch.object(DesktopBackend, "_find_editor_shell_raw", return_value=(object(), "AbapEditor")):
        predicate = editor_loaded_after("Class CL_X change")
        assert not predicate(_editor_session("Class CL_X change", editor=True))
        assert predicate(_editor_session("Method DO_SOMETHING change", editor=True))


def test_window_title_changed() -> None:
    assert not window_title_changed(" Class CL_X display ")(_editor_session("Class CL_X display", editor=False))
    assert window_title_changed("Class CL_X display")(_editor_session("Class CL_X change", editor=False))
