"""GuiStatusbar and GuiStatusPane — status bar components."""

from __future__ import annotations

from sapsucker.components.base import GuiVComponent

__all__ = ["GuiStatusPane", "GuiStatusbar", "GuiVHViewSwitch"]


class GuiStatusbar(GuiVComponent):
    """Wraps the COM GuiStatusbar interface (TypeAsNumber 103).

    The status bar at the bottom of the SAP GUI window.
    Note: extends GuiVComponent, NOT GuiVContainer.
    """

    @property
    def message_type(self) -> str:
        """Message type character (S, W, E, A, I, or empty)."""
        return str(self._com.MessageType)


class GuiStatusPane(GuiVComponent):
    """Individual pane within the status bar (TypeAsNumber 43)."""


class GuiVHViewSwitch(GuiVComponent):
    """View switch control in the status bar area (TypeAsNumber 129)."""
