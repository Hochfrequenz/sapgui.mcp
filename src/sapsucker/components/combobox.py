"""GuiComboBox and GuiComboBoxEntry — dropdown list components."""

from __future__ import annotations

from typing import Any

from sapsucker.components.base import GuiVComponent

__all__ = ["GuiComboBox", "GuiComboBoxEntry"]


class GuiComboBoxEntry:
    """A single entry in a GuiComboBox dropdown list."""

    def __init__(self, com_entry: Any) -> None:
        self._com = com_entry

    @property
    def key(self) -> str:
        """Key value of the entry."""
        return str(self._com.Key)

    @property
    def value(self) -> str:
        """Display value of the entry."""
        return str(self._com.Value)

    @property
    def pos(self) -> int:
        """Position index of the entry."""
        return int(self._com.Pos)

    def __repr__(self) -> str:
        return f"GuiComboBoxEntry(key={self._com.Key!r}, value={self._com.Value!r})"


class GuiComboBox(GuiVComponent):
    """Wraps the COM GuiComboBox interface (TypeAsNumber 34).

    A dropdown selection list. Set value by key string.
    """

    @property
    def value(self) -> str:
        """Currently selected key value."""
        return str(self._com.Value)

    @value.setter
    def value(self, key: str) -> None:
        self._com.Value = key

    @property
    def entries(self) -> list[GuiComboBoxEntry]:
        """Return all entries as a list of GuiComboBoxEntry."""
        result = []
        for i in range(self._com.Entries.Count):
            result.append(GuiComboBoxEntry(self._com.Entries.Item(i)))
        return result

    @property
    def item_count(self) -> int:
        """Number of entries in the dropdown."""
        return int(self._com.Entries.Count)

    @property
    def is_required(self) -> bool:
        """Whether a value must be selected."""
        return bool(self._com.Required)

    @property
    def highlighted(self) -> bool:
        """Whether the combobox is visually highlighted."""
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        """Whether the combobox belongs to a list."""
        return bool(self._com.IsListElement)
