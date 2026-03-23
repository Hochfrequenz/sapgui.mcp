"""Window components — GuiFrameWindow, GuiMainWindow, GuiModalWindow, GuiMessageWindow."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from sapsucker.components.base import GuiVComponent, GuiVContainer

__all__ = ["GuiFrameWindow", "GuiMainWindow", "GuiMessageWindow", "GuiModalWindow"]


class GuiFrameWindow(GuiVContainer):
    """Wraps the COM GuiFrameWindow interface (TypeAsNumber 20).

    Base class for main and modal windows.
    """

    @property
    def handle(self) -> int:
        """Native window handle."""
        return int(self._com.Handle)

    @property
    def iconic(self) -> bool:
        """Whether the window is minimized."""
        return bool(self._com.Iconic)

    @property
    def gui_focus(self) -> GuiVComponent:
        """Return the element that currently has GUI focus."""
        from sapsucker._factory import wrap_com_object

        return wrap_com_object(self._com.GuiFocus)  # type: ignore[return-value]

    @property
    def system_focus(self) -> GuiVComponent:
        """Return the element that currently has system focus."""
        from sapsucker._factory import wrap_com_object

        return wrap_com_object(self._com.SystemFocus)  # type: ignore[return-value]

    @property
    def working_pane_height(self) -> int:
        """Height of the working pane area in pixels."""
        return int(self._com.WorkingPaneHeight)

    @property
    def working_pane_width(self) -> int:
        """Width of the working pane area in pixels."""
        return int(self._com.WorkingPaneWidth)

    @property
    def element_visualization_mode(self) -> bool:
        """Whether element visualization mode is active."""
        return bool(self._com.ElementVisualizationMode)

    def close(self) -> None:
        """Close this window."""
        self._com.Close()

    def iconify(self) -> None:
        """Minimize this window."""
        self._com.Iconify()

    def maximize(self) -> None:
        """Maximize this window."""
        self._com.Maximize()

    def restore(self) -> None:
        """Restore this window from minimized/maximized state."""
        self._com.Restore()

    def send_v_key(self, v_key: int) -> None:
        """Press a virtual key (e.g. 0=Enter, 2=F2, 8=F8)."""
        self._com.SendVKey(v_key)

    def is_v_key_allowed(self, v_key: int) -> bool:
        """Check whether a virtual key is currently available."""
        return bool(self._com.IsVKeyAllowed(v_key))

    def hard_copy(self, filename: str, image_type: int) -> None:
        """Save a screenshot of this window."""
        self._com.HardCopy(filename, image_type)

    def tab_forward(self) -> None:
        """Move focus to the next tab stop."""
        self._com.TabForward()

    def tab_backward(self) -> None:
        """Move focus to the previous tab stop."""
        self._com.TabBackward()

    def jump_forward(self) -> None:
        """Jump forward in the focus chain."""
        self._com.JumpForward()

    def jump_backward(self) -> None:
        """Jump backward in the focus chain."""
        self._com.JumpBackward()


class GuiMainWindow(GuiFrameWindow):
    """Wraps the COM GuiMainWindow interface (TypeAsNumber 21).

    The primary application window with toolbar and statusbar.
    """

    @property
    def buttonbar_visible(self) -> bool:
        """Whether the button bar is visible."""
        return bool(self._com.ButtonbarVisible)

    @buttonbar_visible.setter
    def buttonbar_visible(self, value: bool) -> None:
        self._com.ButtonbarVisible = value

    @property
    def toolbar_visible(self) -> bool:
        """Whether the toolbar is visible."""
        return bool(self._com.ToolbarVisible)

    @toolbar_visible.setter
    def toolbar_visible(self, value: bool) -> None:
        self._com.ToolbarVisible = value

    @property
    def statusbar_visible(self) -> bool:
        """Whether the status bar is visible."""
        return bool(self._com.StatusbarVisible)

    @statusbar_visible.setter
    def statusbar_visible(self, value: bool) -> None:
        self._com.StatusbarVisible = value

    @property
    def titlebar_visible(self) -> bool:
        """Whether the title bar is visible."""
        return bool(self._com.TitlebarVisible)

    @titlebar_visible.setter
    def titlebar_visible(self, value: bool) -> None:
        self._com.TitlebarVisible = value

    def resize_working_pane(self, width: int, height: int, throw_on_fail: bool = True) -> None:
        """Resize the working pane area."""
        self._com.ResizeWorkingPane(width, height, throw_on_fail)

    def resize_working_pane_ex(self, width: int, height: int, throw_on_fail: bool = True) -> None:
        """Resize the working pane area (extended version)."""
        self._com.ResizeWorkingPaneEx(width, height, throw_on_fail)


class GuiModalWindow(GuiFrameWindow):
    """Wraps the COM GuiModalWindow interface (TypeAsNumber 22).

    A modal dialog window (popup).
    """


class GuiMessageWindow(GuiVComponent):
    """Wraps the COM GuiMessageWindow interface (TypeAsNumber 23).

    A system message popup. Note: extends GuiVComponent, NOT GuiFrameWindow.
    """

    @property
    def message_text(self) -> str:
        """Message text content."""
        return str(self._com.MessageText)

    @property
    def message_type(self) -> str:
        """Message type character."""
        return str(self._com.MessageType)

    @property
    def ok_button_text(self) -> str:
        """Text on the OK button."""
        return str(self._com.OKButtonText)

    @property
    def help_button_text(self) -> str:
        """Text on the Help button."""
        return str(self._com.HelpButtonText)

    @property
    def focused_button(self) -> str:
        """Name of the currently focused button."""
        return str(self._com.FocusedButton)

    @property
    def visible(self) -> bool:
        """Whether the message window is visible."""
        return bool(self._com.Visible)
