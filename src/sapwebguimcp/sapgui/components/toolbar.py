"""Toolbar and menu components — GuiToolbar, GuiMenubar, GuiMenu, GuiTitlebar."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVContainer


class GuiToolbar(GuiVContainer):
    """Wraps the COM GuiToolbar interface (TypeAsNumber 101)."""


class GuiMenubar(GuiVContainer):
    """Wraps the COM GuiMenubar interface (TypeAsNumber 111)."""


class GuiMenu(GuiVContainer):
    """Wraps the COM GuiMenu interface (TypeAsNumber 110)."""

    def select(self) -> None:
        """Click / activate this menu item."""
        self._com.Select()


class GuiTitlebar(GuiVContainer):
    """Wraps the COM GuiTitlebar interface (TypeAsNumber 102)."""
