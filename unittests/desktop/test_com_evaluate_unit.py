"""Unit tests for COM evaluate tool helpers."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from sapwebguimcp.tools.com_tools import _safe_attr, _serialize_com_result


class TestSafeAttr:
    def test_returns_attribute_value(self):
        obj = MagicMock()
        obj.Name = "test_field"
        assert _safe_attr(obj, "Name") == "test_field"

    def test_returns_empty_on_missing(self):
        obj = MagicMock(spec=[])
        assert _safe_attr(obj, "Name") == ""

    def test_returns_empty_on_exception(self):
        obj = MagicMock()
        type(obj).Name = PropertyMock(side_effect=Exception("COM error"))
        assert _safe_attr(obj, "Name") == ""


class TestSerializeComResult:
    def test_none(self):
        assert _serialize_com_result(None) == "null"

    def test_string(self):
        assert _serialize_com_result("hello") == '"hello"'

    def test_int(self):
        assert _serialize_com_result(42) == "42"

    def test_bool(self):
        assert _serialize_com_result(True) == "true"

    def test_com_collection(self):
        """COM collection with .Count and .Item() serialized as JSON array."""
        import json

        item0 = MagicMock()
        item0.Id = "/app/con[0]/ses[0]/wnd[0]/usr/txtFIELD1"
        item0.Type = "GuiTextField"
        item0.Name = "txtFIELD1"
        item0.Text = "value1"

        item1 = MagicMock()
        item1.Id = "/app/con[0]/ses[0]/wnd[0]/usr/txtFIELD2"
        item1.Type = "GuiTextField"
        item1.Name = "txtFIELD2"
        item1.Text = "value2"

        collection = MagicMock()
        collection.Count = 2
        collection.Item = lambda i: [item0, item1][i]

        result = _serialize_com_result(collection)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["Name"] == "txtFIELD1"
        assert parsed[1]["Text"] == "value2"

    def test_com_collection_count_throws(self):
        """When .Count throws, falls back to string representation."""
        obj = MagicMock()
        type(obj).Count = PropertyMock(side_effect=Exception("bad"))
        result = _serialize_com_result(obj)
        assert isinstance(result, str)

    def test_com_object_fallback(self):
        """Non-collection COM object falls back to string."""
        obj = MagicMock(spec=["SomeMethod"])  # no Count attribute
        result = _serialize_com_result(obj)
        assert isinstance(result, str)
