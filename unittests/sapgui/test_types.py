"""Tests for GuiComponentType enum and prefix/subtype mappings."""

import pytest

from sapsucker._types import (
    PREFIX_TO_TYPE_NAME,
    SHELL_SUBTYPE_NAMES,
    GuiComponentType,
)


class TestGuiComponentType:
    def test_is_int_enum(self):
        assert isinstance(GuiComponentType.GuiComponent, int)

    def test_abstract_values(self):
        assert GuiComponentType.GuiComponent == 0
        assert GuiComponentType.GuiVComponent == 1
        assert GuiComponentType.GuiVContainer == 2
        assert GuiComponentType.GuiFrameWindow == 20
        assert GuiComponentType.GuiContainer == 70

    def test_top_level_values(self):
        assert GuiComponentType.GuiApplication == 10
        assert GuiComponentType.GuiConnection == 11
        assert GuiComponentType.GuiSession == 12

    def test_window_values(self):
        assert GuiComponentType.GuiMainWindow == 21
        assert GuiComponentType.GuiModalWindow == 22
        assert GuiComponentType.GuiMessageWindow == 23

    def test_field_values(self):
        assert GuiComponentType.GuiLabel == 30
        assert GuiComponentType.GuiTextField == 31
        assert GuiComponentType.GuiCTextField == 32
        assert GuiComponentType.GuiPasswordField == 33
        assert GuiComponentType.GuiComboBox == 34
        assert GuiComponentType.GuiOkCodeField == 35

    def test_button_values(self):
        assert GuiComponentType.GuiButton == 40
        assert GuiComponentType.GuiRadioButton == 41
        assert GuiComponentType.GuiCheckBox == 42
        assert GuiComponentType.GuiStatusPane == 43

    def test_container_values(self):
        assert GuiComponentType.GuiCustomControl == 50
        assert GuiComponentType.GuiContainerShell == 51
        assert GuiComponentType.GuiBox == 62
        assert GuiComponentType.GuiSimpleContainer == 71
        assert GuiComponentType.GuiScrollContainer == 72
        assert GuiComponentType.GuiUserArea == 74
        assert GuiComponentType.GuiSplitterContainer == 75

    def test_table_values(self):
        assert GuiComponentType.GuiTableControl == 80
        assert GuiComponentType.GuiTabStrip == 90
        assert GuiComponentType.GuiTab == 91

    def test_misc_values(self):
        assert GuiComponentType.GuiScrollbar == 100
        assert GuiComponentType.GuiToolbar == 101
        assert GuiComponentType.GuiTitlebar == 102
        assert GuiComponentType.GuiStatusbar == 103
        assert GuiComponentType.GuiMenu == 110
        assert GuiComponentType.GuiMenubar == 111

    def test_collection_values(self):
        assert GuiComponentType.GuiCollection == 120
        assert GuiComponentType.GuiSessionInfo == 121
        assert GuiComponentType.GuiShell == 122
        assert GuiComponentType.GuiGOSShell == 123
        assert GuiComponentType.GuiDialogShell == 125
        assert GuiComponentType.GuiDockShell == 126
        assert GuiComponentType.GuiComponentCollection == 128
        assert GuiComponentType.GuiVHViewSwitch == 129

    def test_lookup_by_value(self):
        assert GuiComponentType(31) == GuiComponentType.GuiTextField

    def test_name(self):
        assert GuiComponentType.GuiTextField.name == "GuiTextField"


class TestPrefixToTypeName:
    def test_txt_maps_to_text_field(self):
        assert PREFIX_TO_TYPE_NAME["txt"] == "GuiTextField"

    def test_ctxt_maps_to_ctext_field(self):
        assert PREFIX_TO_TYPE_NAME["ctxt"] == "GuiCTextField"

    def test_btn_maps_to_button(self):
        assert PREFIX_TO_TYPE_NAME["btn"] == "GuiButton"

    def test_shell_maps_to_gui_shell(self):
        assert PREFIX_TO_TYPE_NAME["shell"] == "GuiShell"

    def test_all_values_are_valid_enum_names(self):
        for type_name in PREFIX_TO_TYPE_NAME.values():
            assert hasattr(GuiComponentType, type_name), f"{type_name} not in enum"


class TestShellSubtypeNames:
    def test_grid_view(self):
        assert SHELL_SUBTYPE_NAMES["GridView"] == "GuiGridView"

    def test_tree(self):
        assert SHELL_SUBTYPE_NAMES["Tree"] == "GuiTree"

    def test_text_edit(self):
        assert SHELL_SUBTYPE_NAMES["TextEdit"] == "GuiTextedit"

    def test_all_keys_present(self):
        expected_keys = {
            "GridView",
            "Tree",
            "TextEdit",
            "AbapEditor",
            "HTMLViewer",
            "ToolbarControl",
            "Picture",
            "Calendar",
            "ColorSelector",
            "ComboBoxControl",
            "InputFieldControl",
            "Splitter",
        }
        assert set(SHELL_SUBTYPE_NAMES.keys()) == expected_keys
