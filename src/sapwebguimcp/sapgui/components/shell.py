"""Shell components — GuiShell and its non-grid/tree/editor subclasses."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVContainer


class GuiShell(GuiVContainer):
    """Wraps the COM GuiShell interface (TypeAsNumber 122).

    Base class for all ActiveX/shell controls embedded in SAP GUI.
    SubType determines the concrete control kind.
    """

    @property
    def sub_type(self) -> str:
        return self._com.SubType

    @property
    def handle(self) -> int:
        return self._com.Handle

    @property
    def acc_description(self) -> str:
        return self._com.AccDescription

    @property
    def drag_drop_supported(self) -> bool:
        return bool(self._com.DragDropSupported)

    @property
    def ocx_events(self):
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
    """Wraps the COM GuiHTMLViewer shell (SubType 'HTMLViewer')."""

    @property
    def browser_handle(self) -> int:
        return self._com.BrowserHandle

    @property
    def document_complete(self) -> bool:
        return bool(self._com.DocumentComplete)

    def sap_event(self, frame: str, post_data: str, url: str) -> None:
        """Trigger a SAP event in the HTML viewer."""
        self._com.SapEvent(frame, post_data, url)

    def get_browser_control_type(self) -> int:
        """Return the browser control type."""
        return self._com.BrowserControlType


class GuiToolbarControl(GuiShell):
    """Wraps the COM GuiToolbarControl shell (SubType 'ToolbarControl')."""

    @property
    def button_count(self) -> int:
        return self._com.ButtonCount

    @property
    def focused_button(self) -> int:
        return self._com.FocusedButton

    def get_button_id(self, pos: int) -> str:
        return self._com.GetButtonId(pos)

    def get_button_text(self, pos: int) -> str:
        return self._com.GetButtonText(pos)

    def get_button_tooltip(self, pos: int) -> str:
        return self._com.GetButtonTooltip(pos)

    def get_button_type(self, pos: int) -> int:
        return self._com.GetButtonType(pos)

    def get_button_enabled(self, pos: int) -> bool:
        return bool(self._com.GetButtonEnabled(pos))

    def get_button_checked(self, pos: int) -> bool:
        return bool(self._com.GetButtonChecked(pos))

    def get_button_icon(self, pos: int) -> str:
        return self._com.GetButtonIcon(pos)

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
    """Wraps the COM GuiPicture shell (SubType 'Picture')."""


class GuiCalendar(GuiShell):
    """Wraps the COM GuiCalendar shell (SubType 'Calendar')."""


class GuiColorSelector(GuiShell):
    """Wraps the COM GuiColorSelector shell (SubType 'ColorSelector')."""

    def change_selection(self, index: int) -> None:
        """Change the selected color by index."""
        self._com.ChangeSelection(index)


class GuiComboBoxControl(GuiShell):
    """Wraps the COM GuiComboBoxControl shell (SubType 'ComboBoxControl')."""


class GuiInputFieldControl(GuiShell):
    """Wraps the COM GuiInputFieldControl shell (SubType 'InputFieldControl')."""


class GuiSplit(GuiShell):
    """Wraps the COM GuiSplit shell (SubType 'Splitter')."""
