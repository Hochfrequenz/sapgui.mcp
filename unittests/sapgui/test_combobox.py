"""Tests for GuiComboBox and GuiComboBoxEntry — issue #515."""

from unittest.mock import MagicMock

from sapwebguimcp.sapgui.components.combobox import GuiComboBox, GuiComboBoxEntry
from unittests.sapgui.conftest import make_mock_com


def _make_combo(**kwargs):
    com = make_mock_com(type_as_number=34, type_name="GuiComboBox", **kwargs)
    return GuiComboBox(com)


def _make_entry(key="K1", value="Value 1", pos=0):
    com = MagicMock()
    com.Key = key
    com.Value = value
    com.Pos = pos
    return GuiComboBoxEntry(com)


class TestGuiComboBoxEntry:
    def test_key(self):
        entry = _make_entry(key="001")
        assert entry.key == "001"

    def test_value(self):
        entry = _make_entry(value="First entry")
        assert entry.value == "First entry"

    def test_pos(self):
        entry = _make_entry(pos=3)
        assert entry.pos == 3

    def test_repr(self):
        entry = _make_entry(key="K1", value="Val")
        r = repr(entry)
        assert "K1" in r
        assert "Val" in r


class TestGuiComboBox:
    def test_value_getter(self):
        combo = _make_combo(Value="001")
        assert combo.value == "001"

    def test_value_setter(self):
        combo = _make_combo()
        combo.value = "002"
        assert combo._com.Value == "002"

    def test_item_count(self):
        combo = _make_combo()
        combo._com.Entries.Count = 5
        assert combo.item_count == 5

    def test_is_required(self):
        combo = _make_combo(Required=True)
        assert combo.is_required is True

    def test_highlighted(self):
        combo = _make_combo(Highlighted=False)
        assert combo.highlighted is False

    def test_is_list_element(self):
        combo = _make_combo(IsListElement=False)
        assert combo.is_list_element is False

    def test_entries_returns_typed_list(self):
        combo = _make_combo()
        entry_com = MagicMock()
        entry_com.Key = "K1"
        entry_com.Value = "V1"
        entry_com.Pos = 0
        combo._com.Entries.Count = 1
        combo._com.Entries.Item.return_value = entry_com
        entries = combo.entries
        assert len(entries) == 1
        assert isinstance(entries[0], GuiComboBoxEntry)
        assert entries[0].key == "K1"

    def test_entries_empty(self):
        combo = _make_combo()
        combo._com.Entries.Count = 0
        assert combo.entries == []
