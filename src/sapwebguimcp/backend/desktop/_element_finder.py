"""Resolve label text to COM elements for the desktop backend.

The core challenge: protocol methods use labels (e.g., fill_field(label="Material")),
but COM uses ID paths. This module resolves labels to COM elements using four
strategies tried in order:

1. Name-prefix convention: label with name FOO -> try txtFOO, ctxtFOO, pwdFOO, cmbFOO
2. Recursive label text match: walk usr subtree, find GuiLabel matching text, then find
   associated field via name prefix
3. Read-only text field label: non-changeable GuiTextField as visual label, supports
   composite labels like "Straße/Hausnummer" → street + house number fields
4. find_by_name fallback: use SAP's native FindByName
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


def _dump_flat_tree(session: Any, wnd_id: str = "wnd[0]") -> list[Any]:
    """Dump and flatten the ``usr`` subtree of the given window.

    Centralises the ``find_by_id(...)/dump_tree()/_flatten()`` idiom so that
    callers in the desktop backend can compute the flat tree once and pass it
    into ``find_field_by_label`` (and its tree-using strategy helpers) without
    each helper redundantly re-dumping the tree.
    """
    usr = session.find_by_id(f"{wnd_id}/usr")
    return _flatten(usr.dump_tree())


def _extract_container_path(label_id: str, wnd_id: str = "wnd[0]") -> str:
    """Extract container path from a label's full ID.

    '/app/con[0]/ses[0]/wnd[0]/usr/sub/lblFOO' -> 'wnd[0]/usr/sub/'
    '/app/con[0]/ses[0]/wnd[1]/usr/lblBAR' -> 'wnd[1]/usr/'
    """
    parts = label_id.split("/")
    for i, p in enumerate(parts):
        if p.startswith("wnd["):
            rel_path = "/".join(parts[i:])
            last_slash = rel_path.rfind("/")
            return rel_path[: last_slash + 1]
    return f"{wnd_id}/usr/"


def _find_by_name_prefix(session: Any, label_name: str, path_prefix: str = "wnd[0]/usr/") -> Any | None:
    """Strategy 1: Label lblFOO -> try txtFOO, ctxtFOO, pwdFOO, cmbFOO, chkFOO, radFOO."""
    for prefix in _INPUT_PREFIXES:
        field = session.find_by_id(path_prefix + prefix + label_name, raise_error=False)
        if field is not None:
            return field
    return None


def _find_by_label_text(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None:
    """Strategy 2: Find a field via a matching ``GuiLabel`` in ``flat_tree``.

    The caller is responsible for providing a flat tree (typically via
    :func:`_dump_flat_tree`). This helper no longer fetches its own tree so
    that batch callers like ``desktop.fill_form`` can share one tree across
    many label lookups.

    Prefers exact match (after stripping) over substring match.
    """
    needle = label.strip().lower()

    # First pass: exact match
    for elem in flat_tree:
        if elem.type_as_number == _TYPE_LABEL and elem.text.strip().lower() == needle:
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            field = _find_by_name_prefix(session, elem.name, path_prefix)
            if field is not None:
                return field

    # Second pass: substring match
    for elem in flat_tree:
        if elem.type_as_number == _TYPE_LABEL and needle in elem.text.strip().lower():
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            field = _find_by_name_prefix(session, elem.name, path_prefix)
            if field is not None:
                return field

    return None


def _find_by_readonly_textfield_label(  # pylint: disable=too-many-locals
    session: Any,
    label: str,
    flat_tree: list[Any],
) -> Any | None:
    """Strategy 3: Non-changeable ``GuiTextField`` acting as visual label.

    SAP address screens use read-only ``GuiTextField`` (type 31,
    ``changeable=False``) as labels. Examples: "Straße/Hausnummer",
    "Postleitzahl/Ort".

    For composite labels containing ``"/"``, the label text is split and each
    part is matched to the consecutive changeable input fields that follow the
    label in the flat tree. Example: "Straße" → ``ADDR2_DATA-STREET``,
    "Hausnummer" → ``ADDR2_DATA-HOUSE_NUM1``.

    Also supports the full composite text (e.g. "Straße/Hausnummer" → first
    field).

    The caller provides ``flat_tree``; this helper no longer dumps its own.
    """
    needle = label.strip().lower()
    input_types = {_TYPE_TEXT_FIELD, _TYPE_CTEXT_FIELD, _TYPE_PASSWORD_FIELD, _TYPE_COMBOBOX}

    for i, elem in enumerate(flat_tree):
        # Only consider non-changeable text fields as labels
        if elem.type_as_number != _TYPE_TEXT_FIELD or elem.changeable:
            continue
        elem_text = elem.text.strip().lower()
        if not elem_text:
            continue

        # Collect consecutive changeable input fields that follow this label
        following_inputs: list[Any] = []
        for j in range(i + 1, len(flat_tree)):
            sibling = flat_tree[j]
            if sibling.type_as_number in input_types and sibling.changeable:
                following_inputs.append(sibling)
            elif sibling.type_as_number in input_types and not sibling.changeable:
                continue  # Skip other read-only text fields (might be another label)
            else:
                break  # Stop at non-input elements (buttons, boxes, containers)

        if not following_inputs:
            continue

        # Exact match on full composite label → first input field
        if elem_text == needle:
            return session.find_by_id(following_inputs[0].id)

        # Split composite label on "/" and match individual parts
        if "/" in elem_text:
            parts = [p.strip().lower() for p in elem_text.split("/")]
            for idx, part in enumerate(parts):
                if part == needle and idx < len(following_inputs):
                    return session.find_by_id(following_inputs[idx].id)

    return None


def _find_by_sap_name(session: Any, label: str, wnd_id: str = "wnd[0]") -> Any | None:
    """Strategy 4: Use SAP's native FindByName for GuiTextField."""
    usr = session.find_by_id(f"{wnd_id}/usr")
    for type_name in ("GuiTextField", "GuiCTextField", "GuiPasswordField", "GuiComboBox"):
        try:
            result = usr.find_by_name(label, type_name)
            if result is not None:
                return result
        except Exception:  # pylint: disable=broad-exception-caught
            continue
    return None


