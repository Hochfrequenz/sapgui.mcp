"""Tests for base component classes."""

from unittest.mock import MagicMock

import pytest

from sapwebguimcp.sapgui._errors import ElementNotFoundError
from sapwebguimcp.sapgui.components.base import GuiComponent, GuiContainer, GuiVComponent, GuiVContainer
from unittests.sapgui.conftest import make_mock_com

# ---------------------------------------------------------------------------
# GuiComponent
# ---------------------------------------------------------------------------


class TestGuiComponent:
    def test_com_property(self, mock_com):
        comp = GuiComponent(mock_com)
        assert comp.com is mock_com

    def test_id_property(self, mock_com):
        mock_com.Id = "/app/con[0]/ses[0]"
        comp = GuiComponent(mock_com)
        assert comp.id == "/app/con[0]/ses[0]"

    def test_name_property(self, mock_com):
        mock_com.Name = "btnOK"
        comp = GuiComponent(mock_com)
        assert comp.name == "btnOK"

    def test_type_property(self, mock_com):
        mock_com.Type = "GuiButton"
        comp = GuiComponent(mock_com)
        assert comp.type == "GuiButton"

    def test_type_as_number_property(self, mock_com):
        mock_com.TypeAsNumber = 40
        comp = GuiComponent(mock_com)
        assert comp.type_as_number == 40

    def test_container_type_property(self, mock_com):
        mock_com.ContainerType = True
        comp = GuiComponent(mock_com)
        assert comp.container_type is True

    def test_parent_property(self, mock_com):
        parent_mock = MagicMock()
        mock_com.Parent = parent_mock
        comp = GuiComponent(mock_com)
        assert comp.parent is parent_mock

    def test_repr(self, mock_com):
        mock_com.Type = "GuiTextField"
        mock_com.Id = "/app/con[0]/ses[0]/wnd[0]/usr/txtFIELD"
        comp = GuiComponent(mock_com)
        r = repr(comp)
        assert "GuiComponent" in r
        assert "GuiTextField" in r
        assert "txtFIELD" in r


# ---------------------------------------------------------------------------
# GuiVComponent
# ---------------------------------------------------------------------------


class TestGuiVComponent:
    def test_text_read(self):
        com = make_mock_com(text="hello")
        vc = GuiVComponent(com)
        assert vc.text == "hello"

    def test_text_write(self):
        com = make_mock_com(text="old")
        vc = GuiVComponent(com)
        vc.text = "new"
        assert com.Text == "new"

    def test_tooltip(self):
        com = make_mock_com(tooltip="tip")
        vc = GuiVComponent(com)
        assert vc.tooltip == "tip"

    def test_default_tooltip(self):
        com = make_mock_com(default_tooltip="def tip")
        vc = GuiVComponent(com)
        assert vc.default_tooltip == "def tip"

    def test_changeable(self):
        com = make_mock_com(changeable=False)
        vc = GuiVComponent(com)
        assert vc.changeable is False

    def test_modified(self):
        com = make_mock_com(modified=True)
        vc = GuiVComponent(com)
        assert vc.modified is True

    def test_dimensions(self):
        com = make_mock_com(height=50, width=200, left=10, top=20, screen_left=100, screen_top=200)
        vc = GuiVComponent(com)
        assert vc.height == 50
        assert vc.width == 200
        assert vc.left == 10
        assert vc.top == 20
        assert vc.screen_left == 100
        assert vc.screen_top == 200

    def test_icon_name(self):
        com = make_mock_com(icon_name="ICON_OK")
        vc = GuiVComponent(com)
        assert vc.icon_name == "ICON_OK"

    def test_is_symbol_font(self):
        com = make_mock_com(is_symbol_font=True)
        vc = GuiVComponent(com)
        assert vc.is_symbol_font is True

    def test_acc_text(self):
        com = make_mock_com(acc_text="accessible")
        vc = GuiVComponent(com)
        assert vc.acc_text == "accessible"

    def test_acc_tooltip(self):
        com = make_mock_com(acc_tooltip="acc tip")
        vc = GuiVComponent(com)
        assert vc.acc_tooltip == "acc tip"

    def test_acc_text_on_request(self):
        com = make_mock_com(acc_text_on_request="on req")
        vc = GuiVComponent(com)
        assert vc.acc_text_on_request == "on req"

    def test_set_focus(self):
        com = make_mock_com()
        vc = GuiVComponent(com)
        vc.set_focus()
        com.SetFocus.assert_called_once()

    def test_visualize(self):
        com = make_mock_com()
        vc = GuiVComponent(com)
        vc.visualize(True)
        com.Visualize.assert_called_once_with(True)

    def test_dump_state(self):
        com = make_mock_com()
        sentinel = MagicMock()
        com.DumpState.return_value = sentinel
        vc = GuiVComponent(com)
        result = vc.dump_state("inner")
        com.DumpState.assert_called_once_with("inner")
        assert result is sentinel


