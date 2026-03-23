"""Two-level type dispatch factory for wrapping raw COM objects."""

from __future__ import annotations

from typing import Any

from sapsucker.components.application import GuiApplication
from sapsucker.components.base import GuiComponent
from sapsucker.components.button import GuiButton
from sapsucker.components.checkbox import GuiCheckBox, GuiRadioButton
from sapsucker.components.combobox import GuiComboBox
from sapsucker.components.connection import GuiConnection
from sapsucker.components.container import (
    GuiContainerShell,
    GuiCustomControl,
    GuiDialogShell,
    GuiDockShell,
    GuiGOSShell,
    GuiScrollContainer,
    GuiSimpleContainer,
    GuiSplitterContainer,
    GuiUserArea,
)
from sapsucker.components.editor import GuiAbapEditor, GuiTextedit
from sapsucker.components.field import (
    GuiBox,
    GuiCTextField,
    GuiLabel,
    GuiPasswordField,
    GuiTextField,
)
from sapsucker.components.grid import GuiGridView
from sapsucker.components.okcode import GuiOkCodeField
from sapsucker.components.session import GuiSession
from sapsucker.components.shell import (
    GuiCalendar,
    GuiColorSelector,
    GuiComboBoxControl,
    GuiHTMLViewer,
    GuiInputFieldControl,
    GuiPicture,
    GuiShell,
    GuiSplit,
    GuiToolbarControl,
)
from sapsucker.components.statusbar import GuiStatusbar, GuiStatusPane, GuiVHViewSwitch
from sapsucker.components.tab import GuiTab, GuiTabStrip
from sapsucker.components.table import GuiTableControl
from sapsucker.components.toolbar import GuiContextMenu, GuiMenu, GuiMenubar, GuiTitlebar, GuiToolbar
from sapsucker.components.tree import GuiTree
from sapsucker.components.window import (
    GuiFrameWindow,
    GuiMainWindow,
    GuiMessageWindow,
    GuiModalWindow,
)

# Level 1: TypeAsNumber -> Python class
_TYPE_MAP: dict[int, type[GuiComponent]] = {
    10: GuiApplication,
    11: GuiConnection,
    12: GuiSession,
    20: GuiFrameWindow,
    21: GuiMainWindow,
    22: GuiModalWindow,
    23: GuiMessageWindow,
    30: GuiLabel,
    31: GuiTextField,
    32: GuiCTextField,
    33: GuiPasswordField,
    34: GuiComboBox,
    35: GuiOkCodeField,
    40: GuiButton,
    41: GuiRadioButton,
    42: GuiCheckBox,
    43: GuiStatusPane,
    50: GuiCustomControl,
    51: GuiContainerShell,
    62: GuiBox,
    71: GuiSimpleContainer,
    72: GuiScrollContainer,
    74: GuiUserArea,
    75: GuiSplitterContainer,
    80: GuiTableControl,
    90: GuiTabStrip,
    91: GuiTab,
    101: GuiToolbar,
    102: GuiTitlebar,
    103: GuiStatusbar,
    110: GuiMenu,
    111: GuiMenubar,
    122: GuiShell,
    123: GuiGOSShell,
    125: GuiDialogShell,
    126: GuiDockShell,
    127: GuiContextMenu,
    129: GuiVHViewSwitch,
}

# Level 2: GuiShell SubType -> Python class
_SHELL_SUBTYPE_MAP: dict[str, type[GuiShell]] = {
    "GridView": GuiGridView,
    "Tree": GuiTree,
    "TextEdit": GuiTextedit,
    "AbapEditor": GuiAbapEditor,
    "HTMLViewer": GuiHTMLViewer,
    "ToolbarControl": GuiToolbarControl,
    "Picture": GuiPicture,
    "Calendar": GuiCalendar,
    "ColorSelector": GuiColorSelector,
    "ComboBoxControl": GuiComboBoxControl,
    "InputFieldControl": GuiInputFieldControl,
    "Splitter": GuiSplit,
}


def wrap_com_object(com_obj: Any) -> GuiComponent:
    """Wrap a raw COM dispatch object in the appropriate Python class.

    Uses two-level dispatch:
    1. TypeAsNumber selects the base class.
    2. For GuiShell (type 122), SubType refines to the concrete shell class.
    3. Unknown types fall back to GuiComponent.
    """
    type_num = com_obj.TypeAsNumber
    cls = _TYPE_MAP.get(type_num)
    if cls is GuiShell:
        sub_type = getattr(com_obj, "SubType", "")
        cls = _SHELL_SUBTYPE_MAP.get(sub_type, GuiShell)
    elif cls is None:
        cls = GuiComponent
    return cls(com_obj)
