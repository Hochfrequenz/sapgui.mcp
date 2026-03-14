"""Tests for collection wrapper classes."""

from unittest.mock import MagicMock

import pytest

from sapwebguimcp.sapgui.components.collection import GuiCollection, GuiComponentCollection
from unittests.sapgui.conftest import make_mock_com


def _make_com_collection(items):
    """Create a mock COM collection with Count, Item(), and __iter__."""
    col = MagicMock()
    col.Count = len(items)
    col.Item = lambda i: items[i]
    # COM collections may not support __iter__ natively, but our wrapper handles it
    return col


def _make_component_items(count):
    """Create a list of mock COM objects that can be wrapped by the factory."""
    return [make_mock_com(type_as_number=31, type_name="GuiTextField", name=f"item{i}") for i in range(count)]


class TestGuiComponentCollection:
    def test_len(self):
        items = _make_component_items(3)
        col = _make_com_collection(items)
        gcc = GuiComponentCollection(col)
        assert len(gcc) == 3

    def test_getitem(self):
        items = _make_component_items(3)
        col = _make_com_collection(items)
        gcc = GuiComponentCollection(col)
        # Items are now wrapped; verify the underlying COM object
        assert gcc[0].com is items[0]
        assert gcc[2].com is items[2]

    def test_getitem_negative_index(self):
        items = _make_component_items(3)
        col = _make_com_collection(items)
        gcc = GuiComponentCollection(col)
        assert gcc[-1].com is items[2]

    def test_getitem_index_error(self):
        items = _make_component_items(1)
        col = _make_com_collection(items)
        gcc = GuiComponentCollection(col)
        with pytest.raises(IndexError):
            gcc[5]

    def test_iter(self):
        items = _make_component_items(2)
        col = _make_com_collection(items)
        gcc = GuiComponentCollection(col)
        result = list(gcc)
        assert [r.com for r in result] == items

    def test_repr(self):
        items = _make_component_items(2)
        col = _make_com_collection(items)
        gcc = GuiComponentCollection(col)
        r = repr(gcc)
        assert "GuiComponentCollection" in r
        assert "2" in r

    def test_empty(self):
        col = _make_com_collection([])
        gcc = GuiComponentCollection(col)
        assert len(gcc) == 0
        assert list(gcc) == []


class TestGuiCollection:
    def test_len(self):
        col = _make_com_collection(["a", "b"])
        gc = GuiCollection(col)
        assert len(gc) == 2

    def test_getitem(self):
        col = _make_com_collection(["a", "b"])
        gc = GuiCollection(col)
        assert gc[0] == "a"

    def test_iter(self):
        col = _make_com_collection(["x", "y", "z"])
        gc = GuiCollection(col)
        assert list(gc) == ["x", "y", "z"]

    def test_repr(self):
        col = _make_com_collection(["a"])
        gc = GuiCollection(col)
        r = repr(gc)
        assert "GuiCollection" in r
        assert "1" in r
