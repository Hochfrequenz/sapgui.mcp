"""Tests for GuiCheckBox and GuiRadioButton — issue #513."""

from unittest.mock import MagicMock

from sapwebguimcp.sapgui.components.checkbox import GuiCheckBox, GuiRadioButton
from unittests.sapgui.conftest import make_mock_com


def _make_checkbox(**kwargs):
    com = make_mock_com(type_as_number=42, type_name="GuiCheckBox", **kwargs)
    return GuiCheckBox(com)


def _make_radio(**kwargs):
    com = make_mock_com(type_as_number=41, type_name="GuiRadioButton", **kwargs)
    return GuiRadioButton(com)


class TestGuiCheckBox:
    def test_selected_getter_true(self):
        chk = _make_checkbox(Selected=1)
        assert chk.selected is True

    def test_selected_getter_false(self):
        chk = _make_checkbox(Selected=0)
        assert chk.selected is False

    def test_selected_setter_true(self):
        chk = _make_checkbox()
        chk.selected = True
        assert chk._com.Selected == 1

    def test_selected_setter_false(self):
        chk = _make_checkbox()
        chk.selected = False
        assert chk._com.Selected == 0

    def test_highlighted(self):
        chk = _make_checkbox(Highlighted=True)
        assert chk.highlighted is True

    def test_is_list_element(self):
        chk = _make_checkbox(IsListElement=False)
        assert chk.is_list_element is False

    def test_color_index(self):
        chk = _make_checkbox(ColorIndex=3)
        assert chk.color_index == 3

    def test_color_intensified(self):
        chk = _make_checkbox(ColorIntensified=True)
        assert chk.color_intensified is True

    def test_color_inverse(self):
        chk = _make_checkbox(ColorInverse=False)
        assert chk.color_inverse is False


class TestGuiRadioButton:
    def test_selected_getter(self):
        rb = _make_radio(Selected=1)
        assert rb.selected is True

    def test_selected_setter(self):
        rb = _make_radio()
        rb.selected = True
        assert rb._com.Selected == 1

    def test_highlighted(self):
        rb = _make_radio(Highlighted=False)
        assert rb.highlighted is False

    def test_is_list_element(self):
        rb = _make_radio(IsListElement=True)
        assert rb.is_list_element is True

    def test_group_count(self):
        rb = _make_radio(GroupCount=4)
        assert rb.group_count == 4

    def test_group_pos(self):
        rb = _make_radio(GroupPos=2)
        assert rb.group_pos == 2
