"""Unit tests for sap_run_script — no live SAP required."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, _RPC_S_UNKNOWN_IF
from sapguimcp.backend.desktop.models.script_results import SapRunScriptResult
from sapguimcp.tools.script_tools import (
    SAFE_BUILTINS,
    _run_in_sandbox,
    _wait,
    _wait_until,
    register_script_tools,
)

_FILENAME = "<sap_script>"


_FAR = 1e12  # sandbox deadline far in the future


class _FakeTime:
    """Stand-in for the ``time`` module: ``sleep`` advances ``monotonic``."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _c(script: str):
    """Compile a script string to a code object, as sap_run_script does before dispatching."""
    return compile(script, _FILENAME, "exec")


class TestSapRunScriptResult:
    def test_success_defaults(self):
        r = SapRunScriptResult(output=["hello"])
        assert r.success is True
        assert r.error is None
        assert r.output == ["hello"]
        assert r.error_traceback is None

    def test_failure_factory(self):
        r = SapRunScriptResult.failure("NameError: x")
        assert r.success is False
        assert r.error == "NameError: x"
        assert r.output == []
        assert r.error_traceback is None

    def test_failure_with_partial_output(self):
        r = SapRunScriptResult.failure("KeyError: 'col'", output=["row0", "row1"])
        assert r.success is False
        assert r.output == ["row0", "row1"]

    def test_success_true_with_error_raises(self):
        with pytest.raises(Exception):
            SapRunScriptResult(success=True, error="oops")

    def test_success_false_without_error_raises(self):
        with pytest.raises(Exception):
            SapRunScriptResult(success=False)

    def test_failure_with_traceback(self):
        r = SapRunScriptResult.failure(
            "RuntimeError: bad",
            error_traceback="Traceback (most recent call last):\nRuntimeError: bad",
        )
        assert r.success is False
        assert r.error_traceback == "Traceback (most recent call last):\nRuntimeError: bad"


