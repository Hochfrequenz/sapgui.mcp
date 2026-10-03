"""Unit tests for COM evaluate tool helpers."""

import json
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from fastmcp import Client, FastMCP

from sapguimcp.backend.desktop._com_thread import ComBatchInterruptedError
from sapguimcp.backend.desktop.models.com_results import ComOperation
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


from sapguimcp.tools.com_tools import _run_operations


def _op(element_id: str = "wnd[0]/usr/txt1", action: str = "get") -> ComOperationInput:
    return ComOperationInput(element_id=element_id, action=action, property_or_method="Text")


class TestRunOperationsStopOnError:
    """Issue #851: fail-fast batch execution and its aggregate signals."""

    @staticmethod
    def _session_with_failures(failing_ids: set[str], calls: list[str]):
        """Mock session that records read order and fails reads of the given ids."""

        def find_by_id(element_id: str, raise_error: bool = True) -> MagicMock:  # noqa: ARG001
            calls.append(element_id)
            if element_id in failing_ids:
                raise Exception(f"Element not found: {element_id}")
            elem = MagicMock()
            elem.com.Text = "ok"
            return elem

        session = MagicMock()
        session.find_by_id = find_by_id
        return session

    def test_default_runs_all_ops_despite_failure(self):
        calls: list[str] = []
        session = self._session_with_failures({"wnd[0]/usr/txt2"}, calls)
        ops = [_op("wnd[0]/usr/txt1"), _op("wnd[0]/usr/txt2"), _op("wnd[0]/usr/txt3")]
        results, aborted = _run_operations(session, ops, stop_on_error=False)
        assert len(calls) == 3, "default must keep running after a failed op"
        assert [r.success for r in results] == [True, False, True]
        assert aborted is None

    def test_stop_on_error_stops_at_first_failure(self):
        calls: list[str] = []
        session = self._session_with_failures({"wnd[0]/usr/txt2"}, calls)
        ops = [_op("wnd[0]/usr/txt1"), _op("wnd[0]/usr/txt2"), _op("wnd[0]/usr/txt3")]
        results, aborted = _run_operations(session, ops, stop_on_error=True)
        assert [r.success for r in results] == [True, False]
        assert aborted == 1

    def test_stop_on_error_no_failures_runs_all(self):
        calls: list[str] = []
        session = self._session_with_failures(set(), calls)
        ops = [_op("wnd[0]/usr/txt1"), _op("wnd[0]/usr/txt2")]
        results, aborted = _run_operations(session, ops, stop_on_error=True)
        assert all(r.success for r in results)
        assert aborted is None

    def test_first_op_failure_returns_only_failed_op(self):
        calls: list[str] = []
        session = self._session_with_failures({"wnd[0]/usr/txt1"}, calls)
        ops = [_op("wnd[0]/usr/txt1"), _op("wnd[0]/usr/txt2")]
        results, aborted = _run_operations(session, ops, stop_on_error=True)
        assert len(results) == 1
        assert aborted == 0

    def test_set_readback_failure_is_not_op_failure(self):
        """setattr succeeded, read-back raised -> success=True (issue #851 companion fix)."""
        raw = MagicMock()
        type(raw).Text = PropertyMock(side_effect=[None, Exception("write-only")])  # setattr, readback
        elem = MagicMock()
        elem.com = raw
        session = _make_mock_session({"wnd[0]/usr/txt1": elem})
        op = ComOperationInput(element_id="wnd[0]/usr/txt1", action="set", property_or_method="Text", args=["x"])
        result = _execute_single_op(session, op)
        assert result.success
        payload = json.loads(result.result or "{}")
        assert payload == {"written": True, "readback_error": "write-only"}

    def test_set_write_failure_is_op_failure(self):
        """setattr itself raising -> success=False."""
        raw = MagicMock()
        type(raw).Text = PropertyMock(side_effect=Exception("read-only"))
        elem = MagicMock()
        elem.com = raw
        session = _make_mock_session({"wnd[0]/usr/txt1": elem})
        op = ComOperationInput(element_id="wnd[0]/usr/txt1", action="set", property_or_method="Text", args=["x"])
        result = _execute_single_op(session, op)
        assert not result.success

    def test_multiple_failures_counted(self):
        calls: list[str] = []
        session = self._session_with_failures({"wnd[0]/usr/txt1", "wnd[0]/usr/txt3"}, calls)
        ops = [_op("wnd[0]/usr/txt1"), _op("wnd[0]/usr/txt2"), _op("wnd[0]/usr/txt3")]
        results, aborted = _run_operations(session, ops, stop_on_error=False)
        assert sum(1 for r in results if not r.success) == 2
        assert aborted is None


