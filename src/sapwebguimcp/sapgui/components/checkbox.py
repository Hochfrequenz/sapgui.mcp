"""GuiCheckBox and GuiRadioButton — toggle components."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVComponent


class GuiCheckBox(GuiVComponent):
    """Wraps the COM GuiCheckBox interface (TypeAsNumber 42)."""

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    @property
    def color_index(self) -> int:
        return self._com.ColorIndex

    @property
    def color_intensified(self) -> bool:
        return bool(self._com.ColorIntensified)

    @property
    def color_inverse(self) -> bool:
        return bool(self._com.ColorInverse)


class GuiRadioButton(GuiVComponent):
    """Wraps the COM GuiRadioButton interface (TypeAsNumber 41)."""

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    @property
    def group_count(self) -> int:
        return self._com.GroupCount

    @property
    def group_pos(self) -> int:
        return self._com.GroupPos
