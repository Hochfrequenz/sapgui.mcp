"""Container components — various GuiVContainer subclasses."""

from __future__ import annotations

from typing import Any

from sapwebguimcp.sapgui.components.base import GuiVContainer

__all__ = [
    "GuiContainerShell",
    "GuiCustomControl",
    "GuiDialogShell",
    "GuiDockShell",
    "GuiGOSShell",
    "GuiScrollContainer",
    "GuiSimpleContainer",
    "GuiSplitterContainer",
    "GuiUserArea",
]


class GuiUserArea(GuiVContainer):
    """Wraps the COM GuiUserArea interface (TypeAsNumber 74).

    The main working area of a window where dynpro elements are placed.
    """

    @property
    def vertical_scrollbar(self) -> Any:
        """Return the vertical scrollbar COM object."""
        return self._com.VerticalScrollbar

    @property
    def horizontal_scrollbar(self) -> Any:
        """Return the horizontal scrollbar COM object."""
        return self._com.HorizontalScrollbar


class GuiScrollContainer(GuiVContainer):
    """Wraps the COM GuiScrollContainer interface (TypeAsNumber 72)."""


class GuiSimpleContainer(GuiVContainer):
    """Wraps the COM GuiSimpleContainer interface (TypeAsNumber 71)."""


class GuiCustomControl(GuiVContainer):
    """Wraps the COM GuiCustomControl interface (TypeAsNumber 50)."""


class GuiContainerShell(GuiVContainer):
    """Wraps the COM GuiContainerShell interface (TypeAsNumber 51)."""


class GuiDialogShell(GuiVContainer):
    """Wraps the COM GuiDialogShell interface (TypeAsNumber 125)."""


class GuiDockShell(GuiVContainer):
    """Wraps the COM GuiDockShell interface (TypeAsNumber 126)."""


class GuiGOSShell(GuiVContainer):
    """Wraps the COM GuiGOSShell interface (TypeAsNumber 123)."""


class GuiSplitterContainer(GuiVContainer):
    """Wraps the COM GuiSplitterContainer interface (TypeAsNumber 75)."""
