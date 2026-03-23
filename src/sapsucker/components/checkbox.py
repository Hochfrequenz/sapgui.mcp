"""GuiCheckBox and GuiRadioButton — toggle components."""

from __future__ import annotations

from sapsucker.components.base import GuiVComponent

__all__ = ["GuiCheckBox", "GuiRadioButton"]


class GuiCheckBox(GuiVComponent):
    """Wraps the COM GuiCheckBox interface (TypeAsNumber 42)."""

    @property
    def selected(self) -> bool:
        """Whether the checkbox is checked."""
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def highlighted(self) -> bool:
        """Whether the checkbox is visually highlighted."""
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        """Whether the checkbox belongs to a list."""
        return bool(self._com.IsListElement)

    @property
    def color_index(self) -> int:
        """Color index of the checkbox."""
        return int(self._com.ColorIndex)

    @property
    def color_intensified(self) -> bool:
        """Whether the color is intensified."""
        return bool(self._com.ColorIntensified)

    @property
    def color_inverse(self) -> bool:
        """Whether the color is inverted."""
        return bool(self._com.ColorInverse)


class GuiRadioButton(GuiVComponent):
    """Wraps the COM GuiRadioButton interface (TypeAsNumber 41)."""

    @property
    def selected(self) -> bool:
        """Whether the radio button is selected."""
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def highlighted(self) -> bool:
        """Whether the radio button is visually highlighted."""
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        """Whether the radio button belongs to a list."""
        return bool(self._com.IsListElement)

    @property
    def group_count(self) -> int:
        """Number of radio buttons in the group."""
        return int(self._com.GroupCount)

    @property
    def group_pos(self) -> int:
        """Position of this radio button within its group."""
        return int(self._com.GroupPos)
