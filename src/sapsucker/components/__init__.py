"""SAP GUI Scripting component wrappers."""

from sapsucker.components.application import GuiApplication
from sapsucker.components.base import GuiComponent, GuiContainer, GuiVComponent, GuiVContainer
from sapsucker.components.button import GuiButton
from sapsucker.components.checkbox import GuiCheckBox, GuiRadioButton
from sapsucker.components.collection import GuiCollection, GuiComponentCollection
from sapsucker.components.combobox import GuiComboBox, GuiComboBoxEntry
from sapsucker.components.connection import GuiConnection
from sapsucker.components.container import (
    GuiContainerShell,
    GuiCustomControl,
    GuiDialogShell,
    GuiDockShell,
    GuiGOSShell,
    GuiScrollbar,
    GuiScrollContainer,
    GuiSimpleContainer,
    GuiSplitterContainer,
    GuiUserArea,
)
from sapsucker.components.editor import GuiAbapEditor, GuiTextedit
from sapsucker.components.field import GuiBox, GuiCTextField, GuiLabel, GuiPasswordField, GuiTextField
from sapsucker.components.grid import GuiGridView
from sapsucker.components.okcode import GuiOkCodeField
from sapsucker.components.session import GuiSession, GuiSessionInfo
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
from sapsucker.components.table import GuiTableColumn, GuiTableControl, GuiTableRow
from sapsucker.components.toolbar import GuiContextMenu, GuiMenu, GuiMenubar, GuiTitlebar, GuiToolbar
from sapsucker.components.tree import GuiTree
from sapsucker.components.window import GuiFrameWindow, GuiMainWindow, GuiMessageWindow, GuiModalWindow

__all__ = [
    # base
    "GuiComponent",
    "GuiVComponent",
    "GuiContainer",
    "GuiVContainer",
    # application / connection / session
    "GuiApplication",
    "GuiConnection",
    "GuiSession",
    "GuiSessionInfo",
    # window
    "GuiFrameWindow",
    "GuiMainWindow",
    "GuiModalWindow",
    "GuiMessageWindow",
    # containers
    "GuiScrollbar",
    "GuiUserArea",
    "GuiScrollContainer",
    "GuiSimpleContainer",
    "GuiCustomControl",
    "GuiContainerShell",
    "GuiDialogShell",
    "GuiDockShell",
    "GuiGOSShell",
    "GuiSplitterContainer",
    # fields
    "GuiTextField",
    "GuiCTextField",
    "GuiPasswordField",
    "GuiLabel",
    "GuiBox",
    # button / checkbox
    "GuiButton",
    "GuiCheckBox",
    "GuiRadioButton",
    # combobox
    "GuiComboBox",
    "GuiComboBoxEntry",
    # okcode
    "GuiOkCodeField",
    # collections
    "GuiComponentCollection",
    "GuiCollection",
    # shell
    "GuiShell",
    "GuiHTMLViewer",
    "GuiToolbarControl",
    "GuiPicture",
    "GuiCalendar",
    "GuiColorSelector",
    "GuiComboBoxControl",
    "GuiInputFieldControl",
    "GuiSplit",
    # editor
    "GuiTextedit",
    "GuiAbapEditor",
    # grid
    "GuiGridView",
    # statusbar
    "GuiStatusbar",
    "GuiStatusPane",
    "GuiVHViewSwitch",
    # tab
    "GuiTabStrip",
    "GuiTab",
    # table
    "GuiTableControl",
    "GuiTableRow",
    "GuiTableColumn",
    # toolbar / menu
    "GuiToolbar",
    "GuiMenubar",
    "GuiMenu",
    "GuiContextMenu",
    "GuiTitlebar",
    # tree
    "GuiTree",
]
