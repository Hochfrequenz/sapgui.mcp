"""Shell components — GuiShell and its non-grid/tree/editor subclasses."""

from __future__ import annotations

from typing import Any

from sapsucker.components.base import GuiVContainer

__all__ = [
    "GuiCalendar",
    "GuiColorSelector",
    "GuiComboBoxControl",
    "GuiHTMLViewer",
    "GuiInputFieldControl",
    "GuiPicture",
    "GuiShell",
    "GuiSplit",
    "GuiToolbarControl",
]


class GuiShell(GuiVContainer):
    """Wraps the COM GuiShell interface (TypeAsNumber 122).

    Base class for all ActiveX/shell controls embedded in SAP GUI.
    SubType determines the concrete control kind.
    """

    @property
    def sub_type(self) -> str:
        """Shell sub-type name (e.g. 'GridView', 'Tree')."""
        return str(self._com.SubType)

    @property
    def handle(self) -> int:
        """Native window handle."""
        return int(self._com.Handle)

    @property
    def acc_description(self) -> str:
        """Accessibility description."""
        return str(self._com.AccDescription)

    @property
    def drag_drop_supported(self) -> bool:
        """Whether drag-and-drop is supported."""
        return bool(self._com.DragDropSupported)

    @property
    def ocx_events(self) -> Any:
        """Return the COM OcxEvents collection."""
        return self._com.OcxEvents

    def select_context_menu_item(self, item_id: str) -> None:
        """Select a context menu item by its function code."""
        self._com.SelectContextMenuItem(item_id)

    def select_context_menu_item_by_position(self, position: str) -> None:
        """Select a context menu item by position path (e.g. '1|2')."""
        self._com.SelectContextMenuItemByPosition(position)

    def select_context_menu_item_by_text(self, text: str) -> None:
        """Select a context menu item by its display text."""
        self._com.SelectContextMenuItemByText(text)


class GuiHTMLViewer(GuiShell):
    """Embedded HTML browser control (SubType 'HTMLViewer')."""

    @property
    def browser_handle(self) -> int:
        """Native browser window handle."""
        return int(self._com.BrowserHandle)

    @property
    def document_complete(self) -> bool:
        """Whether the document has finished loading."""
        return bool(self._com.DocumentComplete)

    def sap_event(self, frame: str, post_data: str, url: str) -> None:
        """Trigger a SAP event in the HTML viewer."""
        self._com.SapEvent(frame, post_data, url)

    def get_browser_control_type(self) -> int:
        """Return the browser control type."""
        return int(self._com.BrowserControlType)


class GuiToolbarControl(GuiShell):
    """Shell-based toolbar with buttons and menus (SubType 'ToolbarControl')."""

    @property
    def button_count(self) -> int:
        """Number of buttons in the toolbar."""
        return int(self._com.ButtonCount)

    @property
    def focused_button(self) -> int:
        """Index of the currently focused button."""
        return int(self._com.FocusedButton)

    def get_button_id(self, pos: int) -> str:
        """Return the button ID at the given position."""
        return str(self._com.GetButtonId(pos))

    def get_button_text(self, pos: int) -> str:
        """Return the button text at the given position."""
        return str(self._com.GetButtonText(pos))

    def get_button_tooltip(self, pos: int) -> str:
        """Return the button tooltip at the given position."""
        return str(self._com.GetButtonTooltip(pos))

    def get_button_type(self, pos: int) -> int:
        """Return the button type at the given position."""
        return int(self._com.GetButtonType(pos))

    def get_button_enabled(self, pos: int) -> bool:
        """Whether the button at the given position is enabled."""
        return bool(self._com.GetButtonEnabled(pos))

    def get_button_checked(self, pos: int) -> bool:
        """Whether the button at the given position is checked."""
        return bool(self._com.GetButtonChecked(pos))

    def get_button_icon(self, pos: int) -> str:
        """Return the button icon name at the given position."""
        return str(self._com.GetButtonIcon(pos))

    def press_button(self, button_id: str) -> None:
        """Press a toolbar button by its ID."""
        self._com.PressButton(button_id)

    def press_context_button(self, button_id: str) -> None:
        """Press a toolbar context button (opens dropdown menu)."""
        self._com.PressContextButton(button_id)

    def select_menu_item(self, item_id: str) -> None:
        """Select a menu item by function code."""
        self._com.SelectMenuItem(item_id)

    def select_menu_item_by_text(self, text: str) -> None:
        """Select a menu item by display text."""
        self._com.SelectMenuItemByText(text)


class GuiPicture(GuiShell):
    """Image display control (SubType 'Picture')."""


class GuiCalendar(GuiShell):
    """Calendar date picker control (SubType 'Calendar')."""


class GuiColorSelector(GuiShell):
    """Color selection control (SubType 'ColorSelector')."""

    def change_selection(self, index: int) -> None:
        """Change the selected color by index."""
        self._com.ChangeSelection(index)


class GuiComboBoxControl(GuiShell):
    """Shell-based combobox control (SubType 'ComboBoxControl')."""


class GuiInputFieldControl(GuiShell):
    """Shell-based input field control (SubType 'InputFieldControl')."""


class GuiSplit(GuiShell):
    """Splitter shell that divides a shell area into panes (SubType 'Splitter')."""
