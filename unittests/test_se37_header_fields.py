"""SE37 on the desktop: the header data of a function module is on the attributes tab, read by field name."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, RETRYABLE_COM_ERRORS
from sapguimcp.tools.se37_tools import _read_se37_header


class _ComError(Exception):
    """A COM error as the COM thread sees it: the HRESULT is the first argument."""

    def __init__(self, code: int) -> None:
        super().__init__(code)


def _flatten(tree: list[Any]) -> list[Any]:
    return tree


def _element(name: str, text: str = "", kind: int = 31) -> Any:
    return SimpleNamespace(id=f"/wnd[0]/usr/tabs/{name}", name=name, text=text, type_as_number=kind)


def _session(elements: list[Any], remote: bool) -> Any:
    window = SimpleNamespace(dump_tree=lambda: elements)

    def find_by_id(element_id: str, **_: Any) -> Any:
        return window if element_id == "wnd[0]" else SimpleNamespace(selected=remote)

    return SimpleNamespace(find_by_id=find_by_id)


_ELEMENTS = [
    _element("HEADER-NAME", "Z_FUNCTION"),
    _element("HEADER-AREA", " ZGROUP "),
    _element("HEADER-AREAT", "text of the group"),
    _element("TFTIT-STEXT", "Short text of the function"),
    _element("TADIR-DEVCLASS", "ZPACKAGE"),
    _element("RS38L-NORMAL", kind=41),
    _element("RS38L-REMOTE", "Remote-enabled function module", kind=41),
]


def test_group_short_text_package_and_the_remote_flag_are_read_by_field_name() -> None:
    assert _read_se37_header(_session(_ELEMENTS, remote=True), _flatten) == {
        "HEADER-AREA": "ZGROUP",
        "TFTIT-STEXT": "Short text of the function",
        "TADIR-DEVCLASS": "ZPACKAGE",
        "RS38L-REMOTE": True,
    }


def test_a_function_module_that_is_not_remote_enabled_reads_false() -> None:
    assert _read_se37_header(_session(_ELEMENTS, remote=False), _flatten)["RS38L-REMOTE"] is False


def test_a_screen_without_the_attributes_tab_gives_no_values() -> None:
    assert _read_se37_header(_session([_element("HEADER-NAME", "Z_FUNCTION")], remote=True), _flatten) == {}


def test_a_label_with_the_name_of_a_field_is_not_taken_for_the_field() -> None:
    labels = [_element("HEADER-AREA", "Function group", kind=30), _element("RS38L-REMOTE", "Remote", kind=30)]
    elements = [*labels, *_ELEMENTS, *labels]  # the labels come before and after the fields
    assert _read_se37_header(_session(elements, remote=True), _flatten)["HEADER-AREA"] == "ZGROUP"
    assert _read_se37_header(_session(labels, remote=True), _flatten) == {}


def test_a_radio_button_that_cannot_be_read_is_left_out_while_the_other_values_are_kept() -> None:
    window = SimpleNamespace(dump_tree=lambda: _ELEMENTS)

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        raise OSError("not readable")

    assert _read_se37_header(SimpleNamespace(find_by_id=find_by_id), _flatten) == {
        "HEADER-AREA": "ZGROUP",
        "TFTIT-STEXT": "Short text of the function",
        "TADIR-DEVCLASS": "ZPACKAGE",
    }


@pytest.mark.parametrize("code", [*RETRYABLE_COM_ERRORS, _RPC_E_DISCONNECTED])
def test_a_com_error_the_com_thread_retries_or_a_lost_connection_is_not_swallowed(code: int) -> None:
    window = SimpleNamespace(dump_tree=lambda: _ELEMENTS)

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        raise _ComError(code)

    with pytest.raises(_ComError):
        _read_se37_header(SimpleNamespace(find_by_id=find_by_id), _flatten)


def test_an_unreadable_radio_button_does_not_stop_the_fields_after_it() -> None:
    elements = [_element("RS38L-REMOTE", "Remote", kind=41), _element("TADIR-DEVCLASS", "ZPACKAGE")]
    window = SimpleNamespace(dump_tree=lambda: elements)

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        raise OSError("not readable")

    assert _read_se37_header(SimpleNamespace(find_by_id=find_by_id), _flatten) == {"TADIR-DEVCLASS": "ZPACKAGE"}
