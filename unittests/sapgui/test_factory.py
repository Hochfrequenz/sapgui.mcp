"""Tests for the two-level type dispatch factory."""

from __future__ import annotations

import pytest

from sapwebguimcp.sapgui._factory import (
    _SHELL_SUBTYPE_MAP,
    _TYPE_MAP,
    wrap_com_object,
)
from sapwebguimcp.sapgui.components.base import GuiComponent
from sapwebguimcp.sapgui.components.button import GuiButton
from sapwebguimcp.sapgui.components.field import GuiTextField
from sapwebguimcp.sapgui.components.grid import GuiGridView
from sapwebguimcp.sapgui.components.shell import GuiShell
from sapwebguimcp.sapgui.components.tree import GuiTree
from sapwebguimcp.sapgui.components.window import GuiMainWindow
from unittests.sapgui.conftest import make_mock_com


class TestWrapComObject:
    """Test wrap_com_object dispatches to the correct class."""

    def test_main_window(self):
        com = make_mock_com(type_as_number=21, type_name="GuiMainWindow")
        result = wrap_com_object(com)
        assert isinstance(result, GuiMainWindow)

    def test_text_field(self):
        com = make_mock_com(type_as_number=31, type_name="GuiTextField")
        result = wrap_com_object(com)
        assert isinstance(result, GuiTextField)

    def test_button(self):
        com = make_mock_com(type_as_number=40, type_name="GuiButton")
        result = wrap_com_object(com)
        assert isinstance(result, GuiButton)

    def test_unknown_type_falls_back_to_gui_component(self):
        com = make_mock_com(type_as_number=9999, type_name="GuiUnknown")
        result = wrap_com_object(com)
        assert type(result) is GuiComponent

    def test_shell_gridview_dispatch(self):
        com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="GridView")
        result = wrap_com_object(com)
        assert isinstance(result, GuiGridView)

    def test_shell_tree_dispatch(self):
        com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="Tree")
        result = wrap_com_object(com)
        assert isinstance(result, GuiTree)

    def test_shell_unknown_subtype_falls_back_to_gui_shell(self):
        com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="UnknownControl")
        result = wrap_com_object(com)
        assert type(result) is GuiShell

    def test_shell_missing_subtype_falls_back_to_gui_shell(self):
        com = make_mock_com(type_as_number=122, type_name="GuiShell")
        # MagicMock will auto-create SubType, so delete it to test getattr fallback
        del com.SubType
        result = wrap_com_object(com)
        assert type(result) is GuiShell


class TestTypeMapCompleteness:
    """Verify all _TYPE_MAP entries produce valid instances."""

    @pytest.mark.parametrize("type_num,cls", list(_TYPE_MAP.items()), ids=[str(k) for k in _TYPE_MAP])
    def test_type_map_entry(self, type_num, cls):
        com = make_mock_com(type_as_number=type_num, type_name=cls.__name__)
        # For shell types (122), add SubType so it doesn't accidentally sub-dispatch
        if type_num != 122:
            result = wrap_com_object(com)
            assert isinstance(result, cls)

    def test_shell_base_with_no_matching_subtype(self):
        com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType="__nonexistent__")
        result = wrap_com_object(com)
        assert type(result) is GuiShell


class TestShellSubtypeMapCompleteness:
    """Verify all _SHELL_SUBTYPE_MAP entries produce valid instances."""

    @pytest.mark.parametrize(
        "sub_type,cls",
        list(_SHELL_SUBTYPE_MAP.items()),
        ids=list(_SHELL_SUBTYPE_MAP.keys()),
    )
    def test_shell_subtype_entry(self, sub_type, cls):
        com = make_mock_com(type_as_number=122, type_name="GuiShell", SubType=sub_type)
        result = wrap_com_object(com)
        assert isinstance(result, cls)
