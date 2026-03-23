"""Tests for GuiButton — issue #513."""

from sapsucker.components.button import GuiButton
from unittests.sapgui.conftest import make_mock_com


def _make_button(**kwargs):
    com = make_mock_com(type_as_number=40, type_name="GuiButton", **kwargs)
    return GuiButton(com)


class TestGuiButton:
    def test_press(self):
        btn = _make_button()
        btn.press()
        btn._com.Press.assert_called_once()

    def test_highlighted(self):
        btn = _make_button(Highlighted=True)
        assert btn.highlighted is True

    def test_highlighted_false(self):
        btn = _make_button(Highlighted=False)
        assert btn.highlighted is False

    def test_is_list_element(self):
        btn = _make_button(IsListElement=False)
        assert btn.is_list_element is False
