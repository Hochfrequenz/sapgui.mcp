"""Tests for the desktop element finder module."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sapwebguimcp.backend.desktop._element_finder import (
    find_button_by_label,
    find_checkbox_by_label,
    find_combobox_by_label,
    find_field_by_label,
    find_radio_by_label,
    find_tab_by_label,
)


def _make_elem(
    *,
    type_as_number: int = 30,
    name: str = "FIELD1",
    text: str = "",
    elem_id: str = "wnd[0]/usr/lblFIELD1",
    elem_type: str = "GuiLabel",
    changeable: bool = False,
    children: list | None = None,
) -> SimpleNamespace:
    """Create a mock ElementInfo."""
    return SimpleNamespace(
        type_as_number=type_as_number,
        name=name,
        text=text,
        id=elem_id,
        type=elem_type,
        changeable=changeable,
        children=children or [],
    )


def _make_session_with_tree(
    tree_elements: list,
    find_by_id_extras: dict | None = None,
) -> MagicMock:
    """Create a mock session whose usr.dump_tree returns the given elements."""
    session = MagicMock()
    usr = MagicMock()
    usr.dump_tree.return_value = tree_elements
    wnd = MagicMock()
    wnd.dump_tree.return_value = tree_elements

    extras = find_by_id_extras or {}

    def find_by_id(element_id: str, raise_error: bool = True) -> MagicMock | None:
        if element_id == "wnd[0]/usr":
            return usr
        if element_id == "wnd[0]":
            return wnd
        if element_id in extras:
            return extras[element_id]
        if not raise_error:
            return None
        raise Exception(f"Element not found: {element_id}")

    session.find_by_id = find_by_id
    return session


class TestFindFieldByLabelNamePrefix:
    """Strategy 1: name-prefix convention (lblFOO -> txtFOO)."""

    def test_finds_text_field_by_name(self):
        txt_field = MagicMock()
        session = _make_session_with_tree(
            [],
            find_by_id_extras={"wnd[0]/usr/txtMATNR": txt_field},
        )
        result = find_field_by_label(session, "MATNR")
        assert result is txt_field

    def test_finds_ctext_field_by_name(self):
        ctxt_field = MagicMock()
        session = _make_session_with_tree(
            [],
            find_by_id_extras={"wnd[0]/usr/ctxtMATNR": ctxt_field},
        )
        result = find_field_by_label(session, "MATNR")
        assert result is ctxt_field

    def test_returns_none_when_no_match(self):
        session = _make_session_with_tree([])
        # Make find_by_name raise so strategy 4 also fails
        usr = session.find_by_id("wnd[0]/usr")
        usr.find_by_name.side_effect = Exception("not found")
        result = find_field_by_label(session, "NONEXISTENT")
        assert result is None


class TestFindFieldByLabelText:
    """Strategy 2: label text match via dump_tree."""

    def test_finds_field_via_label_text(self):
        label_elem = _make_elem(
            type_as_number=30,
            name="MATNR",
            text="Material",
            elem_id="wnd[0]/usr/lblMATNR",
        )
        txt_field = MagicMock()
        session = _make_session_with_tree(
            [label_elem],
            find_by_id_extras={"wnd[0]/usr/txtMATNR": txt_field},
        )
        result = find_field_by_label(session, "Material")
        assert result is txt_field

    def test_case_insensitive_label_match(self):
        label_elem = _make_elem(
            type_as_number=30,
            name="BUKRS",
            text="Company Code",
            elem_id="wnd[0]/usr/lblBUKRS",
        )
        ctxt_field = MagicMock()
        session = _make_session_with_tree(
            [label_elem],
            find_by_id_extras={"wnd[0]/usr/ctxtBUKRS": ctxt_field},
        )
        result = find_field_by_label(session, "company code")
        assert result is ctxt_field


class TestFindFieldByLabelSapName:
    """Strategy 4: SAP native FindByName fallback."""

    def test_finds_via_find_by_name(self):
        field_mock = MagicMock()
        session = _make_session_with_tree([])
        usr = session.find_by_id("wnd[0]/usr")
        usr.find_by_name.return_value = field_mock

        result = find_field_by_label(session, "SOME_FIELD")
        assert result is field_mock


class TestFindButtonByLabel:
    def test_finds_button_by_text(self):
        btn_elem = _make_elem(
            type_as_number=40,
            name="BTN_EXEC",
            text="Execute",
            elem_id="wnd[0]/tbar[1]/btn[8]",
            elem_type="GuiButton",
        )
        btn_mock = MagicMock()
        session = _make_session_with_tree(
            [btn_elem],
            find_by_id_extras={"wnd[0]/tbar[1]/btn[8]": btn_mock},
        )
        result = find_button_by_label(session, "Execute")
        assert result is btn_mock

    def test_returns_none_when_no_button(self):
        session = _make_session_with_tree([])
        result = find_button_by_label(session, "NonExistent")
        assert result is None


class TestFindTabByLabel:
    def test_finds_tab_by_text(self):
        tab_elem = _make_elem(
            type_as_number=91,
            name="TAB_ADDR",
            text="Address",
            elem_id="wnd[0]/usr/tabsTABSTRIP/tabpADDR",
            elem_type="GuiTab",
        )
        tab_mock = MagicMock()
        session = _make_session_with_tree(
            [tab_elem],
            find_by_id_extras={"wnd[0]/usr/tabsTABSTRIP/tabpADDR": tab_mock},
        )
        result = find_tab_by_label(session, "Address")
        assert result is tab_mock

    def test_returns_none_when_no_tab(self):
        session = _make_session_with_tree([])
        result = find_tab_by_label(session, "Missing")
        assert result is None


class TestFindCheckboxByLabel:
    def test_finds_checkbox_by_text(self):
        chk_elem = _make_elem(
            type_as_number=42,
            name="ACTIVE",
            text="Active",
            elem_id="wnd[0]/usr/chkACTIVE",
            elem_type="GuiCheckBox",
        )
        chk_mock = MagicMock()
        session = _make_session_with_tree(
            [chk_elem],
            find_by_id_extras={"wnd[0]/usr/chkACTIVE": chk_mock},
        )
        result = find_checkbox_by_label(session, "Active")
        assert result is chk_mock


class TestFindRadioByLabel:
    def test_finds_radio_by_text(self):
        rad_elem = _make_elem(
            type_as_number=41,
            name="OPT_A",
            text="Option A",
            elem_id="wnd[0]/usr/radOPT_A",
            elem_type="GuiRadioButton",
        )
        rad_mock = MagicMock()
        session = _make_session_with_tree(
            [rad_elem],
            find_by_id_extras={"wnd[0]/usr/radOPT_A": rad_mock},
        )
        result = find_radio_by_label(session, "Option A")
        assert result is rad_mock


class TestFindComboboxByLabel:
    def test_finds_combobox_by_label_text(self):
        label_elem = _make_elem(
            type_as_number=30,
            name="SPRAS",
            text="Language",
            elem_id="wnd[0]/usr/lblSPRAS",
        )
        cmb_mock = MagicMock()
        session = _make_session_with_tree(
            [label_elem],
            find_by_id_extras={"wnd[0]/usr/cmbSPRAS": cmb_mock},
        )
        result = find_combobox_by_label(session, "Language")
        assert result is cmb_mock


class TestFindByReadonlyTextfieldLabel:
    """Strategy 3: Read-only GuiTextField as visual label (composite labels)."""

    def test_full_composite_label_resolves_to_first_field(self):
        """'Straße/Hausnummer' → first changeable field (street)."""
        label = _make_elem(
            type_as_number=31,
            name="ADDR2_KEYW-STREET",
            text="Straße/Hausnummer",
            elem_id="wnd[0]/usr/txtADDR2_KEYW-STREET",
            changeable=False,
        )
        street = _make_elem(
            type_as_number=32,
            name="ADDR2_DATA-STREET",
            text="",
            elem_id="wnd[0]/usr/ctxtADDR2_DATA-STREET",
            changeable=True,
        )
        house = _make_elem(
            type_as_number=31,
            name="ADDR2_DATA-HOUSE_NUM1",
            text="",
            elem_id="wnd[0]/usr/txtADDR2_DATA-HOUSE_NUM1",
            changeable=True,
        )
        street_mock = MagicMock()
        session = _make_session_with_tree(
            [label, street, house],
            find_by_id_extras={"wnd[0]/usr/ctxtADDR2_DATA-STREET": street_mock},
        )
        result = find_field_by_label(session, "Straße/Hausnummer")
        assert result is street_mock

    def test_composite_part_resolves_to_correct_field(self):
        """'Hausnummer' → second changeable field."""
        label = _make_elem(
            type_as_number=31,
            name="ADDR2_KEYW-STREET",
            text="Straße/Hausnummer",
            elem_id="wnd[0]/usr/txtADDR2_KEYW-STREET",
            changeable=False,
        )
        street = _make_elem(
            type_as_number=32,
            name="ADDR2_DATA-STREET",
            text="",
            elem_id="wnd[0]/usr/ctxtADDR2_DATA-STREET",
            changeable=True,
        )
        house = _make_elem(
            type_as_number=31,
            name="ADDR2_DATA-HOUSE_NUM1",
            text="",
            elem_id="wnd[0]/usr/txtADDR2_DATA-HOUSE_NUM1",
            changeable=True,
        )
        house_mock = MagicMock()
        session = _make_session_with_tree(
            [label, street, house],
            find_by_id_extras={"wnd[0]/usr/txtADDR2_DATA-HOUSE_NUM1": house_mock},
        )
        result = find_field_by_label(session, "Hausnummer")
        assert result is house_mock

    def test_non_composite_readonly_label(self):
        """Read-only text field without '/' resolves to following input."""
        label = _make_elem(
            type_as_number=31,
            name="LABEL1",
            text="Bemerkungen",
            elem_id="wnd[0]/usr/txtLABEL1",
            changeable=False,
        )
        field = _make_elem(
            type_as_number=31,
            name="REMARK",
            text="",
            elem_id="wnd[0]/usr/txtREMARK",
            changeable=True,
        )
        field_mock = MagicMock()
        session = _make_session_with_tree(
            [label, field],
            find_by_id_extras={"wnd[0]/usr/txtREMARK": field_mock},
        )
        result = find_field_by_label(session, "Bemerkungen")
        assert result is field_mock

    def test_no_following_inputs_returns_none(self):
        """Read-only label with no changeable fields after it → None (if FindByName also fails)."""
        label = _make_elem(
            type_as_number=31,
            name="LABEL1",
            text="Hinweis",
            elem_id="wnd[0]/usr/txtLABEL1",
            changeable=False,
        )
        session = _make_session_with_tree([label])
        # Ensure Strategy 4 (FindByName) also returns nothing
        usr = session.find_by_id("wnd[0]/usr")
        usr.find_by_name.return_value = None
        result = find_field_by_label(session, "Hinweis")
        assert result is None


class TestDumpFlatTree:
    """Helper that dumps and flattens the usr subtree."""

    def test_returns_flat_list_from_session(self):
        from sapwebguimcp.backend.desktop._element_finder import _dump_flat_tree

        child = _make_elem(
            type_as_number=30,
            name="CHILD",
            text="Child",
            elem_id="wnd[0]/usr/sub/lblCHILD",
        )
        parent = _make_elem(
            type_as_number=30,
            name="PARENT",
            text="Parent",
            elem_id="wnd[0]/usr/lblPARENT",
            children=[child],
        )
        session = _make_session_with_tree([parent])

        flat = _dump_flat_tree(session)

        # Both parent and child should appear in the flat list
        assert len(flat) == 2
        assert flat[0].name == "PARENT"
        assert flat[1].name == "CHILD"

    def test_uses_given_wnd_id(self):
        from sapwebguimcp.backend.desktop._element_finder import _dump_flat_tree

        # Build a session whose wnd[1]/usr returns a single element
        session = MagicMock()
        usr1 = MagicMock()
        elem = _make_elem(
            type_as_number=30,
            name="POPUPLBL",
            text="PopupLabel",
            elem_id="wnd[1]/usr/lblPOPUPLBL",
        )
        usr1.dump_tree.return_value = [elem]

        def find_by_id(element_id, raise_error=True):
            if element_id == "wnd[1]/usr":
                return usr1
            if not raise_error:
                return None
            raise Exception(f"Element not found: {element_id}")

        session.find_by_id = find_by_id

        flat = _dump_flat_tree(session, wnd_id="wnd[1]")
        assert len(flat) == 1
        assert flat[0].name == "POPUPLBL"
