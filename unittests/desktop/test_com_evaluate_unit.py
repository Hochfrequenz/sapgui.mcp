"""Unit tests for COM evaluate tool helpers."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from sapguimcp.tools.com_tools import _safe_attr, _serialize_com_result


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


from sapguimcp.tools.com_tools import ComOperationInput, FindByNameRef, _execute_single_op


def _make_mock_session(element_map: dict):
    """Create a mock session with find_by_id routing."""
    session = MagicMock()

    def find_by_id(element_id, raise_error=True):
        if element_id in element_map:
            return element_map[element_id]
        if raise_error:
            raise Exception(f"Element not found: {element_id}")
        return None

    session.find_by_id = find_by_id
    return session


class TestChainedPropertyAccess:
    def test_single_level_get(self):
        """Backward compat: single property still works."""
        elem = MagicMock()
        elem.com.Text = "hello"
        session = _make_mock_session({"wnd[0]/usr/txt1": elem})
        op = ComOperationInput(element_id="wnd[0]/usr/txt1", action="get", property_or_method="Text")
        result = _execute_single_op(session, op)
        assert result.success
        assert result.result == '"hello"'

    def test_chained_get(self):
        """Chained property: Children.Count works."""
        children = MagicMock()
        children.Count = 3
        elem = MagicMock()
        elem.com.Children = children
        session = _make_mock_session({"wnd[0]/usr": elem})
        op = ComOperationInput(element_id="wnd[0]/usr", action="get", property_or_method="Children.Count")
        result = _execute_single_op(session, op)
        assert result.success
        assert result.result == "3"

    def test_chained_call(self):
        """Chained call: Children.Item(0) works."""
        item = MagicMock()
        item.Id = "child_id"
        children = MagicMock()
        children.Item = MagicMock(return_value=item)
        elem = MagicMock()
        elem.com.Children = children
        session = _make_mock_session({"wnd[0]/usr": elem})
        op = ComOperationInput(element_id="wnd[0]/usr", action="call", property_or_method="Children.Item", args=[0])
        result = _execute_single_op(session, op)
        assert result.success
        children.Item.assert_called_once_with(0)

    def test_parent_blocked(self):
        """Parent in chain is blocked for safety."""
        elem = MagicMock()
        session = _make_mock_session({"wnd[0]": elem})
        op = ComOperationInput(element_id="wnd[0]", action="get", property_or_method="Parent.Id")
        result = _execute_single_op(session, op)
        assert not result.success
        assert "Parent" in result.error

    def test_chained_set(self):
        """Chained set: nested property write works."""
        inner = MagicMock()
        inner.Text = "old"
        elem = MagicMock()
        elem.com.Inner = inner
        session = _make_mock_session({"wnd[0]/usr/txt1": elem})
        op = ComOperationInput(
            element_id="wnd[0]/usr/txt1", action="set", property_or_method="Inner.Text", args=["new"]
        )
        result = _execute_single_op(session, op)
        assert result.success


class TestFindByNameResolver:
    def test_find_by_name_get(self):
        """FindByName resolves element, then get works."""
        field = MagicMock()
        field.Text = "Joel"
        container = MagicMock()
        container.com.FindByName = MagicMock(return_value=field)
        session = _make_mock_session({"wnd[0]/usr": container})
        op = ComOperationInput(
            element_id="wnd[0]/usr",
            action="get",
            property_or_method="Text",
            find_by_name=FindByNameRef(name="BUT000-NAME_LAST", type_name="GuiTextField"),
        )
        result = _execute_single_op(session, op)
        assert result.success
        assert result.result == '"Joel"'
        container.com.FindByName.assert_called_once_with("BUT000-NAME_LAST", "GuiTextField")

    def test_find_by_name_set(self):
        """FindByName resolves element, then set works."""
        field = MagicMock()
        field.Text = ""
        container = MagicMock()
        container.com.FindByName = MagicMock(return_value=field)
        session = _make_mock_session({"wnd[0]/usr": container})
        op = ComOperationInput(
            element_id="wnd[0]/usr",
            action="set",
            property_or_method="Text",
            args=["NewValue"],
            find_by_name=FindByNameRef(name="BUT000-NAME_LAST", type_name="GuiTextField"),
        )
        result = _execute_single_op(session, op)
        assert result.success

    def test_find_by_name_not_found(self):
        """FindByName returns None -> error."""
        container = MagicMock()
        container.com.FindByName = MagicMock(return_value=None)
        session = _make_mock_session({"wnd[0]/usr": container})
        op = ComOperationInput(
            element_id="wnd[0]/usr",
            action="get",
            property_or_method="Text",
            find_by_name=FindByNameRef(name="NONEXIST", type_name="GuiTextField"),
        )
        result = _execute_single_op(session, op)
        assert not result.success
        assert "FindByName" in result.error
        assert "NONEXIST" in result.error


class TestElementNotFound:
    def test_element_not_found_returns_error(self):
        """Standard element-not-found path returns error."""
        session = _make_mock_session({})
        op = ComOperationInput(element_id="wnd[0]/usr/doesNotExist", action="get", property_or_method="Text")
        result = _execute_single_op(session, op)
        assert not result.success
        assert "Element not found" in result.error
        assert "doesNotExist" in result.error


class TestSimpleCall:
    def test_single_level_call(self):
        """Simple single-level method call works."""
        elem = MagicMock()
        elem.com.SendVKey = MagicMock(return_value=None)
        session = _make_mock_session({"wnd[0]": elem})
        op = ComOperationInput(element_id="wnd[0]", action="call", property_or_method="SendVKey", args=[0])
        result = _execute_single_op(session, op)
        assert result.success
        elem.com.SendVKey.assert_called_once_with(0)
