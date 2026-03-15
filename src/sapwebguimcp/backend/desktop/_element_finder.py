"""Resolve label text to COM elements for the desktop backend.

The core challenge: protocol methods use labels (e.g., fill_field(label="Material")),
but COM uses ID paths. This module resolves labels to COM elements using three
strategies tried in order:

1. Name-prefix convention: label with name FOO -> try txtFOO, ctxtFOO, pwdFOO, cmbFOO
2. Recursive label text match: walk usr subtree, find label matching text, then find
   associated field via name prefix
3. find_by_name fallback: use SAP's native FindByName
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# SAP GUI type numbers
_TYPE_LABEL = 30
_TYPE_TEXT_FIELD = 31
_TYPE_CTEXT_FIELD = 32
_TYPE_PASSWORD_FIELD = 33
_TYPE_COMBOBOX = 34
_TYPE_BUTTON = 40
_TYPE_RADIO = 41
_TYPE_CHECKBOX = 42
_TYPE_TAB = 91

_INPUT_PREFIXES = ("txt", "ctxt", "pwd", "cmb", "chk", "rad")


def _flatten(tree: list[Any]) -> list[Any]:
    """Flatten a nested ElementInfo tree into a flat list."""
    result: list[Any] = []
    for elem in tree:
        result.append(elem)
        if elem.children:
            result.extend(_flatten(elem.children))
    return result


def _find_by_name_prefix(session: Any, label_name: str) -> Any | None:
    """Strategy 1: Label lblFOO -> try txtFOO, ctxtFOO, pwdFOO, cmbFOO, chkFOO, radFOO."""
    for prefix in _INPUT_PREFIXES:
        field = session.find_by_id("wnd[0]/usr/" + prefix + label_name, raise_error=False)
        if field is not None:
            return field
    return None


def _find_by_label_text(session: Any, label: str) -> Any | None:
    """Strategy 2: Walk usr subtree, find label matching text, then find field via name prefix."""
    usr = session.find_by_id("wnd[0]/usr")
    tree = usr.dump_tree(max_depth=5)
    for elem in _flatten(tree):
        if elem.type_as_number == _TYPE_LABEL and label.lower() in elem.text.lower():
            field_name = elem.name
            field = _find_by_name_prefix(session, field_name)
            if field is not None:
                return field
    return None


def _find_by_sap_name(session: Any, label: str) -> Any | None:
    """Strategy 3: Use SAP's native FindByName for GuiTextField."""
    usr = session.find_by_id("wnd[0]/usr")
    for type_name in ("GuiTextField", "GuiCTextField", "GuiPasswordField", "GuiComboBox"):
        try:
            return usr.find_by_name(label, type_name)
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return None


def find_field_by_label(session: Any, label: str) -> Any | None:
    """Find an input field by its associated label text.

    Strategies (tried in order):
    1. Name-prefix convention: label lblFOO -> try txtFOO, ctxtFOO, pwdFOO, cmbFOO
    2. Recursive label text match: walk usr subtree, find label matching text,
       then find associated field via name prefix
    3. find_by_name fallback: use SAP's native FindByName
    """
    # Strategy 1: direct name prefix
    field = _find_by_name_prefix(session, label)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "name_prefix"})
        return field

    # Strategy 2: label text match
    field = _find_by_label_text(session, label)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "label_text"})
        return field

    # Strategy 3: SAP native FindByName
    field = _find_by_sap_name(session, label)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "sap_name"})
        return field

    logger.debug("find_field", extra={"label": label, "strategy": "not_found"})
    return None


def find_button_by_label(session: Any, label: str) -> Any | None:
    """Find a button (GuiButton type 40) by its text label."""
    wnd = session.find_by_id("wnd[0]")
    tree = wnd.dump_tree(max_depth=5)
    for elem in _flatten(tree):
        if elem.type_as_number == _TYPE_BUTTON and label.lower() in elem.text.lower():
            return session.find_by_id(elem.id)
    return None


def find_checkbox_by_label(session: Any, label: str) -> Any | None:
    """Find a checkbox (type 42) by adjacent label text or its own text."""
    usr = session.find_by_id("wnd[0]/usr")
    tree = usr.dump_tree(max_depth=5)
    flat = _flatten(tree)

    # First try: checkbox with matching text
    for elem in flat:
        if elem.type_as_number == _TYPE_CHECKBOX and label.lower() in elem.text.lower():
            return session.find_by_id(elem.id)

    # Second try: find label, then look for checkbox with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and label.lower() in elem.text.lower():
            chk = session.find_by_id("wnd[0]/usr/chk" + elem.name, raise_error=False)
            if chk is not None:
                return chk

    return None


def find_radio_by_label(session: Any, label: str) -> Any | None:
    """Find a radio button (type 41) by adjacent label text or its own text."""
    usr = session.find_by_id("wnd[0]/usr")
    tree = usr.dump_tree(max_depth=5)
    flat = _flatten(tree)

    # First try: radio with matching text
    for elem in flat:
        if elem.type_as_number == _TYPE_RADIO and label.lower() in elem.text.lower():
            return session.find_by_id(elem.id)

    # Second try: find label, then look for radio with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and label.lower() in elem.text.lower():
            rad = session.find_by_id("wnd[0]/usr/rad" + elem.name, raise_error=False)
            if rad is not None:
                return rad

    return None


def find_tab_by_label(session: Any, label: str) -> Any | None:
    """Find a tab (GuiTab type 91) by its text."""
    wnd = session.find_by_id("wnd[0]")
    tree = wnd.dump_tree(max_depth=5)
    for elem in _flatten(tree):
        if elem.type_as_number == _TYPE_TAB and label.lower() in elem.text.lower():
            return session.find_by_id(elem.id)
    return None


def find_combobox_by_label(session: Any, label: str) -> Any | None:
    """Find a combobox (type 34) by adjacent label."""
    usr = session.find_by_id("wnd[0]/usr")
    tree = usr.dump_tree(max_depth=5)
    flat = _flatten(tree)

    # First try: combobox with matching text
    for elem in flat:
        if elem.type_as_number == _TYPE_COMBOBOX and label.lower() in elem.text.lower():
            return session.find_by_id(elem.id)

    # Second try: find label, then look for combobox with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and label.lower() in elem.text.lower():
            cmb = session.find_by_id("wnd[0]/usr/cmb" + elem.name, raise_error=False)
            if cmb is not None:
                return cmb

    return None
