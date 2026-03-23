"""Tests for GuiTextField, GuiCTextField, GuiPasswordField, GuiLabel, GuiBox — issue #514."""

from sapwebguimcp.sapgui.components.field import (
    GuiBox,
    GuiCTextField,
    GuiLabel,
    GuiPasswordField,
    GuiTextField,
)
from unittests.sapgui.conftest import make_mock_com


def _make_field(**kwargs):
    com = make_mock_com(type_as_number=31, type_name="GuiTextField", **kwargs)
    return GuiTextField(com)


def _make_label(**kwargs):
    com = make_mock_com(type_as_number=30, type_name="GuiLabel", **kwargs)
    return GuiLabel(com)


class TestGuiTextField:
    def test_caret_position_get(self):
        f = _make_field(CaretPosition=5)
        assert f.caret_position == 5

    def test_caret_position_set(self):
        f = _make_field()
        f.caret_position = 10
        assert f._com.CaretPosition == 10

    def test_max_length(self):
        f = _make_field(MaxLength=40)
        assert f.max_length == 40

    def test_is_required(self):
        f = _make_field(Required=True)
        assert f.is_required is True

    def test_is_numerical(self):
        f = _make_field(Numerical=False)
        assert f.is_numerical is False

    def test_is_hotspot(self):
        f = _make_field(IsHotspot=True)
        assert f.is_hotspot is True

    def test_highlighted(self):
        f = _make_field(Highlighted=False)
        assert f.highlighted is False

    def test_is_list_element(self):
        f = _make_field(IsListElement=False)
        assert f.is_list_element is False


class TestGuiCTextField:
    def test_inherits_from_gui_text_field(self):
        com = make_mock_com(type_as_number=32, type_name="GuiCTextField")
        ctf = GuiCTextField(com)
        assert isinstance(ctf, GuiTextField)


class TestGuiPasswordField:
    def test_inherits_from_gui_text_field(self):
        com = make_mock_com(type_as_number=33, type_name="GuiPasswordField")
        pf = GuiPasswordField(com)
        assert isinstance(pf, GuiTextField)


class TestGuiLabel:
    def test_displayed_text(self):
        lbl = _make_label(DisplayedText="Hello")
        assert lbl.displayed_text == "Hello"

    def test_max_length(self):
        lbl = _make_label(MaxLength=20)
        assert lbl.max_length == 20

    def test_is_numerical(self):
        lbl = _make_label(Numerical=True)
        assert lbl.is_numerical is True

    def test_is_hotspot(self):
        lbl = _make_label(IsHotspot=False)
        assert lbl.is_hotspot is False

    def test_is_left_label(self):
        lbl = _make_label(IsLeftLabel=True)
        assert lbl.is_left_label is True

    def test_is_right_label(self):
        lbl = _make_label(IsRightLabel=False)
        assert lbl.is_right_label is False

    def test_highlighted(self):
        lbl = _make_label(Highlighted=True)
        assert lbl.highlighted is True

    def test_is_list_element(self):
        lbl = _make_label(IsListElement=False)
        assert lbl.is_list_element is False

    def test_color_index(self):
        lbl = _make_label(ColorIndex=2)
        assert lbl.color_index == 2

    def test_color_intensified(self):
        lbl = _make_label(ColorIntensified=True)
        assert lbl.color_intensified is True

    def test_color_inverse(self):
        lbl = _make_label(ColorInverse=False)
        assert lbl.color_inverse is False

    def test_char_height(self):
        lbl = _make_label(CharHeight=1)
        assert lbl.char_height == 1

    def test_char_width(self):
        lbl = _make_label(CharWidth=10)
        assert lbl.char_width == 10

    def test_char_left(self):
        lbl = _make_label(CharLeft=5)
        assert lbl.char_left == 5

    def test_char_top(self):
        lbl = _make_label(CharTop=3)
        assert lbl.char_top == 3

    def test_row_text(self):
        lbl = _make_label(RowText="full row")
        assert lbl.row_text == "full row"

    def test_caret_position_get(self):
        lbl = _make_label(CaretPosition=0)
        assert lbl.caret_position == 0

    def test_caret_position_set(self):
        lbl = _make_label()
        lbl.caret_position = 5
        assert lbl._com.CaretPosition == 5


class TestGuiBox:
    def test_inherits_from_gui_v_component(self):
        from sapwebguimcp.sapgui.components.base import GuiVComponent

        com = make_mock_com(type_as_number=62, type_name="GuiBox")
        box = GuiBox(com)
        assert isinstance(box, GuiVComponent)
