"""GuiComboBox and GuiComboBoxEntry — dropdown list components."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiVComponent


class GuiComboBoxEntry:
    """A single entry in a GuiComboBox dropdown list."""

    def __init__(self, com_entry) -> None:
        self._com = com_entry

    @property
    def key(self) -> str:
        return self._com.Key

    @property
    def value(self) -> str:
        return self._com.Value

    @property
    def pos(self) -> int:
        return self._com.Pos

    def __repr__(self) -> str:
        return f"GuiComboBoxEntry(key={self._com.Key!r}, value={self._com.Value!r})"


class GuiComboBox(GuiVComponent):
    """Wraps the COM GuiComboBox interface (TypeAsNumber 34).

    A dropdown selection list. Set value by key string.
    """

    @property
    def value(self) -> str:
        return self._com.Value

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
        return self._com.Entries.Count

    @property
    def is_required(self) -> bool:
        return bool(self._com.Required)

    @property
    def highlighted(self) -> bool:
        return bool(self._com.Highlighted)

    @property
    def is_list_element(self) -> bool:
        return bool(self._com.IsListElement)
