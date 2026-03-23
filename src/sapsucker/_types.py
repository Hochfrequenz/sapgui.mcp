"""SAP GUI component type enum and prefix mappings."""

# pylint: disable=invalid-name

from enum import IntEnum


class GuiComponentType(IntEnum):
    """Integer enum mapping SAP GUI component type numbers to names."""

    # Abstract
    GuiComponent = 0
    GuiVComponent = 1
    GuiVContainer = 2
    GuiFrameWindow = 20
    GuiContainer = 70

    # Top-level
    GuiApplication = 10
    GuiConnection = 11
    GuiSession = 12

    # Windows
    GuiMainWindow = 21
    GuiModalWindow = 22
    GuiMessageWindow = 23

    # Fields
    GuiLabel = 30
    GuiTextField = 31
    GuiCTextField = 32
    GuiPasswordField = 33
    GuiComboBox = 34
    GuiOkCodeField = 35

    # Buttons
    GuiButton = 40
    GuiRadioButton = 41
    GuiCheckBox = 42
    GuiStatusPane = 43

    # Containers
    GuiCustomControl = 50
    GuiContainerShell = 51
    GuiBox = 62
    GuiSimpleContainer = 71
    GuiScrollContainer = 72
    GuiUserArea = 74
    GuiSplitterContainer = 75

    # Table
    GuiTableControl = 80
    GuiTabStrip = 90
    GuiTab = 91

    # Misc
    GuiScrollbar = 100
    GuiToolbar = 101
    GuiTitlebar = 102
    GuiStatusbar = 103
    GuiMenu = 110
    GuiMenubar = 111

    # Collections
    GuiCollection = 120
    GuiSessionInfo = 121
    GuiShell = 122
    GuiGOSShell = 123
    GuiDialogShell = 125
    GuiDockShell = 126
    GuiContextMenu = 127
    GuiComponentCollection = 128
    GuiVHViewSwitch = 129


PREFIX_TO_TYPE_NAME: dict[str, str] = {
    "txt": "GuiTextField",
    "ctxt": "GuiCTextField",
    "pwd": "GuiPasswordField",
    "lbl": "GuiLabel",
    "btn": "GuiButton",
    "chk": "GuiCheckBox",
    "rad": "GuiRadioButton",
    "cmb": "GuiComboBox",
    "okcd": "GuiOkCodeField",
    "box": "GuiBox",
    "pane": "GuiStatusPane",
    "wnd": "GuiFrameWindow",
    "usr": "GuiUserArea",
    "sub": "GuiSimpleContainer",
    "ssub": "GuiScrollContainer",
    "cntl": "GuiCustomControl",
    "shellcont": "GuiContainerShell",
    "tbar": "GuiToolbar",
    "titl": "GuiTitlebar",
    "sbar": "GuiStatusbar",
    "menu": "GuiMenu",
    "mbar": "GuiMenubar",
    "tabs": "GuiTabStrip",
    "tabp": "GuiTab",
    "tbl": "GuiTableControl",
    "shell": "GuiShell",
}

SHELL_SUBTYPE_NAMES: dict[str, str] = {
    "GridView": "GuiGridView",
    "Tree": "GuiTree",
    "TextEdit": "GuiTextedit",
    "AbapEditor": "GuiAbapEditor",
    "HTMLViewer": "GuiHTMLViewer",
    "ToolbarControl": "GuiToolbarControl",
    "Picture": "GuiPicture",
    "Calendar": "GuiCalendar",
    "ColorSelector": "GuiColorSelector",
    "ComboBoxControl": "GuiComboBoxControl",
    "InputFieldControl": "GuiInputFieldControl",
    "Splitter": "GuiSplit",
}
