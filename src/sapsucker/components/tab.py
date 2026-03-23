"""Tab components — GuiTabStrip and GuiTab."""

from __future__ import annotations

from sapsucker.components.base import GuiVContainer

__all__ = ["GuiTab", "GuiTabStrip"]


class GuiTabStrip(GuiVContainer):
    """Tab strip container holding multiple GuiTab pages (TypeAsNumber 90)."""


class GuiTab(GuiVContainer):
    """Wraps the COM GuiTab interface (TypeAsNumber 91)."""

    def select(self) -> None:
        """Activate this tab page."""
        self._com.Select()
