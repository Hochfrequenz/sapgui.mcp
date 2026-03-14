"""Tests for collection wrapper classes."""

from unittest.mock import MagicMock

import pytest

from sapwebguimcp.sapgui.components.collection import GuiCollection, GuiComponentCollection


def _make_com_collection(items):
    """Create a mock COM collection with Count, Item(), and __iter__."""
    col = MagicMock()
    col.Count = len(items)
    col.Item = lambda i: items[i]
    # COM collections may not support __iter__ natively, but our wrapper handles it
    return col


class TestGuiComponentCollection:
    def test_len(self):
        col = _make_com_collection(["a", "b", "c"])
        gcc = GuiComponentCollection(col)
        assert len(gcc) == 3

    def test_getitem(self):
        col = _make_com_collection(["a", "b", "c"])
        gcc = GuiComponentCollection(col)
        assert gcc[0] == "a"
        assert gcc[2] == "c"

    def test_getitem_negative_index(self):
        col = _make_com_collection(["a", "b", "c"])
        gcc = GuiComponentCollection(col)
        assert gcc[-1] == "c"

    def test_getitem_index_error(self):
        col = _make_com_collection(["a"])
        gcc = GuiComponentCollection(col)
        with pytest.raises(IndexError):
            gcc[5]

    def test_iter(self):
        col = _make_com_collection(["x", "y"])
        gcc = GuiComponentCollection(col)
        assert list(gcc) == ["x", "y"]

    def test_repr(self):
        col = _make_com_collection(["a", "b"])
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
