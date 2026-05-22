"""Unit tests for discover_fields logic using mock element trees.

These tests validate the field discovery algorithm without a live SAP connection,
using ElementInfo fixtures that represent SE18/SE19 screen structures.
"""

from sapsucker.models import ElementInfo

from sapguimcp.backend.desktop import _discover_fields_from_tree


def _make_elem(
    id: str = "",
    type: str = "",
    type_as_number: int = 0,
    name: str = "",
    text: str = "",
    changeable: bool = True,
    children: list | None = None,
) -> ElementInfo:
    """Shorthand factory for ElementInfo."""
    return ElementInfo(
        id=id,
        type=type,
        type_as_number=type_as_number,
        name=name,
        text=text,
        changeable=changeable,
        children=children or [],
    )


# -- SE18-like element tree (key elements only) --

SE18_ELEMENTS = [
    _make_elem(type="GuiRadioButton", type_as_number=41, name="G_IS_SPOT", text="Erweiterungsspot"),
    _make_elem(type="GuiCTextField", type_as_number=32, name="G_ENHSPOTNAME", text="", changeable=True),
    _make_elem(type="GuiRadioButton", type_as_number=41, name="G_IS_BADI", text="BAdI-Name"),
    _make_elem(type="GuiCTextField", type_as_number=32, name="G_BADINAME", text="", changeable=False),
    _make_elem(type="GuiButton", type_as_number=40, name="PUSHBUTTON_DISPLAY", text=" Anzeigen"),
    _make_elem(type="GuiButton", type_as_number=40, name="PUSHBUTTON_CHANGE", text=" Ändern"),
    _make_elem(type="GuiButton", type_as_number=40, name="PUSHBUTTON_CREATE", text=" Anlegen"),
]

# -- SE19-like element tree (key elements only) --

SE19_ELEMENTS = [
    # Section 1: Edit existing implementation
    _make_elem(type="GuiRadioButton", type_as_number=41, name="G_IS_NEW_1", text="Neues BAdI"),
    _make_elem(type="GuiLabel", type_as_number=30, name="G_ENHNAME", text="Erweiterungsimplementierung"),
    _make_elem(type="GuiCTextField", type_as_number=32, name="G_ENHNAME", text=""),
    _make_elem(type="GuiRadioButton", type_as_number=41, name="G_IS_CLASSIC_1", text="Klassisches BAdI"),
    _make_elem(type="GuiLabel", type_as_number=30, name="RSEXSCRN-IMP_NAME", text="Implementierung"),
    _make_elem(type="GuiCTextField", type_as_number=32, name="RSEXSCRN-IMP_NAME", text="", changeable=False),
    _make_elem(type="GuiButton", type_as_number=40, name="PUSHBUTTON_DISPLAY_TEXT", text=" Anzeigen"),
    _make_elem(type="GuiButton", type_as_number=40, name="PUSHBUTTON_CHANGE_TEXT", text=" Ändern"),
    # Section 2: Create new implementation
    _make_elem(type="GuiRadioButton", type_as_number=41, name="G_IS_NEW_2", text="Neues BAdI"),
    _make_elem(type="GuiLabel", type_as_number=30, name="G_ENHSPOTNAME", text="Erweiterungsspot"),
    _make_elem(type="GuiCTextField", type_as_number=32, name="G_ENHSPOTNAME", text=""),
    _make_elem(type="GuiRadioButton", type_as_number=41, name="G_IS_CLASSIC_2", text="Klassisches BAdI"),
    _make_elem(type="GuiLabel", type_as_number=30, name="RSEXSCRN-EXIT_NAME", text="BAdI-Name"),
    _make_elem(type="GuiCTextField", type_as_number=32, name="RSEXSCRN-EXIT_NAME", text="", changeable=False),
    _make_elem(type="GuiButton", type_as_number=40, name="PUSHBUTTON_IMPLEMENT_TEXT", text=" Impl. anlegen"),
]

# -- Toolbar-like elements (buttons with empty text should be skipped) --

TOOLBAR_ELEMENTS = [
    _make_elem(type="GuiButton", type_as_number=40, name="btn[26]", text=""),
    _make_elem(type="GuiButton", type_as_number=40, name="btn[39]", text=""),
    _make_elem(type="GuiButton", type_as_number=40, name="btn[14]", text=""),
]


