"""Toolbar and menu components — GuiToolbar, GuiMenubar, GuiMenu, GuiTitlebar."""

from __future__ import annotations

from sapsucker.components.base import GuiVContainer

__all__ = ["GuiContextMenu", "GuiMenu", "GuiMenubar", "GuiTitlebar", "GuiToolbar"]


class GuiToolbar(GuiVContainer):
    """Standard SAP toolbar below the menu bar (TypeAsNumber 101)."""


class GuiMenubar(GuiVContainer):
    """The menu bar at the top of the SAP window (TypeAsNumber 111)."""


class GuiMenu(GuiVContainer):
    """A menu or menu item. Call select() to click it (TypeAsNumber 110)."""

    def select(self) -> None:
        """Click / activate this menu item."""
        self._com.Select()


class GuiContextMenu(GuiMenu):
    """Context menu item (type 127).

    Extends GuiMenu — inherits select() and other menu methods.
    Appears when a context menu is open. Each item in the menu is a
    GuiContextMenu object. Call select() to click the menu item.
    """


class GuiTitlebar(GuiVContainer):
    """The title bar of a SAP window (TypeAsNumber 102). Only available in New Visual Design."""
