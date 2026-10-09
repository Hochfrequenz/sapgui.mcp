"""``get_form_fields``: ``checked`` of a checkbox or radio button is its ``Selected`` state, not its caption."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend

_USR = "/app/con[1]/ses[0]/wnd[0]/usr/"


class _ComError(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.hresult = code
        self.args = (code, "COM error", None, None)


def _element(name: str, type_as_number: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(id=f"{_USR}{name}", name=name, type_as_number=type_as_number, text=text, children=[])


class _Session:
    """Window with a text field, two checkboxes (one selected) and two radio buttons (one selected)."""

    def __init__(self, selected: dict[str, Any]) -> None:
        self._selected = selected
        self.elements = [
            _element("TSTC-TCODE", 31, "SE16"),
            _element("CHK_ON", 42, "Option on"),
            _element("CHK_OFF", 42, "Option off"),
            _element("RAD_ON", 41, "Radio on"),
            _element("RAD_OFF", 41, "Radio off"),
        ]

    def find_by_id(self, element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]/usr":
            return SimpleNamespace(dump_tree=lambda: self.elements)
        if element_id in ("wnd[1]", "wnd[2]", "wnd[3]"):
            return None  # no popup
        value = self._selected[element_id.removeprefix(_USR)]
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(selected=value)


async def _form_fields(session: _Session) -> Any:
    backend = DesktopBackend(com_thread=MagicMock())

    async def _run(function: Any, **_: Any) -> Any:
        return function()

    backend.com.run = _run  # type: ignore[method-assign]
    with patch.object(DesktopBackend, "require_session", return_value=session):
        return await backend.get_form_fields()


@pytest.mark.anyio
async def test_checked_is_the_selected_state_not_the_caption() -> None:
    session = _Session({"CHK_ON": True, "CHK_OFF": False, "RAD_ON": True, "RAD_OFF": False})
    result = await _form_fields(session)
    checked = {field.id.removeprefix(_USR): field.checked for field in result.fields}
    assert checked == {"TSTC-TCODE": None, "CHK_ON": True, "CHK_OFF": False, "RAD_ON": True, "RAD_OFF": False}


@pytest.mark.anyio
async def test_a_box_whose_state_cannot_be_read_is_unknown_and_the_others_are_still_read() -> None:
    session = _Session({"CHK_ON": True, "CHK_OFF": _ComError(-2147352567), "RAD_ON": False, "RAD_OFF": False})
    result = await _form_fields(session)
    checked = {field.id.removeprefix(_USR): field.checked for field in result.fields}
    assert checked["CHK_OFF"] is None
    assert checked["CHK_ON"] is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code", [-2147417851, -2147418111, -2147023179, -2147417848]
)  # retry later, rejected, stale, gone
async def test_a_transient_com_error_is_not_swallowed(code: int) -> None:
    session = _Session({"CHK_ON": _ComError(code), "CHK_OFF": False, "RAD_ON": False, "RAD_OFF": False})
    with pytest.raises(Exception) as excinfo:  # noqa: PT011 - the COM error type is a fake
        await _form_fields(session)
    assert isinstance(excinfo.value, _ComError)
