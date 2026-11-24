"""The desktop edit tools leave the editor after the edit, so the object is no longer locked (#1166)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.se24_edit_models import SE24EditResult
from sapguimcp.models.se37_edit_models import SE37EditResult
from sapguimcp.models.se38_edit_models import SE38EditResult
from sapguimcp.tools import se24_edit_tools, se37_edit_tools, se38_edit_tools
from sapguimcp.tools.edit_helpers import leave_editor_after

# ---- DesktopBackend.leave_transaction_without_saving --------------------------------------------------------------


@dataclass
class _Dialog:
    has_no_button: bool = True
    closes_on_cancel: bool = True
    leaves_on_no: bool = False  # "save changes?" raised by /n: "No" discards and goes on with /n


class _FakeSession:
    """A session in ``transaction`` with a stack of dialogs; records every key and button press."""

    def __init__(self, transaction: str, dialogs: list[_Dialog] | None = None, popup_on_leave: _Dialog | None = None):
        self.info = MagicMock(transaction=transaction)
        self.dialogs = list(dialogs or [])
        self.popup_on_leave = popup_on_leave
        self.okcd = ""
        self.events: list[str] = []

    def find_by_id(self, element_id: str, raise_error: bool = True) -> Any:
        if element_id == "wnd[0]":
            return MagicMock(send_v_key=self._main_key)
        if element_id == "wnd[0]/tbar[0]/okcd":
            return self
        for index, dialog in enumerate(self.dialogs, start=1):
            if element_id == f"wnd[{index}]":
                return MagicMock(send_v_key=lambda key, i=index: self._dialog_key(i, key))
            if element_id == f"wnd[{index}]/usr/btnSPOP-OPTION2" and dialog.has_no_button:
                return MagicMock(press=lambda i=index: self._press_no(i))
            if element_id == f"wnd[{index}]/usr/btnSPOP-OPTION1":
                raise AssertionError("the 'Yes' button must never be touched")
        if raise_error:
            raise AssertionError(f"unexpected element: {element_id}")
        return None

    @property
    def text(self) -> str:
        return self.okcd

    @text.setter
    def text(self, value: str) -> None:
        self.okcd = value

    def _main_key(self, key: int) -> None:
        assert not self.dialogs, "the main window cannot get a key while a dialog is open"
        self.events.append(f"main:{key}:{self.okcd}")
        if key == 0 and self.okcd == "/n":
            if self.popup_on_leave is not None:
                self.dialogs.append(self.popup_on_leave)
            else:
                self.info.transaction = "SESSION_MANAGER"

    def _dialog_key(self, index: int, key: int) -> None:
        assert index == len(self.dialogs), "keys only go to the topmost dialog"
        assert key == 12, "a dialog is only ever cancelled, never confirmed with Enter"
        self.events.append(f"wnd[{index}]:F12")
        if self.dialogs[-1].closes_on_cancel:
            self.dialogs.pop()

    def _press_no(self, index: int) -> None:
        assert index == len(self.dialogs), "buttons are only pressed on the topmost dialog"
        self.events.append(f"wnd[{index}]:No")
        if self.dialogs.pop().leaves_on_no:
            self.info.transaction = "SESSION_MANAGER"


def _make_backend(session: _FakeSession) -> DesktopBackend:
    backend = DesktopBackend.__new__(DesktopBackend)

    async def run(fn):  # type: ignore[no-untyped-def]
        return fn()

    backend.com = MagicMock()
    backend.com.run = run
    backend.require_session = lambda: session  # type: ignore[assignment,method-assign,return-value]
    return backend


@pytest.mark.anyio
async def test_leaving_ends_the_transaction_with_slash_n() -> None:
    session = _FakeSession("SE38")
    assert await _make_backend(session).leave_transaction_without_saving("SE38") is True
    assert session.events == ["main:0:/n"]


@pytest.mark.anyio
async def test_a_session_in_another_transaction_is_left_alone() -> None:
    session = _FakeSession("VA01")
    assert await _make_backend(session).leave_transaction_without_saving("SE38") is True
    assert session.events == []


@pytest.mark.anyio
async def test_the_save_popup_raised_by_leaving_is_answered_with_no() -> None:
    session = _FakeSession("SE37", popup_on_leave=_Dialog(leaves_on_no=True))
    assert await _make_backend(session).leave_transaction_without_saving("SE37") is True
    assert session.events == ["main:0:/n", "wnd[1]:No"]


@pytest.mark.anyio
async def test_dialogs_already_open_are_closed_topmost_first_before_leaving() -> None:
    session = _FakeSession("SE24", dialogs=[_Dialog(has_no_button=False), _Dialog(has_no_button=False)])
    assert await _make_backend(session).leave_transaction_without_saving("SE24") is True
    assert session.events == ["wnd[2]:F12", "wnd[1]:F12", "main:0:/n"]


@pytest.mark.anyio
async def test_a_popup_without_a_no_button_is_cancelled_and_reported_when_it_keeps_the_session() -> None:
    # F12 on a "save changes?" popup without the standard buttons cancels the leaving: the session stays
    session = _FakeSession("SE38", popup_on_leave=_Dialog(has_no_button=False))
    assert await _make_backend(session).leave_transaction_without_saving("SE38") is False
    assert session.events == ["main:0:/n", "wnd[1]:F12"]


@pytest.mark.anyio
async def test_a_dialog_that_cannot_be_closed_is_reported() -> None:
    session = _FakeSession("SE38", dialogs=[_Dialog(has_no_button=False, closes_on_cancel=False)])
    assert await _make_backend(session).leave_transaction_without_saving("SE38") is False
    assert session.events
    assert all(event == "wnd[1]:F12" for event in session.events)  # /n is not sent past the open dialog


# ---- leave_editor_after -------------------------------------------------------------------------------------------


def _result(success: bool = True) -> SE38EditResult:
    if success:
        return SE38EditResult(program_name="Z_X", backup_source="old", check_messages=["activated"], activated=True)
    return SE38EditResult.failure(error="Check failed", program_name="Z_X", backup_source="old")


def _leaving_backend(**leave: Any) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.leave_transaction_without_saving = AsyncMock(**leave)
    return backend


async def _returns(result: SE38EditResult) -> SE38EditResult:
    return result


@pytest.mark.anyio
@pytest.mark.parametrize("success", [True, False])
async def test_the_editor_is_left_after_success_and_failure(success: bool) -> None:
    backend = _leaving_backend(return_value=True)
    result = await leave_editor_after(backend, "SE38", _returns(_result(success)))
    assert result.success is success
    assert result.check_messages == (["activated"] if success else [])
    backend.leave_transaction_without_saving.assert_awaited_once_with("SE38")


@pytest.mark.anyio
async def test_the_editor_is_left_when_the_edit_raises() -> None:
    backend = _leaving_backend(return_value=True)

    async def edit() -> SE38EditResult:
        raise RuntimeError("COM broke")

    with pytest.raises(RuntimeError, match="COM broke"):
        await leave_editor_after(backend, "SE38", edit())
    backend.leave_transaction_without_saving.assert_awaited_once_with("SE38")


@pytest.mark.anyio
@pytest.mark.parametrize("leave", [{"return_value": False}, {"side_effect": RuntimeError("COM broke")}])
async def test_a_failed_leave_keeps_the_result_and_adds_a_note(leave: dict[str, Any]) -> None:
    result = await leave_editor_after(_leaving_backend(**leave), "SE38", _returns(_result()))
    assert result.success
    assert result.activated
    assert result.check_messages[0] == "activated"
    assert result.check_messages[1].startswith("The session could not leave SE38, so the object may still be locked")


# ---- the three tools ----------------------------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("module", "inner", "tcode", "result", "call"),
    [
        (
            se38_edit_tools,
            "_edit_in_editor",
            "SE38",
            SE38EditResult.failure(error="x", program_name="Z_X", backup_source=""),
            lambda backend: se38_edit_tools._edit_check_activate(backend, "Z_X", "new", MagicMock()),
        ),
        (
            se37_edit_tools,
            "_edit_fm_in_editor",
            "SE37",
            SE37EditResult.failure(error="x", function_module="Z_X", backup_source=""),
            lambda backend: se37_edit_tools._edit_check_activate_fm(backend, "Z_X", "new", MagicMock()),
        ),
        (
            se24_edit_tools,
            "_edit_method_in_editor",
            "SE24",
            SE24EditResult.failure(error="x", class_name="ZCL_X", method_name="M", backup_source=""),
            lambda backend: se24_edit_tools._edit_check_activate_method(backend, "ZCL_X", "M", "new", MagicMock()),
        ),
    ],
)
async def test_each_edit_tool_leaves_its_transaction(
    module: Any, inner: str, tcode: str, result: Any, call: Any
) -> None:
    backend = _leaving_backend(return_value=True)
    with patch.object(module, inner, AsyncMock(return_value=result)):
        assert await call(backend) is result
    backend.leave_transaction_without_saving.assert_awaited_once_with(tcode)
