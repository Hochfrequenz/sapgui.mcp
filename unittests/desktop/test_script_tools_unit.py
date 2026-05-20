"""Unit tests for sap_run_script — no live SAP required."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from sapwebguimcp.backend.desktop.models.script_results import SapRunScriptResult
from sapwebguimcp.tools.script_tools import _run_in_sandbox, register_script_tools


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
        r = _run_in_sandbox("output(42)", self._session())
        assert r.success is True
        assert r.output == [42]
        assert r.error is None

    def test_multiple_outputs_collected_in_order(self):
        script = "output(1)\noutput(2)\noutput(3)"
        r = _run_in_sandbox(script, self._session())
        assert r.output == [1, 2, 3]

    def test_empty_script_succeeds_with_no_output(self):
        r = _run_in_sandbox("", self._session())
        assert r.success is True
        assert r.output == []

    def test_import_raises_name_error_not_import_error(self):
        r = _run_in_sandbox("import os", self._session())
        assert r.success is False
        assert r.error is not None
        assert r.error.startswith("NameError")

    def test_print_raises_name_error(self):
        r = _run_in_sandbox("print('hi')", self._session())
        assert r.success is False
        assert r.error is not None
        assert "NameError" in r.error

    def test_syntax_error_returns_failure(self):
        r = _run_in_sandbox("def broken(:", self._session())
        assert r.success is False
        assert r.error is not None
        assert r.error.startswith("SyntaxError")
        assert r.error_traceback is not None

    def test_runtime_exception_returns_failure(self):
        r = _run_in_sandbox("raise ValueError('boom')", self._session())
        assert r.success is False
        assert r.error == "ValueError: boom"
        assert r.error_traceback is not None
        assert "ValueError" in r.error_traceback

    def test_partial_output_preserved_on_exception(self):
        script = "output('first')\noutput('second')\nraise KeyError('col')"
        r = _run_in_sandbox(script, self._session())
        assert r.success is False
        assert r.output == ["first", "second"]
        assert "KeyError" in r.error

    def test_non_serializable_output_coerced_to_str(self):
        # Pass a MagicMock (not JSON-serializable) — should become its str()
        script = "output(session)"  # session is a MagicMock
        session = self._session()
        r = _run_in_sandbox(script, session)
        assert r.success is True
        assert len(r.output) == 1
        assert isinstance(r.output[0], str)

    def test_loops_and_conditionals_work(self):
        script = (
            "result = []\n"
            "for i in range(5):\n"
            "    if i % 2 == 0:\n"
            "        result.append(i)\n"
            "output(result)\n"
        )
        r = _run_in_sandbox(script, self._session())
        assert r.success is True
        assert r.output == [[0, 2, 4]]

    def test_safe_builtins_available(self):
        script = (
            "nums = list(range(5))\n"
            "evens = list(filter(lambda x: x % 2 == 0, nums))\n"
            "doubled = list(map(lambda x: x * 2, evens))\n"
            "output({'sum': sum(doubled), 'max': max(doubled)})\n"
        )
        r = _run_in_sandbox(script, self._session())
        assert r.success is True
        assert r.output == [{"sum": 12, "max": 8}]

    def test_session_accessible_in_script(self):
        session = self._session()
        session.find_by_id.return_value.text = "HELLO"
        script = "output(session.find_by_id('wnd[0]/usr/txtFLD').text)"
        r = _run_in_sandbox(script, session)
        assert r.success is True
        assert r.output == ["HELLO"]

    def test_null_bytes_in_script_return_failure(self):
        r = _run_in_sandbox("x = \x00", self._session())
        assert r.success is False
        # compile() raises SyntaxError for null bytes in Python 3
        assert r.error is not None
        assert r.error.startswith("SyntaxError")


class TestSapRunScriptTool:
    def _make_tool_fn(self, mcp: FastMCP):
        # FastMCP >= 3.x stores tools in _local_provider._components keyed as "tool:<name>@"
        return mcp._local_provider._components["tool:sap_run_script@"].fn

    def test_non_desktop_backend_returns_failure(self):
        mock_backend = MagicMock()
        mock_backend.backend_type = "webgui"

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        with patch(
            "sapwebguimcp.tools.script_tools.get_backend",
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
            "sapwebguimcp.tools.script_tools.get_backend",
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
        with patch("sapwebguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script="def broken(:", session=None, agent_id=None))

        assert result.success is False
        assert result.error.startswith("SyntaxError")
        mock_get_backend.assert_not_called()