class TestRunInSandbox:
    def _session(self) -> MagicMock:
        """A mock sapsucker GuiSession — only used when the script touches it."""
        return MagicMock()

    def test_basic_output(self):
        r = _run_in_sandbox(_c("output(42)"), self._session(), deadline=_FAR)
        assert r.success is True
        assert r.output == [42]
        assert r.error is None

    def test_multiple_outputs_collected_in_order(self):
        script = "output(1)\noutput(2)\noutput(3)"
        r = _run_in_sandbox(_c(script), self._session(), deadline=_FAR)
        assert r.output == [1, 2, 3]

    def test_empty_script_succeeds_with_no_output(self):
        r = _run_in_sandbox(_c(""), self._session(), deadline=_FAR)
        assert r.success is True
        assert r.output == []

    def test_import_raises_name_error_not_import_error(self):
        r = _run_in_sandbox(_c("import os"), self._session(), deadline=_FAR)
        assert r.success is False
        assert r.error is not None
        assert r.error.startswith("NameError")

    def test_print_raises_name_error(self):
        r = _run_in_sandbox(_c("print('hi')"), self._session(), deadline=_FAR)
        assert r.success is False
        assert r.error is not None
        assert "NameError" in r.error

    def test_runtime_exception_returns_failure(self):
        r = _run_in_sandbox(_c("raise ValueError('boom')"), self._session(), deadline=_FAR)
        assert r.success is False
        assert r.error == "ValueError: boom"
        assert r.error_traceback is not None
        assert "ValueError" in r.error_traceback

    def test_partial_output_preserved_on_exception(self):
        script = "output('first')\noutput('second')\nraise KeyError('col')"
        r = _run_in_sandbox(_c(script), self._session(), deadline=_FAR)
        assert r.success is False
        assert r.output == ["first", "second"]
        assert "KeyError" in r.error

    def test_non_serializable_output_coerced_to_str(self):
        # Pass a MagicMock (not JSON-serializable) — should become its str()
        script = "output(session)"  # session is a MagicMock
        session = self._session()
        r = _run_in_sandbox(_c(script), session, deadline=_FAR)
        assert r.success is True
        assert len(r.output) == 1
        assert isinstance(r.output[0], str)

    def test_loops_and_conditionals_work(self):
        script = "result = []\nfor i in range(5):\n    if i % 2 == 0:\n        result.append(i)\noutput(result)\n"
        r = _run_in_sandbox(_c(script), self._session(), deadline=_FAR)
        assert r.success is True
        assert r.output == [[0, 2, 4]]

    def test_safe_builtins_available(self):
        script = (
            "nums = list(range(5))\n"
            "evens = list(filter(lambda x: x % 2 == 0, nums))\n"
            "doubled = list(map(lambda x: x * 2, evens))\n"
            "output({'sum': sum(doubled), 'max': max(doubled)})\n"
        )
        r = _run_in_sandbox(_c(script), self._session(), deadline=_FAR)
        assert r.success is True
        assert r.output == [{"sum": 12, "max": 8}]

    def test_builtins_mutation_does_not_leak_to_next_call(self):
        """A script mutating __builtins__ must not affect any later call."""
        mutate = "__builtins__['len'] = lambda x: 999\ndel __builtins__['sorted']\noutput('mutated')"
        r1 = _run_in_sandbox(_c(mutate), self._session(), deadline=_FAR)
        assert r1.success is True

        r2 = _run_in_sandbox(_c("output(len([1, 2, 3]))"), self._session(), deadline=_FAR)
        assert r2.success is True
        assert r2.output == [3]

        r3 = _run_in_sandbox(_c("output(sorted([3, 1, 2]))"), self._session(), deadline=_FAR)
        assert r3.success is True
        assert r3.output == [[1, 2, 3]]

        assert SAFE_BUILTINS["len"] is len
        assert "sorted" in SAFE_BUILTINS

    def test_session_accessible_in_script(self):
        session = self._session()
        session.find_by_id.return_value.text = "HELLO"
        script = "output(session.find_by_id('wnd[0]/usr/txtFLD').text)"
        r = _run_in_sandbox(_c(script), session, deadline=_FAR)
        assert r.success is True
        assert r.output == ["HELLO"]

    def test_getattr_available_for_dynamic_access(self):
        session = self._session()
        session.SomeProperty = "value"
        r = _run_in_sandbox(_c("output(getattr(session, 'SomeProperty'))"), session, deadline=_FAR)
        assert r.success is True
        assert r.output == ["value"]

    def test_wait_in_sandbox(self):
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            r = _run_in_sandbox(_c("wait(250)\noutput('done')"), self._session(), deadline=_FAR)
        assert r.success is True
        assert r.output == ["done"]
        assert clock.sleeps == [0.25]

    def test_wait_negative_in_sandbox_fails(self):
        r = _run_in_sandbox(_c("wait(-10)"), self._session(), deadline=_FAR)
        assert r.success is False
        assert "ValueError" in r.error
        assert "non-negative" in r.error

    def test_script_can_catch_timeout_error(self):
        clock = _FakeTime()
        script = "try:\n    wait(5000)\nexcept TimeoutError:\n    output('caught')"
        with patch("sapguimcp.tools.script_tools.time", clock):
            r = _run_in_sandbox(_c(script), self._session(), deadline=2.0)
        assert r.success is True
        assert r.output == ["caught"]

    def test_wait_beyond_deadline_fails_without_sleeping(self):
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            r = _run_in_sandbox(_c("output('a')\nwait(5000)\noutput('b')"), self._session(), deadline=2.0)
        assert r.success is False
        assert "TimeoutError" in r.error
        assert r.output == ["a"]
        assert not clock.sleeps

    def test_wait_until_stops_at_sandbox_deadline(self):
        session = self._session()
        session.find_by_id.side_effect = RuntimeError("not found")
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            r = _run_in_sandbox(_c("wait_until('wnd[0]/x', 60000, 100)\noutput('no')"), session, deadline=1.0)
        assert r.success is False
        assert "TimeoutError" in r.error
        assert r.output == []
        assert clock.now == pytest.approx(1.0)

    def test_wait_until_in_sandbox_found(self):
        session = self._session()
        mock_elem = MagicMock()
        mock_elem.text = "Tree loaded"
        session.find_by_id.return_value = mock_elem

        script = "elem = wait_until('wnd[0]/usr/tree', timeout_ms=1000)\noutput(elem.text if elem else None)\n"
        r = _run_in_sandbox(_c(script), session, deadline=_FAR)
        assert r.success is True
        assert r.output == ["Tree loaded"]

    def test_wait_until_in_sandbox_not_found(self):
        session = self._session()
        session.find_by_id.side_effect = Exception("Element not found")

        with patch("sapguimcp.tools.script_tools.time", _FakeTime()):
            script = "elem = wait_until('wnd[0]/usr/tree', 200, 50)\noutput(elem is None)\n"
            r = _run_in_sandbox(_c(script), session, deadline=_FAR)
        assert r.success is True
        assert r.output == [True]

    def test_wait_and_wait_until_inside_function(self):
        session = self._session()
        mock_elem = MagicMock()
        mock_elem.text = "inner"
        session.find_by_id.return_value = mock_elem

        script = "def helper():\n    wait(50)\n    return wait_until('wnd[0]/btn', 100).text\noutput(helper())\n"
        with patch("sapguimcp.tools.script_tools.time", _FakeTime()):
            r = _run_in_sandbox(_c(script), session, deadline=_FAR)
        assert r.success is True
        assert r.output == ["inner"]

    def test_sandbox_helpers_mutation_does_not_leak(self):
        mutate = "wait = lambda x: 999\nwait_until = lambda *a, **kw: 999\noutput('mutated')"
        r1 = _run_in_sandbox(_c(mutate), self._session(), deadline=_FAR)
        assert r1.success is True

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            r2 = _run_in_sandbox(_c("wait(50)\noutput('ok')"), self._session(), deadline=_FAR)
        assert r2.success is True
        assert r2.output == ["ok"]
        assert clock.sleeps == [0.05]