# ---------------------------------------------------------------------------
# GuiContainer
# ---------------------------------------------------------------------------


class TestGuiContainer:
    def test_children_property(self):
        child1 = make_mock_com(name="child1")
        child2 = make_mock_com(name="child2")
        com = make_mock_com(container_type=True, children=[child1, child2])
        gc = GuiContainer(com)
        assert gc.children is com.Children

    def test_find_by_id_delegates(self):
        com = make_mock_com(container_type=True, children=[])
        found = MagicMock()
        com.FindById.return_value = found
        gc = GuiContainer(com)
        result = gc.find_by_id("usr/txtFIELD")
        com.FindById.assert_called_once_with("usr/txtFIELD", False)
        assert result is found

    def test_find_by_id_not_found_raises(self):
        com = make_mock_com(container_type=True, children=[])
        com.FindById.return_value = None
        gc = GuiContainer(com)
        with pytest.raises(ElementNotFoundError, match="usr/txtFIELD"):
            gc.find_by_id("usr/txtFIELD")

    def test_find_by_id_not_found_no_raise(self):
        com = make_mock_com(container_type=True, children=[])
        com.FindById.return_value = None
        gc = GuiContainer(com)
        result = gc.find_by_id("usr/txtFIELD", raise_error=False)
        assert result is None


# ---------------------------------------------------------------------------
# GuiVContainer
# ---------------------------------------------------------------------------


class TestGuiVContainer:
    def test_inherits_container_and_vcomponent(self):
        assert issubclass(GuiVContainer, GuiContainer)
        assert issubclass(GuiVContainer, GuiVComponent)

    def test_find_by_name(self):
        com = make_mock_com(container_type=True, children=[])
        sentinel = MagicMock()
        com.FindByName.return_value = sentinel
        vc = GuiVContainer(com)
        result = vc.find_by_name("FIELD", "GuiTextField")
        com.FindByName.assert_called_once_with("FIELD", "GuiTextField")
        assert result is sentinel

    def test_find_by_name_ex(self):
        com = make_mock_com(container_type=True, children=[])
        sentinel = MagicMock()
        com.FindByNameEx.return_value = sentinel
        vc = GuiVContainer(com)
        result = vc.find_by_name_ex("FIELD", 31)
        com.FindByNameEx.assert_called_once_with("FIELD", 31)
        assert result is sentinel

    def test_find_all_by_name(self):
        com = make_mock_com(container_type=True, children=[])
        sentinel = MagicMock()
        com.FindAllByName.return_value = sentinel
        vc = GuiVContainer(com)
        result = vc.find_all_by_name("FIELD", "GuiTextField")
        com.FindAllByName.assert_called_once_with("FIELD", "GuiTextField")
        assert result is sentinel

    def test_find_all_by_name_ex(self):
        com = make_mock_com(container_type=True, children=[])
        sentinel = MagicMock()
        com.FindAllByNameEx.return_value = sentinel
        vc = GuiVContainer(com)
        result = vc.find_all_by_name_ex("FIELD", 31)
        com.FindAllByNameEx.assert_called_once_with("FIELD", 31)
        assert result is sentinel
