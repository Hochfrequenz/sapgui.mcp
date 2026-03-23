"""Tests for GuiContextMenu — issue #477."""

from unittest.mock import MagicMock

from sapsucker.components.toolbar import GuiContextMenu, GuiMenu


def _make_context_menu():
    com = MagicMock()
    com.TypeAsNumber = 127
    return GuiContextMenu(com)


class TestGuiContextMenu:
    def test_inherits_from_gui_menu(self):
        menu = _make_context_menu()
        assert isinstance(menu, GuiMenu)

    def test_select_inherited(self):
        menu = _make_context_menu()
        menu.select()
        menu._com.Select.assert_called_once()
