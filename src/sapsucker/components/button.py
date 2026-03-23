"""GuiButton — pushbutton component."""

from __future__ import annotations

from sapsucker.components.base import GuiVComponent

__all__ = ["GuiButton"]


class GuiButton(GuiVComponent):
    """Wraps the COM GuiButton interface (TypeAsNumber 40).

    A clickable pushbutton on a screen or toolbar.
    """

    @property
    def highlighted(self) -> bool:
        """Whether the button is visually highlighted."""
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        """Whether the button belongs to a list."""
        return bool(self._com.IsListElement)

    def press(self) -> None:
        """Press (click) the button."""
        self._com.Press()
