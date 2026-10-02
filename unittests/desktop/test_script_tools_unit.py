"""Unit tests for sap_run_script — no live SAP required."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

import sapguimcp.models.config as config_module
from sapguimcp.backend.desktop._com_thread import _RPC_E_DISCONNECTED, _RPC_S_UNKNOWN_IF

if TYPE_CHECKING:
    from pathlib import Path

from sapguimcp.backend.desktop.models.script_results import SapRunScriptResult
from sapguimcp.resources.sandbox_resource import register_sandbox_resources
from sapguimcp.tools.script_tools import (
    MAX_SCRIPT_BYTES,
    SAFE_BUILTINS,
    SANDBOX_CONTRACT_VERSION,
    _build_sandbox_globals,
    _merge_params,
    _resolve_and_validate_script_path,
    _run_in_sandbox,
    _wait,
    _wait_until,
    get_configured_script_roots,
    get_sandbox_contract,
    register_script_tools,
)
from sapguimcp.utils import is_path_within_root

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


def _set_script_roots(monkeypatch: pytest.MonkeyPatch, value: str | None) -> None:
    """Point the SCRIPT_ROOTS setting at *value* with a fresh settings singleton (restored afterwards)."""
    monkeypatch.setattr(config_module, "_settings", None)
    if value is None:
        monkeypatch.delenv("SCRIPT_ROOTS", raising=False)
    else:
        monkeypatch.setenv("SCRIPT_ROOTS", value)


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

    def test_result_with_script_path_and_sha256(self):
        r = SapRunScriptResult(
            output=["ok"],
            script_path="/path/to/script.py",
            script_sha256="abc123def456",
        )
        assert r.success is True
        assert r.script_path == "/path/to/script.py"
        assert r.script_sha256 == "abc123def456"

        f = SapRunScriptResult.failure(
            "SyntaxError: invalid syntax",
            script_path="/path/to/script.py",
            script_sha256="abc123def456",
        )
        assert f.success is False
        assert f.script_path == "/path/to/script.py"
        assert f.script_sha256 == "abc123def456"


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


class TestScriptPathValidation:
    def test_get_configured_script_roots_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        r1 = tmp_path / "root1"
        r2 = tmp_path / "root2"
        _set_script_roots(monkeypatch, f"{r1}{os.pathsep}{r2}")
        roots = get_configured_script_roots()
        assert roots == [r1, r2]

    def test_get_configured_script_roots_empty(self, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, "")
        assert get_configured_script_roots() == []

    def test_get_configured_script_roots_empty_entries(self, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, os.pathsep * 2)
        assert get_configured_script_roots() == []

    def test_get_configured_script_roots_quotes_and_whitespace(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        _set_script_roots(monkeypatch, f' "{a}" {os.pathsep} {b} ')
        assert get_configured_script_roots() == [a, b]

    def test_get_configured_script_roots_skips_relative(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        good = tmp_path / "good"
        _set_script_roots(monkeypatch, f"relative_dir{os.pathsep}{good}")
        with caplog.at_level(logging.WARNING, logger="sapguimcp.tools.script_tools"):
            roots = get_configured_script_roots()
        assert roots == [good]
        assert "must be absolute" in caplog.text

    @pytest.mark.skipif(sys.platform != "win32", reason="drive-relative paths are Windows-only")
    def test_get_configured_script_roots_skips_bare_drive(self, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, "C:")
        assert get_configured_script_roots() == []

    @pytest.mark.skipif(sys.platform != "win32", reason="drive-relative paths are Windows-only")
    def test_drive_relative_script_path_not_outside_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "root"
        root.mkdir()
        # "C:evil.py" is relative to the cwd of drive C: - put a matching file there so a
        # resolution against the cwd would find it.
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "evil.py").write_text("output(1)")
        monkeypatch.chdir(outside)
        try:
            resolved = _resolve_and_validate_script_path("C:evil.py", [root])
        except ValueError:
            return
        assert is_path_within_root(resolved, root)

    @pytest.mark.parametrize("prefix", ["\\\\?\\", "\\\\.\\"])
    def test_device_prefix_script_path_rejected(self, tmp_path: Path, prefix: str):
        with pytest.raises(ValueError, match="UNC and device paths are not allowed"):
            _resolve_and_validate_script_path(prefix + "C:\\x\\script.py", [tmp_path])

    def test_symlink_to_non_py_target_rejected(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        real = root / "x.txt"
        real.write_text("output(1)")
        link = root / "link.py"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"cannot create symlinks here: {exc}")
        with pytest.raises(ValueError, match=re.escape("target must have a .py extension")):
            _resolve_and_validate_script_path(str(link), [root])

    def test_is_path_within_root(self, tmp_path: Path):
        child = tmp_path / "sub" / "file.py"
        assert is_path_within_root(child, tmp_path) is True
        outside = tmp_path.parent / "other.py"
        assert is_path_within_root(outside, tmp_path) is False

    def test_resolve_and_validate_script_path_success(self, tmp_path: Path):
        script_file = tmp_path / "test.py"
        script_file.write_text("output(1)")
        resolved = _resolve_and_validate_script_path(str(script_file), [tmp_path])
        assert resolved == script_file.resolve()

    def test_resolve_and_validate_script_path_relative(self, tmp_path: Path):
        script_file = tmp_path / "test.py"
        script_file.write_text("output(1)")
        resolved = _resolve_and_validate_script_path("test.py", [tmp_path])
        assert resolved == script_file.resolve()

    def test_resolve_and_validate_script_path_no_roots(self, tmp_path: Path):
        script_file = tmp_path / "test.py"
        script_file.write_text("output(1)")
        with pytest.raises(ValueError, match="script_path is disabled: no script roots configured"):
            _resolve_and_validate_script_path(str(script_file), [])

    def test_resolve_and_validate_script_path_outside_roots(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        outside_file = tmp_path / "outside.py"
        outside_file.write_text("output(1)")
        with pytest.raises(ValueError, match="is not within any configured script root"):
            _resolve_and_validate_script_path(str(outside_file), [root])

    def test_resolve_and_validate_script_path_traversal(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        outside_file = tmp_path / "outside.py"
        outside_file.write_text("output(1)")
        traversal_path = str(root / ".." / "outside.py")
        with pytest.raises(ValueError, match="is not within any configured script root"):
            _resolve_and_validate_script_path(traversal_path, [root])

    def test_resolve_and_validate_script_path_not_found(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.py"
        with pytest.raises(ValueError, match="Script file not found"):
            _resolve_and_validate_script_path(str(missing), [tmp_path])

    def test_resolve_and_validate_script_path_is_dir(self, tmp_path: Path):
        sub_dir = tmp_path / "subdir.py"
        sub_dir.mkdir()
        with pytest.raises(ValueError, match="is a directory, not a file"):
            _resolve_and_validate_script_path(str(sub_dir), [tmp_path])

    def test_resolve_and_validate_script_path_non_py(self, tmp_path: Path):
        txt_file = tmp_path / "script.txt"
        txt_file.write_text("print(1)")
        with pytest.raises(ValueError, match=re.escape("must have a .py extension")):
            _resolve_and_validate_script_path(str(txt_file), [tmp_path])

    def test_resolve_and_validate_script_path_unc(self, tmp_path: Path):
        with pytest.raises(ValueError, match="UNC and device paths are not allowed"):
            _resolve_and_validate_script_path(r"\\server\share\script.py", [tmp_path])

    def test_relative_path_resolves_against_root_not_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "root"
        root.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        (root / "same.py").write_text("output('root')")
        (other / "same.py").write_text("output('cwd')")
        monkeypatch.chdir(other)
        resolved = _resolve_and_validate_script_path("same.py", [root])
        assert resolved == (root / "same.py").resolve()

    def test_relative_path_cwd_file_outside_roots_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "root"
        root.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        (other / "only_cwd.py").write_text("output(1)")
        monkeypatch.chdir(other)
        with pytest.raises(ValueError, match="Script file not found"):
            _resolve_and_validate_script_path("only_cwd.py", [root])

    def test_relative_path_first_matching_root_wins(self, tmp_path: Path):
        r1 = tmp_path / "r1"
        r2 = tmp_path / "r2"
        r1.mkdir()
        r2.mkdir()
        (r2 / "a.py").write_text("output(2)")
        assert _resolve_and_validate_script_path("a.py", [r1, r2]) == (r2 / "a.py").resolve()
        (r1 / "a.py").write_text("output(1)")
        assert _resolve_and_validate_script_path("a.py", [r1, r2]) == (r1 / "a.py").resolve()

    def test_symlink_escape_rejected(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "evil.py").write_text("output(1)")
        link = root / "link.py"
        try:
            link.symlink_to(outside / "evil.py")
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"cannot create symlinks here: {exc}")
        with pytest.raises(ValueError, match="is not within any configured script root"):
            _resolve_and_validate_script_path(str(link), [root])

    def test_symlinked_dir_escape_rejected_relative(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "evil.py").write_text("output(1)")
        try:
            (root / "sub").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"cannot create symlinks here: {exc}")
        with pytest.raises(ValueError, match="is not within any configured script root"):
            _resolve_and_validate_script_path("sub/evil.py", [root])

    def test_symlink_inside_root_allowed(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        real = root / "real.py"
        real.write_text("output(1)")
        link = root / "link.py"
        try:
            link.symlink_to(real)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"cannot create symlinks here: {exc}")
        assert _resolve_and_validate_script_path(str(link), [root]) == real.resolve()

    @pytest.mark.skipif(sys.platform != "win32", reason="NTFS junctions are Windows-only")
    def test_junction_escape_rejected(self, tmp_path: Path):
        root = tmp_path / "allowed"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "evil.py").write_text("output(1)")
        junction = root / "jct"
        proc = subprocess.run(  # noqa: S603
            ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.skip(f"cannot create junction: {proc.stderr or proc.stdout}")
        try:
            with pytest.raises(ValueError, match="is not within any configured script root"):
                _resolve_and_validate_script_path(str(junction / "evil.py"), [root])
        finally:
            junction.rmdir()  # removes the junction only, not the target

    @pytest.mark.parametrize("name", ["CON.py", "nul.py", "sub/COM1.py"])
    def test_reserved_device_name_rejected(self, tmp_path: Path, name: str):
        with pytest.raises(ValueError, match="Invalid or reserved Windows file name"):
            _resolve_and_validate_script_path(name, [tmp_path])

    @pytest.mark.skipif(sys.platform != "win32", reason="alternate data streams are Windows-only")
    def test_alternate_data_stream_rejected(self, tmp_path: Path):
        (tmp_path / "ok.txt").write_text("x")
        with pytest.raises(ValueError, match="Alternate data streams"):
            _resolve_and_validate_script_path("ok.txt:x.py", [tmp_path])
        with pytest.raises(ValueError, match="Alternate data streams"):
            _resolve_and_validate_script_path(str(tmp_path / "ok.txt:x.py"), [tmp_path])


class TestScriptPathTimeoutReporting:
    def test_timeout_error_reported_with_script_path(self):
        r = _run_in_sandbox(_c("raise TimeoutError('t')"), object(), "x.py", "abc", deadline=math.inf)
        assert r.success is False
        assert "TimeoutError" in r.error
        assert r.script_path == "x.py"
        assert r.script_sha256 == "abc"


class TestMergeParams:
    def test_merge_params_success(self):
        source = "PARAMS = {'limit': 10, 'name': 'default'}\noutput(PARAMS)"
        tree = ast.parse(source)
        _merge_params(tree, {"limit": 20, "name": "custom"})
        code = compile(tree, "<test>", "exec")
        sandbox_result = _run_in_sandbox(code, MagicMock(), deadline=_FAR)
        assert sandbox_result.output == [{"limit": 20, "name": "custom"}]

    def test_merge_params_annotated(self):
        source = "PARAMS: dict[str, int] = {'count': 1}\noutput(PARAMS['count'])"
        tree = ast.parse(source)
        _merge_params(tree, {"count": 42})
        code = compile(tree, "<test>", "exec")
        sandbox_result = _run_in_sandbox(code, MagicMock(), deadline=_FAR)
        assert sandbox_result.output == [42]

    def test_merge_params_unknown_key_raises(self):
        source = "PARAMS = {'a': 1}\n"
        tree = ast.parse(source)
        with pytest.raises(ValueError, match=re.escape("Unknown params: 'b'. Valid keys are: 'a'")):
            _merge_params(tree, {"b": 2})

    def test_merge_params_no_params_dict_raises(self):
        source = "x = 1\noutput(x)\n"
        tree = ast.parse(source)
        with pytest.raises(ValueError, match="Script does not define a top-level 'PARAMS' dict"):
            _merge_params(tree, {"a": 1})

    def test_merge_params_non_dict_params_raises(self):
        source = "PARAMS = 123\n"
        tree = ast.parse(source)
        with pytest.raises(ValueError, match="Top-level 'PARAMS' must be a dict literal"):
            _merge_params(tree, {"a": 1})

    def test_merge_params_multiple_params_raises(self):
        source = "PARAMS = {'a': 1}\nPARAMS = {'a': 2}\n"
        tree = ast.parse(source)
        with pytest.raises(ValueError, match="Multiple top-level 'PARAMS' assignments"):
            _merge_params(tree, {"a": 3})

    @pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
    def test_merge_params_non_finite_float_rejected(self, bad: float):
        tree = ast.parse("PARAMS = {'a': 1}\n")
        with pytest.raises(ValueError, match="Non-finite float"):
            _merge_params(tree, {"a": bad})

    def test_merge_params_nested_values(self):
        tree = ast.parse("PARAMS = {'a': 1}\noutput(PARAMS)\n")
        value = {"x": [1, -2.5, None, True, "s"], "y": {"z": "w"}}
        _merge_params(tree, {"a": value})
        sandbox_result = _run_in_sandbox(compile(tree, "<test>", "exec"), MagicMock(), deadline=_FAR)
        assert sandbox_result.output == [{"a": value}]

    def test_merge_params_deep_nesting_rejected(self):
        tree = ast.parse("PARAMS = {'a': 1}\n")
        deep: list = []
        for _ in range(100_000):
            deep = [deep]
        with pytest.raises(ValueError, match="nested too deeply"):
            _merge_params(tree, {"a": deep})

    def test_merge_params_unsupported_type_rejected(self):
        tree = ast.parse("PARAMS = {'a': 1}\n")
        with pytest.raises(ValueError, match="Unsupported params value type"):
            _merge_params(tree, {"a": {1, 2}})


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
        assert captured == {"script_path": None, "script_sha256": None, "deadline": 130.0}

    def test_mutually_exclusive_neither_script_nor_path(self):
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)
        result = asyncio.run(tool_fn(script=None, script_path=None))
        assert result.success is False
        assert "Exactly one of 'script' or 'script_path' must be provided" in result.error

    def test_mutually_exclusive_both_script_and_path(self):
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)
        result = asyncio.run(tool_fn(script="output(1)", script_path="/path/test.py"))
        assert result.success is False
        assert "Cannot specify both 'script' and 'script_path'" in result.error

    def test_expected_sha256_with_inline_script_rejected(self):
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)
        result = asyncio.run(tool_fn(script="output(1)", expected_sha256="abc123"))
        assert result.success is False
        assert "'expected_sha256' is only valid with 'script_path'" in result.error

    def test_script_path_disabled_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, None)

        script_file = tmp_path / "test.py"
        script_file.write_text("output(1)")

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script_path=str(script_file)))

        assert result.success is False
        assert "script_path is disabled: no script roots configured" in result.error
        mock_get_backend.assert_not_called()

    def test_script_path_outside_roots_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "allowed"
        root.mkdir()
        _set_script_roots(monkeypatch, str(root))
        outside_file = tmp_path / "outside.py"
        outside_file.write_text("output(1)")

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script_path=str(outside_file)))

        assert result.success is False
        assert "is not within any configured script root" in result.error
        mock_get_backend.assert_not_called()

    def test_script_path_sha256_mismatch_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, str(tmp_path))
        script_file = tmp_path / "test.py"
        script_file.write_text("output(1)")

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(
                tool_fn(
                    script_path=str(script_file),
                    expected_sha256="0000000000000000000000000000000000000000000000000000000000000000",
                )
            )

        assert result.success is False
        assert "SHA-256 mismatch" in result.error
        assert result.script_path == str(script_file.resolve())
        assert result.script_sha256 == hashlib.sha256(script_file.read_bytes()).hexdigest()
        mock_get_backend.assert_not_called()

    @pytest.mark.parametrize("exc", [RuntimeError("Symlink loop"), OSError("boom")])
    def test_script_path_resolution_error_returns_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
    ):
        _set_script_roots(monkeypatch, str(tmp_path))

        def raiser(*_args: object, **_kwargs: object):
            raise exc

        monkeypatch.setattr("sapguimcp.tools.script_tools._resolve_and_validate_script_path", raiser)
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)
        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script_path=str(tmp_path / "x.py")))
        assert result.success is False
        assert "Cannot resolve script_path" in result.error
        mock_get_backend.assert_not_called()

    def test_script_path_unknown_params_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, str(tmp_path))
        script_file = tmp_path / "test.py"
        script_file.write_text("PARAMS = {'known': 1}\noutput(PARAMS)")

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(
                tool_fn(
                    script_path=str(script_file),
                    params={"unknown_key": 99},
                )
            )

        assert result.success is False
        assert "Unknown params: 'unknown_key'" in result.error
        mock_get_backend.assert_not_called()

    def test_script_path_and_params_execution_matches_inline(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        from sapguimcp.backend.desktop import DesktopBackend

        _set_script_roots(monkeypatch, str(tmp_path))
        script_file = tmp_path / "my_script.py"
        script_content = (
            "PARAMS = {'batch_size': 5, 'prefix': 'DEFAULT'}\n"
            "output({'batch': PARAMS['batch_size'], 'prefix': PARAMS['prefix']})\n"
        )
        script_file.write_text(script_content, encoding="utf-8-sig")
        expected_hash = hashlib.sha256(script_file.read_bytes()).hexdigest()

        mock_session = MagicMock()
        mock_backend = MagicMock()
        mock_backend.__class__ = DesktopBackend  # lets isinstance() pass
        mock_backend.backend_type = "desktop"
        mock_backend.require_session.return_value = mock_session

        async def fake_com_run(fn):
            return fn()

        mock_backend.com.run = AsyncMock(side_effect=fake_com_run)

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        with patch("sapguimcp.tools.script_tools.get_backend", new_callable=AsyncMock, return_value=mock_backend):
            result = asyncio.run(
                tool_fn(
                    script_path=str(script_file),
                    params={"batch_size": 25, "prefix": "CUSTOM"},
                    expected_sha256=expected_hash,
                )
            )

        assert result.success is True
        assert result.output == [{"batch": 25, "prefix": "CUSTOM"}]
        assert result.script_path == str(script_file.resolve())
        assert result.script_sha256 == expected_hash

        # Run same logic as inline script to verify identical output
        inline_script = (
            "PARAMS = {'batch_size': 25, 'prefix': 'CUSTOM'}\n"
            "output({'batch': PARAMS['batch_size'], 'prefix': PARAMS['prefix']})\n"
        )
        with patch("sapguimcp.tools.script_tools.get_backend", new_callable=AsyncMock, return_value=mock_backend):
            inline_result = asyncio.run(tool_fn(script=inline_script))

        assert inline_result.success is True
        assert inline_result.output == result.output
        assert inline_result.script_path is None
        assert inline_result.script_sha256 is None

    def test_params_with_inline_script_rejected(self):
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)
        result = asyncio.run(tool_fn(script="PARAMS = {'a': 1}", params={"a": 2}))
        assert result.success is False
        assert "'params' is only valid with 'script_path'" in result.error

    def test_script_path_too_large_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        _set_script_roots(monkeypatch, str(tmp_path))
        big = tmp_path / "big.py"
        big.write_bytes(b"#" * (MAX_SCRIPT_BYTES + 1))

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script_path=str(big)))

        assert result.success is False
        assert "exceeds the maximum size" in result.error
        mock_get_backend.assert_not_called()

    def test_script_path_relative_ignores_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "root"
        root.mkdir()
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()
        (cwd_dir / "only_here.py").write_text("output(1)")
        monkeypatch.chdir(cwd_dir)
        _set_script_roots(monkeypatch, str(root))

        mcp = FastMCP("test")
        register_script_tools(mcp)
        tool_fn = self._make_tool_fn(mcp)

        mock_get_backend = AsyncMock()
        with patch("sapguimcp.tools.script_tools.get_backend", mock_get_backend):
            result = asyncio.run(tool_fn(script_path="only_here.py"))

        assert result.success is False
        assert "Script file not found" in result.error
        mock_get_backend.assert_not_called()


class TestSandboxContract:
    def test_version(self):
        assert SANDBOX_CONTRACT_VERSION == 2
        assert get_sandbox_contract().version == 2
        # Pin the exact sorted list of allowed builtins.
        # Changing the sandbox requires bumping SANDBOX_CONTRACT_VERSION and updating this list.
        expected_builtins = [
            "AttributeError",
            "Exception",
            "IndexError",
            "KeyError",
            "NotImplementedError",
            "RuntimeError",
            "StopIteration",
            "TimeoutError",
            "TypeError",
            "ValueError",
            "abs",
            "all",
            "any",
            "bool",
            "dict",
            "enumerate",
            "filter",
            "float",
            "getattr",
            "int",
            "isinstance",
            "len",
            "list",
            "map",
            "max",
            "min",
            "range",
            "reversed",
            "round",
            "set",
            "sorted",
            "str",
            "sum",
            "tuple",
            "zip",
        ]
        assert get_sandbox_contract().allowed_builtins == expected_builtins

    def test_allowed_builtins_content(self):
        contract = get_sandbox_contract()
        assert isinstance(contract.allowed_builtins, list)
        expected_subset = {
            "abs",
            "all",
            "any",
            "bool",
            "dict",
            "enumerate",
            "filter",
            "float",
            "getattr",
            "int",
            "isinstance",
            "len",
            "list",
            "map",
            "max",
            "min",
            "range",
            "reversed",
            "round",
            "set",
            "sorted",
            "str",
            "sum",
            "tuple",
            "zip",
            "AttributeError",
            "Exception",
            "IndexError",
            "KeyError",
            "NotImplementedError",
            "RuntimeError",
            "StopIteration",
            "TypeError",
            "ValueError",
        }
        assert expected_subset.issubset(set(contract.allowed_builtins))

        # Should NOT contain internal / private names (starting with _)
        for name in contract.allowed_builtins:
            assert not name.startswith("_"), f"Internal builtin leaked: {name}"
        assert "__import__" not in contract.allowed_builtins

        # Should NOT contain builtins excluded by sandbox design
        missing_builtins = ["print", "ord", "divmod", "open", "eval", "exec", "globals", "locals"]
        for missing in missing_builtins:
            assert missing not in contract.allowed_builtins

        # Must match SAFE_BUILTINS keys minus private/stub entries
        expected_allowed = sorted(k for k in SAFE_BUILTINS if not k.startswith("_"))
        assert contract.allowed_builtins == expected_allowed

    def test_injected_names(self):
        contract = get_sandbox_contract()
        assert isinstance(contract.injected_names, list)
        assert set(contract.injected_names) == {"output", "session", "wait", "wait_until"}

    def test_injected_names_match_actual_sandbox_globals(self):
        contract = get_sandbox_contract()
        actual = _build_sandbox_globals(object(), lambda _v: None, math.inf)
        assert set(actual) - {"__builtins__"} == set(contract.injected_names)

    def test_exec_receives_globals_matching_contract(self):
        seen: dict = {}
        real_exec = exec

        def spy(code, globals_):
            seen.update(globals_)
            return real_exec(code, globals_)

        with patch("sapguimcp.tools.script_tools.exec", spy, create=True):
            _run_in_sandbox(compile("output(1)", _FILENAME, "exec"), object(), deadline=math.inf)
        assert set(seen) - {"__builtins__"} == set(get_sandbox_contract().injected_names)
        assert set(seen["__builtins__"]) == set(SAFE_BUILTINS)

    def test_sap_run_script_description_includes_sandbox_contract(self):
        mcp = FastMCP("test")
        register_script_tools(mcp)
        tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
        desc = tools["sap_run_script"].description or ""

        assert "Sandbox contract (v2):" in desc
        contract = get_sandbox_contract()
        assert f"- Allowed builtins: {', '.join(contract.allowed_builtins)}\n" in desc
        injected = ", ".join(f"``{n}``" for n in contract.injected_names)
        assert f"- Injected names: {injected} " in desc
        assert "sandbox://sap_run_script" in desc

    def test_sandbox_resource_registration_and_read(self):
        mcp = FastMCP("test")
        register_sandbox_resources(mcp)

        resources = {str(r.uri): r for r in asyncio.run(mcp.list_resources())}
        assert "sandbox://sap_run_script" in resources
        resource = resources["sandbox://sap_run_script"]
        assert resource.mime_type == "application/json"

        # Read resource content
        content = asyncio.run(mcp.read_resource("sandbox://sap_run_script"))
        assert len(content.contents) == 1
        payload = json.loads(content.contents[0].content)

        assert payload == get_sandbox_contract().model_dump()
