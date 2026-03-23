"""Tests for GuiFrameWindow, GuiMainWindow, GuiModalWindow, GuiMessageWindow — issue #518."""

from sapsucker.components.window import (
    GuiFrameWindow,
    GuiMainWindow,
    GuiMessageWindow,
    GuiModalWindow,
)
from unittests.sapgui.conftest import make_mock_com


def _make_frame(**kwargs):
    com = make_mock_com(type_as_number=20, type_name="GuiFrameWindow", **kwargs)
    return GuiFrameWindow(com)


def _make_main(**kwargs):
    com = make_mock_com(type_as_number=21, type_name="GuiMainWindow", **kwargs)
    return GuiMainWindow(com)


def _make_message(**kwargs):
    com = make_mock_com(type_as_number=23, type_name="GuiMessageWindow", **kwargs)
    return GuiMessageWindow(com)


class TestGuiFrameWindow:
    def test_handle(self):
        wnd = _make_frame(Handle=12345)
        assert wnd.handle == 12345

    def test_iconic(self):
        wnd = _make_frame(Iconic=False)
        assert wnd.iconic is False

    def test_working_pane_height(self):
        wnd = _make_frame(WorkingPaneHeight=600)
        assert wnd.working_pane_height == 600

    def test_working_pane_width(self):
        wnd = _make_frame(WorkingPaneWidth=800)
        assert wnd.working_pane_width == 800

    def test_element_visualization_mode(self):
        wnd = _make_frame(ElementVisualizationMode=False)
        assert wnd.element_visualization_mode is False

    def test_send_v_key(self):
        wnd = _make_frame()
        wnd.send_v_key(0)
        wnd._com.SendVKey.assert_called_once_with(0)

    def test_is_v_key_allowed(self):
        wnd = _make_frame()
        wnd._com.IsVKeyAllowed.return_value = True
        assert wnd.is_v_key_allowed(8) is True
        wnd._com.IsVKeyAllowed.assert_called_once_with(8)

    def test_close(self):
        wnd = _make_frame()
        wnd.close()
        wnd._com.Close.assert_called_once()

    def test_iconify(self):
        wnd = _make_frame()
        wnd.iconify()
        wnd._com.Iconify.assert_called_once()

    def test_maximize(self):
        wnd = _make_frame()
        wnd.maximize()
        wnd._com.Maximize.assert_called_once()

    def test_restore(self):
        wnd = _make_frame()
        wnd.restore()
        wnd._com.Restore.assert_called_once()

    def test_hard_copy(self):
        wnd = _make_frame()
        wnd.hard_copy("screenshot.bmp", 0)
        wnd._com.HardCopy.assert_called_once_with("screenshot.bmp", 0)

    def test_tab_forward(self):
        wnd = _make_frame()
        wnd.tab_forward()
        wnd._com.TabForward.assert_called_once()

    def test_tab_backward(self):
        wnd = _make_frame()
        wnd.tab_backward()
        wnd._com.TabBackward.assert_called_once()

    def test_jump_forward(self):
        wnd = _make_frame()
        wnd.jump_forward()
        wnd._com.JumpForward.assert_called_once()

    def test_jump_backward(self):
        wnd = _make_frame()
        wnd.jump_backward()
        wnd._com.JumpBackward.assert_called_once()


class TestGuiMainWindow:
    def test_inherits_from_frame(self):
        wnd = _make_main()
        assert isinstance(wnd, GuiFrameWindow)

    def test_buttonbar_visible_get(self):
        wnd = _make_main(ButtonbarVisible=True)
        assert wnd.buttonbar_visible is True

    def test_buttonbar_visible_set(self):
        wnd = _make_main()
        wnd.buttonbar_visible = False
        assert wnd._com.ButtonbarVisible is False

    def test_toolbar_visible_get(self):
        wnd = _make_main(ToolbarVisible=True)
        assert wnd.toolbar_visible is True

    def test_statusbar_visible_get(self):
        wnd = _make_main(StatusbarVisible=True)
        assert wnd.statusbar_visible is True

    def test_titlebar_visible_get(self):
        wnd = _make_main(TitlebarVisible=True)
        assert wnd.titlebar_visible is True

    def test_resize_working_pane(self):
        wnd = _make_main()
        wnd.resize_working_pane(800, 600)
        wnd._com.ResizeWorkingPane.assert_called_once_with(800, 600, True)


class TestGuiModalWindow:
    def test_inherits_from_frame(self):
        com = make_mock_com(type_as_number=22, type_name="GuiModalWindow")
        wnd = GuiModalWindow(com)
        assert isinstance(wnd, GuiFrameWindow)


class TestGuiMessageWindow:
    def test_message_text(self):
        msg = _make_message(MessageText="Error occurred")
        assert msg.message_text == "Error occurred"

    def test_message_type(self):
        msg = _make_message(MessageType="E")
        assert msg.message_type == "E"

    def test_ok_button_text(self):
        msg = _make_message(OKButtonText="OK")
        assert msg.ok_button_text == "OK"

    def test_help_button_text(self):
        msg = _make_message(HelpButtonText="Help")
        assert msg.help_button_text == "Help"

    def test_focused_button(self):
        msg = _make_message(FocusedButton="btn[0]")
        assert msg.focused_button == "btn[0]"

    def test_visible(self):
        msg = _make_message(Visible=True)
        assert msg.visible is True
