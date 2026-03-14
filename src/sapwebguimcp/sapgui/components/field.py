"""Field components — GuiTextField, GuiCTextField, GuiPasswordField, GuiLabel, GuiBox."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVComponent


class GuiTextField(GuiVComponent):
    """Wraps the COM GuiTextField interface (TypeAsNumber 31).

    A standard single-line input field.
    """

    @property
    def caret_position(self) -> int:
        return self._com.CaretPosition

    @caret_position.setter
    def caret_position(self, value: int) -> None:
        self._com.CaretPosition = value

    @property
    def max_length(self) -> int:
        return self._com.MaxLength

    @property
    def is_required(self) -> bool:
        return bool(self._com.Required)

    @property
    def is_numerical(self) -> bool:
        return bool(self._com.Numerical)

    @property
    def is_hotspot(self) -> bool:
        return bool(self._com.IsHotspot)

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)


class GuiCTextField(GuiTextField):
    """Text field with F4 search help button (TypeAsNumber 32)."""


class GuiPasswordField(GuiTextField):
    """Password input field, text is masked (TypeAsNumber 33)."""


class GuiLabel(GuiVComponent):
    """Wraps the COM GuiLabel interface (TypeAsNumber 30).

    A read-only text label on a screen.
    """

    @property
    def caret_position(self) -> int:
        return self._com.CaretPosition

    @caret_position.setter
    def caret_position(self, value: int) -> None:
        self._com.CaretPosition = value

    @property
    def max_length(self) -> int:
        return self._com.MaxLength

    @property
    def is_numerical(self) -> bool:
        return bool(self._com.Numerical)

    @property
    def is_hotspot(self) -> bool:
        return bool(self._com.IsHotspot)

    @property
    def is_left_label(self) -> bool:
        return bool(self._com.IsLeftLabel)

    @property
    def is_right_label(self) -> bool:
        return bool(self._com.IsRightLabel)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def displayed_text(self) -> str:
        return self._com.DisplayedText

    @property
    def color_index(self) -> int:
        return self._com.ColorIndex

    @property
    def color_intensified(self) -> bool:
        return bool(self._com.ColorIntensified)

    @property
    def color_inverse(self) -> bool:
        return bool(self._com.ColorInverse)

    @property
    def char_height(self) -> int:
        return self._com.CharHeight

    @property
    def char_width(self) -> int:
        return self._com.CharWidth

    @property
    def char_left(self) -> int:
        return self._com.CharLeft

    @property
    def char_top(self) -> int:
        return self._com.CharTop

    @property
    def row_text(self) -> str:
        return self._com.RowText


class GuiBox(GuiVComponent):
    """Group box frame, NOT a container (TypeAsNumber 62)."""
