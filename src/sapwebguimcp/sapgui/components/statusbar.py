"""GuiStatusbar and GuiStatusPane — status bar components."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVComponent


class GuiStatusbar(GuiVComponent):
    """Wraps the COM GuiStatusbar interface (TypeAsNumber 103).

    The status bar at the bottom of the SAP GUI window.
    Note: extends GuiVComponent, NOT GuiVContainer.
    """

    @property
    def message_type(self) -> str:
        return self._com.MessageType


class GuiStatusPane(GuiVComponent):
    """Wraps the COM GuiStatusPane interface (TypeAsNumber 43).

    An individual pane within the status bar area.
    """


class GuiVHViewSwitch(GuiVComponent):
    """Wraps the COM GuiVHViewSwitch interface (TypeAsNumber 129).

    Vertical/Horizontal view switcher control.
    """
