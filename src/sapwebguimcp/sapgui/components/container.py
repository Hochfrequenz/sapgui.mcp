"""Container components — various GuiVContainer subclasses."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVContainer


class GuiScrollbar:
    """Scrollbar object exposed by GuiUserArea.

    Not a GuiComponent subclass — it's a standalone helper object
    accessible via GuiUserArea.vertical_scrollbar / horizontal_scrollbar.
    """

    def __init__(self, com_obj) -> None:  # noqa: ANN001
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
        self._com.Position = value

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
