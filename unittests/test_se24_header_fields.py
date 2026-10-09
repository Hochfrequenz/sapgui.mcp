"""SE24 on the desktop: the header data of a class or interface is on the properties tab, read by field name."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, RETRYABLE_COM_ERRORS
from sapguimcp.tools.se24_tools import _read_se24_header

_TEXT, _CTEXT, _COMBO, _CHECK, _LABEL = 31, 32, 34, 42, 30


class _ComError(Exception):
    """A COM error as the COM thread sees it: the HRESULT is the first argument."""

    def __init__(self, code: int) -> None:
        super().__init__(code)


def _flatten(tree: list[Any]) -> list[Any]:
    return tree


def _element(name: str, text: str, kind: int) -> Any:
    return SimpleNamespace(id=f"/wnd[0]/usr/{name}", name=name, text=text, type_as_number=kind)


def _session(elements: list[Any], *, final: bool = False, key: str = "0") -> Any:
    window = SimpleNamespace(dump_tree=lambda: elements)

    def find_by_id(element_id: str, **_: Any) -> Any:
        return window if element_id == "wnd[0]" else SimpleNamespace(selected=final, key=key)

    return SimpleNamespace(find_by_id=find_by_id)


def _class(*, instantiation: str = "Public", superclass: str | None = None) -> list[Any]:
    elements = [
        _element("VSEOCLASS-CLSNAME", "ZCL_EXAMPLE", _TEXT),
        _element("VSEOCLASS-DESCRIPT", " An example class ", _TEXT),
        _element("SEOX-CREATABLE", instantiation, _COMBO),
        _element("VSEOCLASS-CLSFINAL", "Final", _CHECK),
        _element("DY_0152-DEVCLASS", "ZPACKAGE", _TEXT),
    ]
    if superclass:
        elements.append(_element("DY_0152-SUPERCLASS", superclass, _CTEXT))
    return elements


def test_description_package_and_the_flags_of_a_class_are_read_by_field_name() -> None:
    assert _read_se24_header(_session(_class(), final=True), _flatten) == {
        "description": "An example class",
        "package": "ZPACKAGE",
        "is_abstract": False,
        "is_final": True,
    }


def test_a_class_instantiated_abstract_is_abstract_by_the_key_of_the_combo_box_in_any_language() -> None:
    # the text is that of the logon language: only the key tells in every language
    elements = _class(instantiation="Abstraite")
    assert _read_se24_header(_session(elements, key="3"), _flatten)["is_abstract"] is True
    assert _read_se24_header(_session(elements, key="0"), _flatten)["is_abstract"] is False


@pytest.mark.parametrize("text", ["Abstrakt", "Abstract", " abstrakt "])
def test_the_text_decides_when_the_key_cannot_be_read(text: str) -> None:
    window = SimpleNamespace(dump_tree=lambda: _class(instantiation=text))

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        raise OSError("key not readable")

    assert _read_se24_header(SimpleNamespace(find_by_id=find_by_id), _flatten)["is_abstract"] is True


def test_a_subclass_names_its_superclass_and_a_class_without_one_has_no_key() -> None:
    assert _read_se24_header(_session(_class(superclass="ZCL_BASE")), _flatten)["superclass"] == "ZCL_BASE"
    assert "superclass" not in _read_se24_header(_session(_class()), _flatten)


def test_an_interface_has_its_own_description_and_package_fields() -> None:
    elements = [
        _element("VSEOINTERF-DESCRIPT", "An interface", _TEXT),
        _element("DY_0153-DEVCLASS", "ZPACKAGE", _TEXT),
    ]
    assert _read_se24_header(_session(elements), _flatten) == {"description": "An interface", "package": "ZPACKAGE"}


def test_a_label_with_the_name_of_a_field_is_not_taken_for_the_field() -> None:
    labels = [
        _element("VSEOCLASS-DESCRIPT", "Short description", _LABEL),
        _element("DY_0152-DEVCLASS", "Package", _LABEL),
    ]
    assert _read_se24_header(_session([*labels, *_class(), *labels]), _flatten)["description"] == "An example class"
    assert _read_se24_header(_session(labels), _flatten) == {}


def test_a_screen_without_the_properties_tab_gives_no_values() -> None:
    assert _read_se24_header(_session([_element("VSEOCLASS-CLSNAME", "ZCL_EXAMPLE", _TEXT)]), _flatten) == {}


def test_a_checkbox_that_cannot_be_read_is_left_out_while_the_other_values_are_kept() -> None:
    window = SimpleNamespace(dump_tree=_class)

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        raise OSError("not readable")

    values = _read_se24_header(SimpleNamespace(find_by_id=find_by_id), _flatten)
    assert values["description"] == "An example class"
    assert "is_final" not in values


@pytest.mark.parametrize("code", [*RETRYABLE_COM_ERRORS, _RPC_E_DISCONNECTED])
def test_a_com_error_the_com_thread_retries_or_a_lost_connection_is_not_swallowed(code: int) -> None:
    window = SimpleNamespace(dump_tree=_class)

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        raise _ComError(code)

    with pytest.raises(_ComError):
        _read_se24_header(SimpleNamespace(find_by_id=find_by_id), _flatten)


def test_an_unreadable_element_does_not_stop_the_elements_after_it() -> None:
    # the final checkbox comes before the combo box and the package: it cannot be read, the others still are
    window = SimpleNamespace(dump_tree=_class)

    def find_by_id(element_id: str, **_: Any) -> Any:
        if element_id == "wnd[0]":
            return window
        if element_id.endswith("CLSFINAL"):
            raise OSError("not readable")
        return SimpleNamespace(selected=False, key="3")

    values = _read_se24_header(SimpleNamespace(find_by_id=find_by_id), _flatten)
    assert "is_final" not in values
    assert (values["is_abstract"], values["package"]) == (True, "ZPACKAGE")