class TestComEvaluateWiring:
    """The registered tool must wire the aggregates into ComEvaluateResult (#851)."""

    @staticmethod
    def _server():
        from sapguimcp.backend.desktop import DesktopBackend
        from sapguimcp.tools.com_tools import register_com_tools

        session = MagicMock()
        elem = MagicMock()
        type(elem).com = PropertyMock(return_value=elem)
        elem.Text = "ok"

        def find_by_id(element_id: str, raise_error: bool = True):  # noqa: ARG001
            if "missing" in element_id:
                raise Exception(f"Element not found: {element_id}")
            return elem

        session.find_by_id = find_by_id

        class _FakeDesktopBackend(DesktopBackend):
            """Minimal stand-in passing the isinstance guard without COM."""

            def __init__(self) -> None:
                self._fake_session = session

            @property
            def backend_type(self) -> str:
                return "desktop"

            def require_session(self):
                return self._fake_session

        backend = _FakeDesktopBackend()
        backend.com = MagicMock()
        backend.com.run = AsyncMock(side_effect=lambda fn: fn())

        server = FastMCP("t")
        register_com_tools(server)
        return server, backend

    @staticmethod
    def _ops() -> list[ComOperationInput]:
        return [
            ComOperationInput(element_id="wnd[0]/usr/txt1", action="get", property_or_method="Text"),
            ComOperationInput(element_id="wnd[0]/usr/missing", action="get", property_or_method="Text"),
            ComOperationInput(element_id="wnd[0]/usr/txt1", action="get", property_or_method="Text"),
        ]

    @pytest.mark.anyio
    async def test_default_aggregates_failed_count(self):
        server, backend = self._server()

        with patch("sapguimcp.tools.com_tools.get_backend", new=AsyncMock(return_value=backend)):
            async with Client(server) as client:
                raw = await client.call_tool(
                    "sap_com_evaluate", {"operations": [op.model_dump() for op in self._ops()]}
                )
        result = json.loads(raw.content[0].text)
        assert result["success"] is True
        assert result["failed_count"] == 1
        assert result["aborted_at_index"] is None
        assert len(result["operations"]) == 3

    @pytest.mark.anyio
    async def test_stop_on_error_wires_aborted_at_index(self):
        server, backend = self._server()

        with patch("sapguimcp.tools.com_tools.get_backend", new=AsyncMock(return_value=backend)):
            async with Client(server) as client:
                raw = await client.call_tool(
                    "sap_com_evaluate",
                    {"operations": [op.model_dump() for op in self._ops()], "stop_on_error": True},
                )
        result = json.loads(raw.content[0].text)
        assert result["success"] is True
        assert result["failed_count"] == 1
        assert result["aborted_at_index"] == 1
        assert len(result["operations"]) == 2


class TestRunOperationsResume:
    """Issue #879: a COM-interrupted batch resumes, never re-runs completed ops."""

    def test_resume_skips_completed_ops(self):
        completed = [
            ComOperation(success=True, result='"a"'),
            ComOperation(success=True, result='"b"'),
        ]
        carrier = ComBatchInterruptedError(completed, 2, -2147417851)
        executed: list[str] = []

        def find_by_id(element_id: str, raise_error: bool = True) -> MagicMock:  # noqa: ARG001
            executed.append(element_id)
            elem = MagicMock()
            elem.com.Text = "ok"
            return elem

        session = MagicMock()
        session.find_by_id = find_by_id
        ops = [
            ComOperationInput(element_id="wnd[0]/usr/txt1", action="get", property_or_method="Text"),
            ComOperationInput(element_id="wnd[0]/usr/txt2", action="get", property_or_method="Text"),
            ComOperationInput(element_id="wnd[0]/usr/txt3", action="get", property_or_method="Text"),
        ]
        results, aborted = _run_operations(session, ops, stop_on_error=False, resume=carrier)
        # Only op 3 ran in this invocation; ops 1-2 came from the carrier.
        assert executed == ["wnd[0]/usr/txt3"]
        assert len(results) == 3
        assert results[0] is completed[0]
        assert results[2].success
        assert aborted is None

    def test_retryable_error_from_op_raises_carrier(self, monkeypatch):
        """A retryable COM error escaping an op re-raises as a resume carrier."""
        from sapguimcp.tools import com_tools

        class FakeComError(Exception):
            def __init__(self, hr):
                super().__init__(hr)
                self.args = (hr,)

        done = [ComOperation(success=True, result='"a"')]
        ops = [
            ComOperationInput(element_id="wnd[0]/usr/txt1", action="get", property_or_method="Text"),
            ComOperationInput(element_id="wnd[0]/usr/txt2", action="get", property_or_method="Text"),
        ]

        def fake_op(session, operation):  # noqa: ARG001
            raise FakeComError(-2147417851)

        monkeypatch.setattr(com_tools, "_execute_single_op", fake_op)
        with pytest.raises(com_tools.ComBatchInterruptedError) as exc_info:
            _run_operations(MagicMock(), ops, stop_on_error=False, resume=ComBatchInterruptedError(done, 1, 0))
        assert exc_info.value.error_code == -2147417851
        assert exc_info.value.completed == done

    def test_non_retryable_error_propagates(self, monkeypatch):
        from sapguimcp.tools import com_tools

        def fake_op(session, operation):  # noqa: ARG001
            raise KeyError("boom")

        monkeypatch.setattr(com_tools, "_execute_single_op", fake_op)
        op = ComOperationInput(element_id="wnd[0]/usr/txt1", action="get", property_or_method="Text")
        with pytest.raises(KeyError):
            _run_operations(MagicMock(), [op], stop_on_error=False)
