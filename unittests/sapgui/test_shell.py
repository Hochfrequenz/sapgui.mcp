"""Tests for GuiShell, GuiToolbarControl, GuiHTMLViewer — issue #519."""

from unittest.mock import MagicMock

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


def _make_shell(**kwargs):
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = kwargs.pop("SubType", "Shell")
    for k, v in kwargs.items():
        setattr(com, k, v)
    return GuiShell(com)


def _make_toolbar(**kwargs):
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "ToolbarControl"
    for k, v in kwargs.items():
        setattr(com, k, v)
    return GuiToolbarControl(com)


def _make_html(**kwargs):
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "HTMLViewer"
    for k, v in kwargs.items():
        setattr(com, k, v)
    return GuiHTMLViewer(com)


class TestGuiShell:
    def test_sub_type(self):
        sh = _make_shell(SubType="GridView")
        assert sh.sub_type == "GridView"

    def test_handle(self):
        sh = _make_shell(Handle=9999)
        assert sh.handle == 9999

    def test_acc_description(self):
        sh = _make_shell(AccDescription="ALV Grid")
        assert sh.acc_description == "ALV Grid"

    def test_drag_drop_supported(self):
        sh = _make_shell(DragDropSupported=False)
        assert sh.drag_drop_supported is False

    def test_select_context_menu_item(self):
        sh = _make_shell()
        sh.select_context_menu_item("COPY")
        sh._com.SelectContextMenuItem.assert_called_once_with("COPY")

    def test_select_context_menu_item_by_position(self):
        sh = _make_shell()
        sh.select_context_menu_item_by_position("1|2")
        sh._com.SelectContextMenuItemByPosition.assert_called_once_with("1|2")

    def test_select_context_menu_item_by_text(self):
        sh = _make_shell()
        sh.select_context_menu_item_by_text("Copy")
        sh._com.SelectContextMenuItemByText.assert_called_once_with("Copy")


class TestGuiToolbarControl:
    def test_inherits_from_shell(self):
        tb = _make_toolbar()
        assert isinstance(tb, GuiShell)

    def test_button_count(self):
        tb = _make_toolbar(ButtonCount=5)
        assert tb.button_count == 5

    def test_focused_button(self):
        tb = _make_toolbar(FocusedButton=2)
        assert tb.focused_button == 2

    def test_get_button_id(self):
        tb = _make_toolbar()
        tb._com.GetButtonId.return_value = "BTN_SAVE"
        assert tb.get_button_id(0) == "BTN_SAVE"

    def test_get_button_text(self):
        tb = _make_toolbar()
        tb._com.GetButtonText.return_value = "Save"
        assert tb.get_button_text(0) == "Save"

    def test_get_button_tooltip(self):
        tb = _make_toolbar()
        tb._com.GetButtonTooltip.return_value = "Save document"
        assert tb.get_button_tooltip(0) == "Save document"

    def test_get_button_type(self):
        tb = _make_toolbar()
        tb._com.GetButtonType.return_value = 0
        assert tb.get_button_type(0) == 0

    def test_get_button_enabled(self):
        tb = _make_toolbar()
        tb._com.GetButtonEnabled.return_value = True
        assert tb.get_button_enabled(0) is True

    def test_get_button_checked(self):
        tb = _make_toolbar()
        tb._com.GetButtonChecked.return_value = False
        assert tb.get_button_checked(0) is False

    def test_get_button_icon(self):
        tb = _make_toolbar()
        tb._com.GetButtonIcon.return_value = "@01@"
        assert tb.get_button_icon(0) == "@01@"

    def test_press_button(self):
        tb = _make_toolbar()
        tb.press_button("BTN_SAVE")
        tb._com.PressButton.assert_called_once_with("BTN_SAVE")

    def test_press_context_button(self):
        tb = _make_toolbar()
        tb.press_context_button("BTN_MENU")
        tb._com.PressContextButton.assert_called_once_with("BTN_MENU")

    def test_select_menu_item(self):
        tb = _make_toolbar()
        tb.select_menu_item("FUNC_CODE")
        tb._com.SelectMenuItem.assert_called_once_with("FUNC_CODE")

    def test_select_menu_item_by_text(self):
        tb = _make_toolbar()
        tb.select_menu_item_by_text("Export")
        tb._com.SelectMenuItemByText.assert_called_once_with("Export")


class TestGuiHTMLViewer:
    def test_inherits_from_shell(self):
        html = _make_html()
        assert isinstance(html, GuiShell)

    def test_browser_handle(self):
        html = _make_html(BrowserHandle=12345)
        assert html.browser_handle == 12345

    def test_document_complete(self):
        html = _make_html(DocumentComplete=True)
        assert html.document_complete is True

    def test_sap_event(self):
        html = _make_html()
        html.sap_event("frame", "data", "url")
        html._com.SapEvent.assert_called_once_with("frame", "data", "url")

    def test_get_browser_control_type(self):
        html = _make_html()
        html._com.BrowserControlType = 1
        assert html.get_browser_control_type() == 1


class TestGuiColorSelector:
    def test_change_selection(self):
        com = MagicMock()
        com.TypeAsNumber = 122
        com.SubType = "ColorSelector"
        cs = GuiColorSelector(com)
        cs.change_selection(3)
        com.ChangeSelection.assert_called_once_with(3)


class TestShellSubclassInheritance:
    """Verify empty subclasses inherit from GuiShell."""

    def test_picture(self):
        assert issubclass(GuiPicture, GuiShell)

    def test_calendar(self):
        assert issubclass(GuiCalendar, GuiShell)

    def test_combobox_control(self):
        assert issubclass(GuiComboBoxControl, GuiShell)

    def test_input_field_control(self):
        assert issubclass(GuiInputFieldControl, GuiShell)

    def test_split(self):
        assert issubclass(GuiSplit, GuiShell)