class TestDiscoverFieldsFromTree:
    """Test the pure field discovery logic extracted from discover_fields()."""

    def test_se18_returns_radios_textfields_and_buttons(self):
        """SE18 tree should produce radios, text fields, and labeled buttons."""
        result = _discover_fields_from_tree(SE18_ELEMENTS)
        types = {f["type"] for f in result}

        assert "GuiRadioButton" in types
        assert "GuiCTextField" in types
        assert "GuiButton" in types

    def test_se18_radio_labels_are_populated(self):
        """Radio buttons should use their own text as label."""
        result = _discover_fields_from_tree(SE18_ELEMENTS)
        radios = [f for f in result if f["type"] == "GuiRadioButton"]

        assert len(radios) >= 2
        labels = {r["label"] for r in radios}
        assert "Erweiterungsspot" in labels
        assert "BAdI-Name" in labels

    def test_se18_text_field_labels_fall_back_to_name(self):
        """SE18 text fields have no adjacent GuiLabel — label should be elem.name."""
        result = _discover_fields_from_tree(SE18_ELEMENTS)
        text_fields = [f for f in result if f["type"] == "GuiCTextField"]

        # Without GuiLabel elements, labels fall back to element name
        names = {f["name"] for f in text_fields}
        labels = {f["label"] for f in text_fields}
        assert names == labels, "Without labels, field labels should equal element names"

    def test_se18_button_labels_are_stripped(self):
        """Pushbuttons should have stripped text as labels."""
        result = _discover_fields_from_tree(SE18_ELEMENTS)
        buttons = [f for f in result if f["type"] == "GuiButton"]

        assert len(buttons) >= 3
        button_labels = {b["label"] for b in buttons}
        assert "Anzeigen" in button_labels
        assert "Ändern" in button_labels
        assert "Anlegen" in button_labels

    def test_se19_has_four_radio_buttons(self):
        """SE19 should have at least 4 radios (2 sections x 2 options)."""
        result = _discover_fields_from_tree(SE19_ELEMENTS)
        radios = [f for f in result if f["type"] == "GuiRadioButton"]
        assert len(radios) >= 4

    def test_se19_label_map_resolves_from_guilabel(self):
        """SE19 has GuiLabel elements — text fields should get real labels."""
        result = _discover_fields_from_tree(SE19_ELEMENTS)
        text_fields = [f for f in result if f["type"] == "GuiCTextField"]

        # Fields with matching GuiLabel names should get the label text
        label_map = {f["name"]: f["label"] for f in text_fields}

        # G_ENHNAME has a GuiLabel with text "Erweiterungsimplementierung"
        assert label_map.get("G_ENHNAME") == "Erweiterungsimplementierung"
        # RSEXSCRN-IMP_NAME has GuiLabel "Implementierung"
        assert label_map.get("RSEXSCRN-IMP_NAME") == "Implementierung"

    def test_toolbar_buttons_with_empty_text_are_skipped(self):
        """Buttons with empty text (toolbar icons) should not appear in results."""
        result = _discover_fields_from_tree(TOOLBAR_ELEMENTS)
        assert len(result) == 0, f"Expected no fields from toolbar, got {result}"

    def test_empty_tree_returns_empty(self):
        """Empty element list should return empty results."""
        result = _discover_fields_from_tree([])
        assert result == []

    def test_mixed_tree_with_toolbar_noise(self):
        """Real screen has toolbar buttons mixed with real fields — only real ones returned."""
        mixed = TOOLBAR_ELEMENTS + SE18_ELEMENTS
        result = _discover_fields_from_tree(mixed)

        # Should have the same count as SE18 alone (toolbar filtered out)
        se18_only = _discover_fields_from_tree(SE18_ELEMENTS)
        assert len(result) == len(se18_only)

    def test_checkbox_included_when_present(self):
        """GuiCheckBox (type 42) should be included with its text as label."""
        elems = [
            _make_elem(type="GuiCheckBox", type_as_number=42, name="MY_CHECK", text="mehrfach verwendbar"),
        ]
        result = _discover_fields_from_tree(elems)
        assert len(result) == 1
        assert result[0]["type"] == "GuiCheckBox"
        assert result[0]["label"] == "mehrfach verwendbar"