class TestWaitHelpers:
    def test_wait_sleeps(self):
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            _wait(150, _FAR)
        assert clock.sleeps == [0.15]

    def test_wait_negative_ms_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            _wait(-10, _FAR)

    @pytest.mark.parametrize("bad", [float("inf"), float("nan")])
    def test_wait_non_finite_raises(self, bad):
        with pytest.raises(ValueError, match="finite"):
            _wait(bad, _FAR)

    @pytest.mark.parametrize("bad", ["10", None, True])
    def test_wait_non_numeric_raises(self, bad):
        with pytest.raises(TypeError, match="must be a number"):
            _wait(bad, _FAR)

    def test_wait_zero_ms(self):
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            _wait(0, _FAR)
        assert clock.sleeps == [0.0]

    def test_wait_exceeding_deadline_raises_without_sleep(self):
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock), pytest.raises(TimeoutError, match="tool timeout"):
            _wait(1001, 1.0)
        assert not clock.sleeps

    def test_wait_exactly_to_deadline_is_allowed(self):
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            _wait(1000, 1.0)
        assert clock.sleeps == [1.0]

    def test_wait_until_immediate_success(self):
        session = MagicMock()
        mock_elem = MagicMock()
        session.find_by_id.return_value = mock_elem

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            elem = _wait_until(session, "wnd[0]/usr/btn", timeout_ms=1000)
        assert elem is mock_elem
        assert not clock.sleeps
        session.find_by_id.assert_called_once_with("wnd[0]/usr/btn", raise_error=False)

    def test_wait_until_subsequent_success_after_exceptions(self):
        session = MagicMock()
        mock_elem = MagicMock()
        session.find_by_id.side_effect = [RuntimeError("not found"), mock_elem]

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            elem = _wait_until(session, "wnd[0]/usr/tree", timeout_ms=1000, poll_ms=100)
        assert elem is mock_elem
        assert session.find_by_id.call_count == 2
        assert clock.sleeps == [0.1]

    def test_wait_until_subsequent_success_after_none(self):
        session = MagicMock()
        mock_elem = MagicMock()
        session.find_by_id.side_effect = [None, mock_elem]

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            elem = _wait_until(session, "wnd[0]/usr/tree", timeout_ms=1000, poll_ms=100)
        assert elem is mock_elem
        assert session.find_by_id.call_count == 2
        assert clock.sleeps == [0.1]

    def test_wait_until_timeout_returns_none(self):
        session = MagicMock()
        session.find_by_id.side_effect = RuntimeError("not found")

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            elem = _wait_until(session, "wnd[0]/usr/tree", timeout_ms=200, poll_ms=50)
        assert elem is None
        assert clock.now == pytest.approx(0.2)

    def test_wait_until_stops_at_sandbox_deadline_and_raises(self):
        session = MagicMock()
        session.find_by_id.return_value = None

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock), pytest.raises(TimeoutError, match="tool timeout"):
            _wait_until(session, "wnd[0]/x", timeout_ms=60000, poll_ms=100, deadline=0.5)
        assert clock.now == pytest.approx(0.5)

    def test_wait_until_own_timeout_before_sandbox_deadline_returns_none(self):
        session = MagicMock()
        session.find_by_id.return_value = None

        with patch("sapguimcp.tools.script_tools.time", _FakeTime()):
            assert _wait_until(session, "wnd[0]/x", timeout_ms=200, poll_ms=50, deadline=10.0) is None

    def test_wait_until_reraises_disconnected(self):
        session = MagicMock()
        exc = OSError("dead")
        exc.hresult = _RPC_E_DISCONNECTED  # type: ignore[attr-defined]
        session.find_by_id.side_effect = exc

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock), pytest.raises(OSError, match="dead"):
            _wait_until(session, "wnd[0]", timeout_ms=1000)
        assert session.find_by_id.call_count == 1
        assert not clock.sleeps

    def test_wait_until_reraises_other_fatal_com_error(self):
        session = MagicMock()
        exc = OSError("stale")
        exc.hresult = _RPC_S_UNKNOWN_IF  # type: ignore[attr-defined]
        session.find_by_id.side_effect = exc

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock), pytest.raises(OSError, match="stale"):
            _wait_until(session, "wnd[0]", timeout_ms=1000)
        assert session.find_by_id.call_count == 1

    def test_wait_until_uses_raise_error_false_and_treats_none_as_not_found(self):
        session = MagicMock()
        session.find_by_id.return_value = None
        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            assert _wait_until(session, "wnd[0]/x", timeout_ms=100, poll_ms=50) is None
        session.find_by_id.assert_called_with("wnd[0]/x", raise_error=False)

    @pytest.mark.parametrize("huge", [10**400, -(10**400)])
    def test_huge_int_raises_value_error(self, huge):
        with pytest.raises(ValueError, match="finite"):
            _wait(huge, _FAR)
        with pytest.raises(ValueError, match="finite"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=huge)
        with pytest.raises(ValueError, match="finite"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=10, poll_ms=huge)

    def test_wait_until_logs_last_error_on_timeout(self, caplog):
        session = MagicMock()
        session.find_by_id.side_effect = RuntimeError("widget missing")

        with patch("sapguimcp.tools.script_tools.time", _FakeTime()), caplog.at_level("DEBUG"):
            assert _wait_until(session, "wnd[0]/x", timeout_ms=100, poll_ms=50) is None
        assert "widget missing" in caplog.text

    def test_wait_until_timeout_zero_found(self):
        session = MagicMock()
        mock_elem = MagicMock()
        session.find_by_id.return_value = mock_elem

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            assert _wait_until(session, "wnd[0]", timeout_ms=0) is mock_elem
        assert not clock.sleeps

    def test_wait_until_timeout_zero_not_found(self):
        session = MagicMock()
        session.find_by_id.return_value = None

        clock = _FakeTime()
        with patch("sapguimcp.tools.script_tools.time", clock):
            assert _wait_until(session, "wnd[0]", timeout_ms=0) is None
        assert not clock.sleeps

    def test_wait_until_negative_timeout_raises(self):
        with pytest.raises(ValueError, match="timeout_ms must be non-negative"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=-1)

    def test_wait_until_invalid_poll_raises(self):
        with pytest.raises(ValueError, match="poll_ms must be greater than 0"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=1000, poll_ms=0)
        with pytest.raises(ValueError, match="poll_ms must be greater than 0"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=1000, poll_ms=-50)

    @pytest.mark.parametrize("bad", [float("inf"), float("nan")])
    def test_wait_until_non_finite_raises(self, bad):
        with pytest.raises(ValueError, match="finite"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=bad)
        with pytest.raises(ValueError, match="finite"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=10, poll_ms=bad)

    @pytest.mark.parametrize("bad", ["10", None, True])
    def test_wait_until_non_numeric_raises(self, bad):
        with pytest.raises(TypeError, match="must be a number"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=bad)
        with pytest.raises(TypeError, match="must be a number"):
            _wait_until(MagicMock(), "wnd[0]", timeout_ms=10, poll_ms=bad)


