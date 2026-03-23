"""Container components — various GuiVContainer subclasses."""

from __future__ import annotations

from typing import Any

from sapsucker.components.base import GuiVContainer

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


class GuiScrollbar:
    """Scrollbar object exposed by GuiUserArea.

    Not a GuiComponent subclass — it's a standalone helper object
    accessible via GuiUserArea.vertical_scrollbar / horizontal_scrollbar.
    """

    def __init__(self, com_obj: Any) -> None:
        self._com = com_obj

    @property
    def minimum(self) -> int:
        """Minimum scroll position."""
        return int(self._com.Minimum)

    @property
    def maximum(self) -> int:
        """Maximum scroll position."""
        return int(self._com.Maximum)

    @property
    def position(self) -> int:
        """Current scroll position."""
        return int(self._com.Position)

    @position.setter
    def position(self, value: int) -> None:
        self._com.Position = int(value)

    @property
    def page_size(self) -> int:
        """Number of visible rows/columns (page size for scrolling)."""
        return int(self._com.PageSize)

    def __repr__(self) -> str:
        return f"<GuiScrollbar pos={self.position} range={self.minimum}-{self.maximum}>"


class GuiUserArea(GuiVContainer):
    """Wraps the COM GuiUserArea interface (TypeAsNumber 74).

    The main working area of a window where dynpro elements are placed.
    """

    @property
    def vertical_scrollbar(self) -> GuiScrollbar:
        """Vertical scrollbar of the user area."""
        return GuiScrollbar(self._com.VerticalScrollbar)

    @property
    def horizontal_scrollbar(self) -> GuiScrollbar:
        """Horizontal scrollbar of the user area."""
        return GuiScrollbar(self._com.HorizontalScrollbar)


class GuiScrollContainer(GuiVContainer):
    """Scrollable container (TypeAsNumber 72)."""


class GuiSimpleContainer(GuiVContainer):
    """Simple container without scrollbars (TypeAsNumber 71)."""


class GuiCustomControl(GuiVContainer):
    """Wrapper for ActiveX controls on dynpro screens (TypeAsNumber 50). Parent of shell controls."""


class GuiContainerShell(GuiVContainer):
    """Container for shell controls (TypeAsNumber 51)."""


class GuiDialogShell(GuiVContainer):
    """External window container for shells, e.g. toolbar popups (TypeAsNumber 125)."""


class GuiDockShell(GuiVContainer):
    """Dockable shell container (TypeAsNumber 126)."""


class GuiGOSShell(GuiVContainer):
    """Generic Object Services shell (TypeAsNumber 123). Only available in New Visual Design."""


class GuiSplitterContainer(GuiVContainer):
    """Splitter container that divides an area into panes (TypeAsNumber 75)."""
