"""Field components — GuiTextField, GuiCTextField, GuiPasswordField, GuiLabel, GuiBox."""

from __future__ import annotations

from sapsucker.components.base import GuiVComponent

__all__ = ["GuiBox", "GuiCTextField", "GuiLabel", "GuiPasswordField", "GuiTextField"]


class GuiTextField(GuiVComponent):
    """Wraps the COM GuiTextField interface (TypeAsNumber 31).

    A standard single-line input field.
    """

    @property
    def caret_position(self) -> int:
        """Current caret (cursor) position within the field."""
        return int(self._com.CaretPosition)

    @caret_position.setter
    def caret_position(self, value: int) -> None:
        self._com.CaretPosition = value

    @property
    def max_length(self) -> int:
        """Maximum number of characters allowed."""
        return int(self._com.MaxLength)

    @property
    def is_required(self) -> bool:
        """Whether the field is mandatory."""
        return bool(self._com.Required)

    @property
    def is_numerical(self) -> bool:
        """Whether only numeric input is accepted."""
        return bool(self._com.Numerical)

    @property
    def is_hotspot(self) -> bool:
        """Whether the field acts as a clickable hotspot."""
        return bool(self._com.IsHotspot)

    @property
    def highlighted(self) -> bool:
        """Whether the field is visually highlighted."""
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        """Whether the field belongs to a list."""
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
        """Current caret position."""
        return int(self._com.CaretPosition)

    @caret_position.setter
    def caret_position(self, value: int) -> None:
        self._com.CaretPosition = value

    @property
    def max_length(self) -> int:
        """Maximum text length."""
        return int(self._com.MaxLength)

    @property
    def is_numerical(self) -> bool:
        """Whether the label displays numeric content."""
        return bool(self._com.Numerical)

    @property
    def is_hotspot(self) -> bool:
        """Whether the label acts as a clickable hotspot."""
        return bool(self._com.IsHotspot)

    @property
    def is_left_label(self) -> bool:
        """Whether this is a left-aligned label for another field."""
        return bool(self._com.IsLeftLabel)

    @property
    def is_right_label(self) -> bool:
        """Whether this is a right-aligned label for another field."""
        return bool(self._com.IsRightLabel)

    @property
    def is_list_element(self) -> bool:
        """Whether the label belongs to a list."""
        return bool(self._com.IsListElement)

    @property
    def highlighted(self) -> bool:
        """Whether the label is visually highlighted."""
        return bool(self._com.Highlighted)

    @property
    def displayed_text(self) -> str:
        """Text as currently displayed on screen."""
        return str(self._com.DisplayedText)

    @property
    def color_index(self) -> int:
        """Color index of the label."""
        return int(self._com.ColorIndex)

    @property
    def color_intensified(self) -> bool:
        """Whether the color is intensified."""
        return bool(self._com.ColorIntensified)

    @property
    def color_inverse(self) -> bool:
        """Whether the color is inverted."""
        return bool(self._com.ColorInverse)

    @property
    def char_height(self) -> int:
        """Character height in rows."""
        return int(self._com.CharHeight)

    @property
    def char_width(self) -> int:
        """Character width in columns."""
        return int(self._com.CharWidth)

    @property
    def char_left(self) -> int:
        """Character-based left position."""
        return int(self._com.CharLeft)

    @property
    def char_top(self) -> int:
        """Character-based top position."""
        return int(self._com.CharTop)

    @property
    def row_text(self) -> str:
        """Full text of the row containing this label."""
        return str(self._com.RowText)


class GuiBox(GuiVComponent):
    """Group box frame, NOT a container (TypeAsNumber 62)."""
