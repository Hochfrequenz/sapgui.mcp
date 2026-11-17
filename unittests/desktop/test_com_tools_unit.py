"""Unit tests for COM evaluate tool — mocked, no SAP connection needed."""

import json
from unittest.mock import MagicMock, PropertyMock

import pytest

from sapguimcp.tools.com_tools import (
    ComOperationInput,
    _execute_single_op,
    _serialize_com_result,
)

# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------


class TestSerializeComResult:
    """Tests for _serialize_com_result."""

    def test_none(self) -> None:
        assert _serialize_com_result(None) == "null"

    def test_string(self) -> None:
        assert _serialize_com_result("hello") == '"hello"'

    def test_int(self) -> None:
        assert _serialize_com_result(42) == "42"

    def test_bool(self) -> None:
        assert _serialize_com_result(True) == "true"

    def test_float(self) -> None:
        assert _serialize_com_result(3.14) == "3.14"

    def test_complex_object_falls_back_to_str(self) -> None:
        obj = object()
        result = _serialize_com_result(obj)
        parsed = json.loads(result)
        assert isinstance(parsed, str)


# ---------------------------------------------------------------------------
# Operation execution tests
# ---------------------------------------------------------------------------


def _make_session(element_mock: MagicMock | None = None) -> MagicMock:
    """Create a mock SAP session with find_by_id returning element_mock."""
    session = MagicMock()
    if element_mock is not None:
        session.find_by_id.return_value = element_mock
    else:
        session.find_by_id.side_effect = Exception("Element not found")
    return session


class TestExecuteSingleOp:
    """Tests for _execute_single_op."""

    def test_get_property(self) -> None:
        """get action reads a property from the element."""
        elem = MagicMock()
        elem.com = MagicMock()
        elem.com.Text = "hello world"
        session = _make_session(elem)

        op = ComOperationInput(
            element_id="wnd[0]/usr/txtFIELD",
            action="get",
            property_or_method="Text",
        )
        result = _execute_single_op(session, op)
        assert result.success
        assert json.loads(result.result) == "hello world"
        assert result.element_id == "wnd[0]/usr/txtFIELD"
        assert result.action == "get"

    def test_set_property(self) -> None:
        """set action writes a property and reads it back."""
        elem = MagicMock()
        elem.com = MagicMock()
        type(elem.com).Text = PropertyMock(return_value="new value")
        session = _make_session(elem)

        op = ComOperationInput(
            element_id="wnd[0]/usr/txtFIELD",
            action="set",
            property_or_method="Text",
            args=["new value"],
        )
        result = _execute_single_op(session, op)
        assert result.success
        assert json.loads(result.result) == "new value"

    def test_call_method(self) -> None:
        """call action invokes a method with args."""
        elem = MagicMock()
        elem.com = MagicMock()
        elem.com.GetCellValue.return_value = "100-100"
        session = _make_session(elem)

        op = ComOperationInput(
            element_id="wnd[0]/usr/cntl/shell",
            action="call",
            property_or_method="GetCellValue",
            args=[0, "MATNR"],
        )
        result = _execute_single_op(session, op)
        assert result.success
        assert json.loads(result.result) == "100-100"
        elem.com.GetCellValue.assert_called_once_with(0, "MATNR")

    def test_call_method_no_args(self) -> None:
        """call action with no args passes empty tuple."""
        elem = MagicMock()
        elem.com = MagicMock()
        elem.com.SomeMethod.return_value = None
        session = _make_session(elem)

        op = ComOperationInput(
            element_id="wnd[0]",
            action="call",
            property_or_method="SomeMethod",
        )
        result = _execute_single_op(session, op)
        assert result.success
        elem.com.SomeMethod.assert_called_once_with()

    def test_element_not_found(self) -> None:
        """Returns failure when element_id doesn't exist."""
        session = _make_session(None)  # find_by_id raises

        op = ComOperationInput(
            element_id="wnd[0]/usr/NONEXISTENT",
            action="get",
            property_or_method="Text",
        )
        result = _execute_single_op(session, op)
        assert not result.success
        assert "not found" in result.error.lower()

    def test_unknown_action_rejected_by_pydantic(self) -> None:
        """Pydantic Literal validation rejects unknown actions."""
        from pydantic import ValidationError  # pylint: disable=import-outside-toplevel

        with pytest.raises(ValidationError, match="action"):
            ComOperationInput(
                element_id="wnd[0]/usr/txtFIELD",
                action="delete",  # type: ignore[arg-type]
                property_or_method="Text",
            )

    def test_property_access_error(self) -> None:
        """Returns failure when property doesn't exist."""
        elem = MagicMock()
        elem.com = MagicMock(spec=[])  # no attributes
        session = _make_session(elem)

        op = ComOperationInput(
            element_id="wnd[0]/usr/txtFIELD",
            action="get",
            property_or_method="NonExistentProp",
        )
        result = _execute_single_op(session, op)
        assert not result.success

    def test_set_without_args(self) -> None:
        """set action with no args sets empty string."""
        elem = MagicMock()
        elem.com = MagicMock()
        type(elem.com).Text = PropertyMock(return_value="")
        session = _make_session(elem)

        op = ComOperationInput(
            element_id="wnd[0]/usr/txtFIELD",
            action="set",
            property_or_method="Text",
        )
        result = _execute_single_op(session, op)
        assert result.success


# ---------------------------------------------------------------------------
# Model serialization tests
# ---------------------------------------------------------------------------


class TestComModels:
    """Tests for Pydantic model roundtrip."""

    def test_operation_input_roundtrip(self) -> None:
        op = ComOperationInput(
            element_id="wnd[0]/usr/txtFIELD",
            action="get",
            property_or_method="Text",
        )
        json_str = op.model_dump_json()
        restored = ComOperationInput.model_validate_json(json_str)
        assert restored.element_id == op.element_id
        assert restored.action == op.action
        assert restored.args is None

    def test_operation_input_with_args(self) -> None:
        op = ComOperationInput(
            element_id="wnd[0]",
            action="call",
            property_or_method="SendVKey",
            args=[0],
        )
        json_str = op.model_dump_json()
        restored = ComOperationInput.model_validate_json(json_str)
        assert restored.args == [0]