def find_field_by_label(
    session: Any,
    label: str,
    flat_tree: list[Any],
    wnd_id: str = "wnd[0]",
) -> Any | None:
    """Find an input field by its associated label text.

    The caller must provide a ``flat_tree`` (typically obtained via
    :func:`_dump_flat_tree`). Strategies 2 and 3 walk this list directly
    instead of dumping their own tree, so a batch caller like
    ``desktop.fill_form`` can hoist the dump out of its per-field loop.

    Strategies (tried in order):

    1. Name-prefix convention: label ``lblFOO`` -> try ``txtFOO``, ``ctxtFOO``,
       ``pwdFOO``, ``cmbFOO``
    2. Recursive label text match: walk ``flat_tree``, find label matching
       text, then find associated field via name prefix
    3. Read-only text field label: non-changeable ``GuiTextField`` as visual
       label, supports composite labels like "Straße/Hausnummer"
    4. ``find_by_name`` fallback: use SAP's native ``FindByName``
    """
    # Strategy 1: direct name prefix
    field = _find_by_name_prefix(session, label, path_prefix=f"{wnd_id}/usr/")
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "name_prefix"})
        return field

    # Strategy 2: label text match (GuiLabel type 30)
    field = _find_by_label_text(session, label, flat_tree, wnd_id=wnd_id)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "label_text"})
        return field

    # Strategy 3: read-only text field label (composite labels like "Straße/Hausnummer")
    field = _find_by_readonly_textfield_label(session, label, flat_tree)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "readonly_textfield_label"})
        return field

    # Strategy 4: SAP native FindByName
    field = _find_by_sap_name(session, label, wnd_id=wnd_id)
    if field is not None:
        logger.debug("find_field", extra={"label": label, "strategy": "sap_name"})
        return field

    logger.debug("find_field", extra={"label": label, "strategy": "not_found"})
    return None


def find_button_by_label(session: Any, label: str, wnd_id: str = "wnd[0]") -> Any | None:
    """Find a button (GuiButton type 40) by its text label.

    Prefers exact match (after stripping) over substring match.
    """
    wnd = session.find_by_id(wnd_id)
    tree = wnd.dump_tree()
    flat = _flatten(tree)
    needle = label.strip().lower()

    # First pass: exact match
    for elem in flat:
        if elem.type_as_number == _TYPE_BUTTON and elem.text.strip().lower() == needle:
            return session.find_by_id(elem.id)

    # Second pass: substring match
    for elem in flat:
        if elem.type_as_number == _TYPE_BUTTON and needle in elem.text.strip().lower():
            return session.find_by_id(elem.id)

    return None