class TestSapRunScriptTool:
    def _make_tool_fn(self, mcp: FastMCP):
        # FastMCP >= 3.x stores registered tools in _local_provider._components under a key of
        # the form "tool:<name>@".  There is no public API for extracting the underlying async
        # function, so we reach into the private structure here.  If FastMCP changes its internal
        # layout this will raise KeyError/AttributeError and the tests below will fail clearly.
        return mcp._local_provider._components["tool:sap_run_script@"].fn

    def test_non_desktop_backend_returns_failure(self):
        mock_backend = MagicMock()
        mock_backend.backend_type = "webgui"

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        with patch(
            "sapguimcp.tools.script_tools.get_backend",
            new_callable=AsyncMock,
            return_value=mock_backend,
        ):
            result = asyncio.run(tool_fn(script="output(1)", session=None, agent_id=None))

        assert result.success is False
        assert "desktop" in result.error.lower()

    def test_get_backend_value_error_returns_failure(self):
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        with patch(
            "sapguimcp.tools.script_tools.get_backend",
            new_callable=AsyncMock,
            side_effect=ValueError("No session configured"),
        ):
            result = asyncio.run(tool_fn(script="output(1)", session=None, agent_id=None))

        assert result.success is False
        assert "No session" in result.error

    def test_syntax_error_fails_before_backend_lookup(self):
        """Invalid Python is rejected before get_backend is ever called."""
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script="def broken(:", session=None, agent_id=None))

        assert result.success is False
        assert result.error.startswith("SyntaxError")
        mock_get_backend.assert_not_called()

    def test_null_bytes_fail_before_backend_lookup(self):
        """Null bytes in source raise SyntaxError before get_backend is called."""
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script="x = \x00", session=None, agent_id=None))

        assert result.success is False
        assert result.error.startswith("SyntaxError")
        mock_get_backend.assert_not_called()

    def test_timeout_returns_structured_failure(self):
        """asyncio.TimeoutError from com.run is converted to a structured failure."""
        from sapguimcp.backend.desktop import DesktopBackend

        mock_backend = MagicMock()
        mock_backend.__class__ = DesktopBackend  # lets isinstance() pass
        mock_backend.backend_type = "desktop"
        mock_backend.com.run = AsyncMock(side_effect=asyncio.TimeoutError)

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        with patch(
            "sapguimcp.tools.script_tools.get_backend",
            new_callable=AsyncMock,
            return_value=mock_backend,
        ):
            result = asyncio.run(tool_fn(script="output(1)", session=None, agent_id=None, timeout=1))

        assert result.success is False
        assert "timed out" in result.error
        assert "1s" in result.error

    def test_deadline_is_submit_time_plus_timeout(self):
        """The sandbox deadline is computed before queueing, on the same clock as wait_for."""
        from sapguimcp.backend.desktop import DesktopBackend

        mock_backend = MagicMock()
        mock_backend.__class__ = DesktopBackend
        mock_backend.backend_type = "desktop"

        async def fake_run(fn):
            clock.now += 7.0  # time spent queued before the COM thread picks the job up
            return fn()

        mock_backend.com.run = fake_run
        clock = _FakeTime()
        clock.now = 100.0
        captured: dict = {}

        def fake_sandbox(_code, _session, **kwargs):
            captured.update(kwargs)
            return SapRunScriptResult(output=[])

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        with (
            patch("sapguimcp.tools.script_tools.get_backend", new_callable=AsyncMock, return_value=mock_backend),
            patch("sapguimcp.tools.script_tools._run_in_sandbox", fake_sandbox),
            patch("sapguimcp.tools.script_tools.time", clock),
        ):
            result = asyncio.run(tool_fn(script="output(1)", session=None, agent_id=None, timeout=30))

        assert result.success is True
        assert captured == {"deadline": 130.0}
