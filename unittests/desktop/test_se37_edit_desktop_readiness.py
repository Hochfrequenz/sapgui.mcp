"""Tests for the SE37 edit tool on the desktop: navigation with readiness waits and the edit/revert workflow (#1100)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.base import CheckActivateResult
from sapguimcp.models.sap_results import PopupInfo, ScreenInfo, StatusBarInfo
from sapguimcp.tools.desktop_wait_predicates import editor_loaded
from sapguimcp.tools.se37_edit_tools import (
    _edit_check_activate_fm,
    _open_fm_in_change_mode_desktop,
    _open_source_tab_desktop,
)

if TYPE_CHECKING:
    from sapguimcp.lang import LanguagePack

_INITIAL = "Function Builder: Einstieg"
_DISPLAY = "Function Builder: Funktionsbaustein Z_X anzeigen"


def _backend(*, titles: list[str], popup: PopupInfo | None = None, status: str = "") -> Any:
    backend = MagicMock(spec=DesktopBackend)
    for name in (
        "enter_transaction",
        "wait",
        "wait_for_ready",
        "press_key",
        "click_tab",
        "fill_field",
        "dismiss_language_dialog",
        "replace_editor_source",
        "check_and_activate",
        "read_editor_source",
    ):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.leave_transaction_without_saving = AsyncMock(return_value=True)
    backend.wait_for_condition = AsyncMock(return_value=True)
    iterator = iter(titles)
    backend.get_screen_info = AsyncMock(side_effect=lambda: ScreenInfo(title=next(iterator, titles[-1]), url="sap://s"))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=status))
    # the popup is there when the lookup has finished, until the language dialog is dismissed
    backend.check_popup = AsyncMock(
        side_effect=lambda: popup if not backend.dismiss_language_dialog.await_count else None
    )
    session = SimpleNamespace(find_by_id=lambda _element_id, **_: SimpleNamespace(text="Function Builder"))
    backend.require_session = MagicMock(return_value=session)
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


def _pressed(backend: Any) -> list[str]:
    return [call.args[0] for call in backend.press_key.await_args_list]


@pytest.mark.anyio
async def test_open_fm_waits_for_state_changes_not_fixed_times(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_INITIAL, _DISPLAY])
    assert await _open_fm_in_change_mode_desktop(backend, "z_x", lang_de) is None
    backend.wait.assert_not_awaited()
    backend.fill_field.assert_awaited_once_with("Funktionsbaustein", "Z_X")
    # F7 (display) and Ctrl+F1 (change mode) are each followed by a wait for a state change
    assert _pressed(backend) == ["F7", "Ctrl+F1"]
    assert backend.wait_for_condition.await_count == 2
    assert all(call.kwargs["timeout_ms"] <= 3000 for call in backend.wait_for_condition.await_args_list)


@pytest.mark.anyio
async def test_open_fm_falls_back_to_the_field_name_when_no_label_matches(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_INITIAL, _DISPLAY])
    backend.fill_field = AsyncMock(side_effect=ValueError("no such field"))
    assert await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de) is None
    backend.focus_and_type.assert_awaited_once_with("RS38L-NAME", "Z_X")


@pytest.mark.anyio
async def test_open_fm_reports_a_name_field_that_cannot_be_filled(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_INITIAL])
    backend.fill_field = AsyncMock(side_effect=ValueError("no such field"))
    backend.focus_and_type = AsyncMock(return_value=False)
    assert await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de) == "Could not fill function module name field"
    assert _pressed(backend) == []


@pytest.mark.anyio
async def test_open_fm_that_does_not_exist_reports_the_status_text(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_INITIAL], status="Funktionsbaustein Z_X nicht vorhanden")
    assert await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de) == "Funktionsbaustein Z_X nicht vorhanden"
    assert _pressed(backend) == ["F7"]  # no change mode for a function module that was not displayed


@pytest.mark.anyio
async def test_open_fm_without_a_name_is_an_error_before_navigating(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_INITIAL])
    assert await _open_fm_in_change_mode_desktop(backend, "", lang_de) == "No function module name given"
    backend.enter_transaction.assert_not_called()


@pytest.mark.anyio
async def test_open_fm_that_does_not_exist_without_status_text_still_reports_an_error(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_INITIAL])
    assert await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de) == "Function module 'Z_X' not found"


@pytest.mark.anyio
async def test_open_fm_leaves_an_unrelated_popup_alone_and_reports_it(lang_de: LanguagePack) -> None:
    popup = PopupInfo(message="Object is locked by another user", buttons=[])
    backend = _backend(titles=[_INITIAL, _DISPLAY])
    backend.check_popup = AsyncMock(return_value=popup)
    error = await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de)
    assert error == "Unexpected popup while displaying function module 'Z_X': Object is locked by another user"
    assert _pressed(backend) == ["F7"]


@pytest.mark.anyio
async def test_open_fm_confirms_the_language_dialog_that_comes_with_change_mode(lang_de: LanguagePack) -> None:
    popup = PopupInfo(title="Language", text="Different original and logon languages", buttons=[])
    backend = _backend(titles=[_INITIAL, _DISPLAY])
    backend.check_popup = AsyncMock(
        side_effect=lambda: (
            popup if "Ctrl+F1" in _pressed(backend) and not backend.dismiss_language_dialog.await_count else None
        )
    )
    assert await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de) is None
    backend.dismiss_language_dialog.assert_awaited_once()
    # F7, Ctrl+F1, popup gone after the dismissal
    assert backend.wait_for_condition.await_count == 3


@pytest.mark.anyio
async def test_open_fm_reports_an_unrelated_popup_after_change_mode(lang_de: LanguagePack) -> None:
    popup = PopupInfo(message="Object is locked by another user", buttons=[])
    backend = _backend(titles=[_INITIAL, _DISPLAY])
    backend.check_popup = AsyncMock(side_effect=lambda: popup if "Ctrl+F1" in _pressed(backend) else None)
    error = await _open_fm_in_change_mode_desktop(backend, "Z_X", lang_de)
    assert error == (
        "Unexpected popup while switching function module 'Z_X' to change mode: Object is locked by another user"
    )
    assert "Enter" not in _pressed(backend)


@pytest.mark.anyio
async def test_source_tab_waits_for_the_editor(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_DISPLAY])
    assert await _open_source_tab_desktop(backend, "Z_X", lang_de) is None
    backend.click_tab.assert_awaited_once_with("Quelltext")
    backend.wait_for_condition.assert_awaited_once()
    assert backend.wait_for_condition.await_args.args[0] is editor_loaded
    assert backend.wait_for_condition.await_args.kwargs["timeout_ms"] <= 10000


@pytest.mark.anyio
async def test_source_tab_tries_every_label_of_the_language(lang_en: LanguagePack) -> None:
    backend = _backend(titles=[_DISPLAY])
    backend.click_tab = AsyncMock(side_effect=[ValueError("no such tab"), None])
    assert await _open_source_tab_desktop(backend, "Z_X", lang_en) is None
    assert [call.args[0] for call in backend.click_tab.await_args_list] == ["Source Code", "Source text"]


@pytest.mark.anyio
async def test_source_tab_that_does_not_exist_is_reported(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_DISPLAY])
    backend.click_tab = AsyncMock(side_effect=ValueError("no such tab"))
    assert await _open_source_tab_desktop(backend, "Z_X", lang_de) == "Could not find the source code tab"
    backend.wait_for_condition.assert_not_awaited()


@pytest.mark.anyio
async def test_source_tab_without_an_editor_is_reported(lang_de: LanguagePack) -> None:
    backend = _backend(titles=[_DISPLAY])
    backend.wait_for_condition = AsyncMock(return_value=False)
    error = await _open_source_tab_desktop(backend, "Z_X", lang_de)
    assert error == "The source editor of function module 'Z_X' did not open within 10 s"


# ---- edit workflow -----------------------------------------------------------------------------------------------


def _failed(message: str) -> CheckActivateResult:
    return CheckActivateResult.failure(error=message, activated=False, messages=[message])


_BACKUP = "FUNCTION z_x.\nENDFUNCTION."
_NEW = "FUNCTION z_x.\n  WRITE 'new'.\nENDFUNCTION."


def _edit_backend() -> Any:
    backend = _backend(titles=[_INITIAL, _DISPLAY])
    backend.read_editor_source = AsyncMock(return_value=_BACKUP)
    backend.replace_editor_source = AsyncMock(return_value=True)
    backend.check_and_activate = AsyncMock(return_value=CheckActivateResult(success=True, activated=True, messages=[]))
    return backend


@pytest.mark.anyio
async def test_edit_replaces_the_source_and_activates(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert result.success
    assert (result.function_module, result.backup_source, result.activated) == ("Z_X", _BACKUP, True)
    backend.replace_editor_source.assert_awaited_once_with(_NEW)
    backend.check_and_activate.assert_awaited_once()


@pytest.mark.anyio
async def test_edit_stops_at_a_navigation_error(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.click_tab = AsyncMock(side_effect=ValueError("no such tab"))
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert result.error == "Could not find the source code tab"
    backend.replace_editor_source.assert_not_awaited()


@pytest.mark.anyio
async def test_edit_stops_when_the_source_cannot_be_read(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.read_editor_source = AsyncMock(return_value=None)
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert "Could not read current source code" in (result.error or "")
    backend.replace_editor_source.assert_not_awaited()


@pytest.mark.anyio
async def test_edit_restores_the_backup_when_the_replacement_fails(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.replace_editor_source = AsyncMock(side_effect=[False, True])
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert result.backup_source == _BACKUP
    assert "The original source was restored into the editor" in (result.error or "")
    assert [call.args[0] for call in backend.replace_editor_source.await_args_list] == [_NEW, _BACKUP]
    backend.check_and_activate.assert_not_awaited()


@pytest.mark.anyio
async def test_edit_reverts_and_reactivates_when_check_or_activation_fails(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.check_and_activate = AsyncMock(
        side_effect=[
            _failed("Syntax error in line 2"),
            CheckActivateResult(success=True, activated=True, messages=[]),
        ]
    )
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert not result.activated
    assert result.check_messages[0] == "Syntax error in line 2"
    assert "Auto-reverted to original source and re-activated successfully" in result.check_messages
    assert [call.args[0] for call in backend.replace_editor_source.await_args_list] == [_NEW, _BACKUP]


@pytest.mark.anyio
async def test_edit_does_not_claim_a_restore_without_a_confirmed_activation(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.check_and_activate = AsyncMock(
        side_effect=[
            _failed("Syntax error in line 2"),
            CheckActivateResult(success=True, activated=False, messages=["Activation not confirmed"]),
        ]
    )
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert "re-activated successfully" not in (result.error or "")
    assert "Auto-reverted source but re-activation could not be confirmed: Activation not confirmed" in (
        result.check_messages
    )


@pytest.mark.anyio
async def test_edit_reports_a_failed_reactivation_after_the_revert(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.check_and_activate = AsyncMock(
        side_effect=[
            _failed("Syntax error in line 2"),
            _failed("Locked"),
        ]
    )
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert "Auto-reverted source but re-activation failed: Locked" in result.check_messages


@pytest.mark.anyio
async def test_edit_warns_when_the_revert_itself_fails(lang_de: LanguagePack) -> None:
    backend = _edit_backend()
    backend.replace_editor_source = AsyncMock(side_effect=[True, False])
    backend.check_and_activate = AsyncMock(return_value=_failed("Syntax error in line 2"))
    result = await _edit_check_activate_fm(backend, "Z_X", _NEW, lang_de)
    assert not result.success
    assert "WARNING: Auto-revert failed! Manual intervention needed." in result.check_messages
    backend.check_and_activate.assert_awaited_once()