def find_checkbox_by_label(session: Any, label: str, wnd_id: str = "wnd[0]") -> Any | None:
    """Find a checkbox (type 42) by adjacent label text or its own text.

    Prefers exact match (after stripping) over substring match.
    """
    usr = session.find_by_id(f"{wnd_id}/usr")
    tree = usr.dump_tree()
    flat = _flatten(tree)
    needle = label.strip().lower()

    # Exact match on checkbox text
    for elem in flat:
        if elem.type_as_number == _TYPE_CHECKBOX and elem.text.strip().lower() == needle:
            return session.find_by_id(elem.id)

    # Exact match on label, then look for checkbox with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and elem.text.strip().lower() == needle:
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            chk = session.find_by_id(path_prefix + "chk" + elem.name, raise_error=False)
            if chk is not None:
                return chk

    # Substring match on checkbox text
    for elem in flat:
        if elem.type_as_number == _TYPE_CHECKBOX and needle in elem.text.strip().lower():
            return session.find_by_id(elem.id)

    # Substring match on label, then look for checkbox with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and needle in elem.text.strip().lower():
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            chk = session.find_by_id(path_prefix + "chk" + elem.name, raise_error=False)
            if chk is not None:
                return chk

    return None


def find_radio_by_label(session: Any, label: str, wnd_id: str = "wnd[0]") -> Any | None:
    """Find a radio button (type 41) by adjacent label text or its own text.

    Prefers exact match (after stripping) over substring match.
    """
    usr = session.find_by_id(f"{wnd_id}/usr")
    tree = usr.dump_tree()
    flat = _flatten(tree)
    needle = label.strip().lower()

    # Exact match on radio text
    for elem in flat:
        if elem.type_as_number == _TYPE_RADIO and elem.text.strip().lower() == needle:
            return session.find_by_id(elem.id)

    # Exact match on label, then look for radio with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and elem.text.strip().lower() == needle:
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            rad = session.find_by_id(path_prefix + "rad" + elem.name, raise_error=False)
            if rad is not None:
                return rad

    # Substring match on radio text
    for elem in flat:
        if elem.type_as_number == _TYPE_RADIO and needle in elem.text.strip().lower():
            return session.find_by_id(elem.id)

    # Substring match on label, then look for radio with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and needle in elem.text.strip().lower():
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            rad = session.find_by_id(path_prefix + "rad" + elem.name, raise_error=False)
            if rad is not None:
                return rad

    return None


def find_tab_by_label(session: Any, label: str, wnd_id: str = "wnd[0]") -> Any | None:
    """Find a tab (GuiTab type 91) by its text.

    Prefers exact match (after stripping) over substring match.
    """
    wnd = session.find_by_id(wnd_id)
    tree = wnd.dump_tree()
    flat = _flatten(tree)
    needle = label.strip().lower()

    # First pass: exact match
    for elem in flat:
        if elem.type_as_number == _TYPE_TAB and elem.text.strip().lower() == needle:
            return session.find_by_id(elem.id)

    # Second pass: substring match
    for elem in flat:
        if elem.type_as_number == _TYPE_TAB and needle in elem.text.strip().lower():
            return session.find_by_id(elem.id)

    return None


def find_combobox_by_label(session: Any, label: str, wnd_id: str = "wnd[0]") -> Any | None:
    """Find a combobox (type 34) by adjacent label.

    Prefers exact match (after stripping) over substring match.
    """
    usr = session.find_by_id(f"{wnd_id}/usr")
    tree = usr.dump_tree()
    flat = _flatten(tree)
    needle = label.strip().lower()

    # Exact match on combobox text
    for elem in flat:
        if elem.type_as_number == _TYPE_COMBOBOX and elem.text.strip().lower() == needle:
            return session.find_by_id(elem.id)

    # Exact match on label, then look for combobox with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and elem.text.strip().lower() == needle:
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            cmb = session.find_by_id(path_prefix + "cmb" + elem.name, raise_error=False)
            if cmb is not None:
                return cmb

    # Substring match on combobox text
    for elem in flat:
        if elem.type_as_number == _TYPE_COMBOBOX and needle in elem.text.strip().lower():
            return session.find_by_id(elem.id)

    # Substring match on label, then look for combobox with same name
    for elem in flat:
        if elem.type_as_number == _TYPE_LABEL and needle in elem.text.strip().lower():
            path_prefix = _extract_container_path(elem.id, wnd_id=wnd_id)
            cmb = session.find_by_id(path_prefix + "cmb" + elem.name, raise_error=False)
            if cmb is not None:
                return cmb

    return None
