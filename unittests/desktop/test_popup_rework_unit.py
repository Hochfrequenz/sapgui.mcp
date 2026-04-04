"""Unit tests for active window detection, element finder wnd_id, and button tooltip fallback."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from sapwebguimcp.backend.desktop import _active_window_id, _flatten


def _make_session(*, has_wnd1: bool = False, has_wnd2: bool = False, has_wnd3: bool = False) -> MagicMock:
    """Create a mock session with configurable open windows."""
    session = MagicMock()
    windows = {"wnd[0]": MagicMock()}
    if has_wnd1:
        windows["wnd[1]"] = MagicMock()
    if has_wnd2:
        windows["wnd[2]"] = MagicMock()
    if has_wnd3:
        windows["wnd[3]"] = MagicMock()

    def find_by_id(element_id: str, raise_error: bool = True):
        result = windows.get(element_id)
        if result is None and raise_error:
            raise Exception(f"Element not found: {element_id}")
        return result

    session.find_by_id = find_by_id
    return session


def _make_element(*, id: str, type_as_number: int, text: str, name: str = ""):
    """Create a mock ElementInfo for dump_tree results."""
    elem = MagicMock()
    elem.id = id
    elem.type_as_number = type_as_number
    elem.text = text
    elem.name = name
    elem.children = []
    return elem


# ---- Active window detection ----


def test_active_window_no_popup():
    session = _make_session()
    assert _active_window_id(session) == "wnd[0]"


def test_active_window_wnd1():
    session = _make_session(has_wnd1=True)
    assert _active_window_id(session) == "wnd[1]"


def test_active_window_wnd2():
    session = _make_session(has_wnd1=True, has_wnd2=True)
    assert _active_window_id(session) == "wnd[2]"


def test_active_window_wnd3():
    session = _make_session(has_wnd1=True, has_wnd2=True, has_wnd3=True)
    assert _active_window_id(session) == "wnd[3]"


# ---- Button tooltip fallback (#570) ----


def _run_button_discovery(tree_elements: list, session: MagicMock) -> list[dict]:
    """Replicate the discover_buttons / check_popup button-collection logic."""
    buttons: list[dict] = []
    for elem in _flatten(tree_elements):
        if elem.type_as_number != 40:
            continue
        label = elem.text.strip()
        if not label:
            try:
                btn_com = session.find_by_id(elem.id)
                label = str(cast(Any, btn_com).tooltip).strip()
            except Exception:
                pass
        if label:
            buttons.append({"label": label, "id": elem.id})
    return buttons


def test_button_with_text_found():
    """Standard button with .text is discovered normally."""
    btn = _make_element(id="wnd[0]/usr/btnSAVE", type_as_number=40, text="Save")
    session = MagicMock()
    buttons = _run_button_discovery([btn], session)
    assert len(buttons) == 1
    assert buttons[0]["label"] == "Save"


def test_button_with_tooltip_only_found():
    """Toolbar button with empty .text but .tooltip is discovered via fallback."""
    btn = _make_element(id="wnd[0]/tbar[0]/btn[0]", type_as_number=40, text="")
    btn_com = MagicMock()
    btn_com.tooltip = "Weiter   (Enter)"
    session = MagicMock()
    session.find_by_id = MagicMock(return_value=btn_com)

    buttons = _run_button_discovery([btn], session)
    assert len(buttons) == 1
    assert buttons[0]["label"] == "Weiter   (Enter)"


def test_button_with_no_text_and_no_tooltip_skipped():
    """Button with empty .text AND empty .tooltip is skipped."""
    btn = _make_element(id="wnd[0]/tbar[0]/btn[99]", type_as_number=40, text="")
    btn_com = MagicMock()
    btn_com.tooltip = ""
    session = MagicMock()
    session.find_by_id = MagicMock(return_value=btn_com)

    buttons = _run_button_discovery([btn], session)
    assert len(buttons) == 0


def test_mixed_buttons_text_and_tooltip():
    """Mix of text buttons and tooltip-only buttons all discovered."""
    btn_text = _make_element(id="wnd[0]/usr/btnOK", type_as_number=40, text="OK")
    btn_tooltip = _make_element(id="wnd[0]/tbar[0]/btn[0]", type_as_number=40, text="")
    btn_empty = _make_element(id="wnd[0]/tbar[0]/btn[99]", type_as_number=40, text="")
    non_button = _make_element(id="wnd[0]/usr/lblFOO", type_as_number=30, text="Label")

    btn_com_weiter = MagicMock()
    btn_com_weiter.tooltip = "Weiter   (Enter)"
    btn_com_empty = MagicMock()
    btn_com_empty.tooltip = "  "

    def find_by_id(eid, raise_error=True):
        if eid == "wnd[0]/tbar[0]/btn[0]":
            return btn_com_weiter
        if eid == "wnd[0]/tbar[0]/btn[99]":
            return btn_com_empty
        return None

    session = MagicMock()
    session.find_by_id = find_by_id

    buttons = _run_button_discovery([btn_text, btn_tooltip, btn_empty, non_button], session)
    assert len(buttons) == 2
    assert buttons[0]["label"] == "OK"
    assert buttons[1]["label"] == "Weiter   (Enter)"
