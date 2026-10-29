"""Issue #1012: 0x80010105 is RPC_E_SERVERFAULT (never retried), 0x8001010A is RETRYLATER (retried)."""

# pylint: disable=protected-access

import concurrent.futures
from typing import Any

import pytest

from sapguimcp.backend.desktop import _com_thread as mod
from sapguimcp.backend.desktop._com_thread import (
    ComBatchInterruptedError,
    ComThread,
    describe_com_error,
    is_transient_busy_error,
)
from sapguimcp.tools.com_tools import _is_retryable_com_code

SERVERFAULT = -2147417851  # 0x80010105
RETRYLATER = -2147417846  # 0x8001010A
CALL_REJECTED = -2147418111  # 0x80010001
UNKNOWN_IF = -2147023179  # 0x800706B5


class FakeComError(Exception):
    def __init__(self, hr: int) -> None:
        super().__init__(hr)
        self.hresult = hr


@pytest.fixture
def com_thread():
    thread = ComThread(init_com=False, min_interval_ms=0)
    yield thread
    thread.shutdown()


def _run(thread: ComThread, fn: Any, max_retries: int = 3) -> concurrent.futures.Future:
    fut: concurrent.futures.Future = concurrent.futures.Future()
    thread._execute_with_retry(fn, fut, last_call=0.0, max_retries=max_retries)
    return fut


def test_constants_are_pinned_to_the_windows_values() -> None:
    assert mod._RPC_E_SERVERFAULT == SERVERFAULT == 0x80010105 - 2**32
    assert mod._RPC_E_SERVERCALL_RETRYLATER == RETRYLATER == 0x8001010A - 2**32
    assert mod._RPC_E_CALL_REJECTED == CALL_REJECTED
    assert SERVERFAULT not in mod.RETRYABLE_COM_ERRORS
    assert {RETRYLATER, CALL_REJECTED, UNKNOWN_IF} == set(mod.RETRYABLE_COM_ERRORS)
    try:
        import winerror  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        return
    assert winerror.RPC_E_SERVERFAULT == SERVERFAULT
    assert winerror.RPC_E_SERVERCALL_RETRYLATER == RETRYLATER


@pytest.mark.parametrize("code", [RETRYLATER, CALL_REJECTED])
def test_busy_codes_are_retried_with_backoff(com_thread: ComThread, code: int) -> None:
    calls = 0

    def fn() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FakeComError(code)
        return "ok"

    com_thread._current_interval_s = 0.01
    fut = _run(com_thread, fn)
    assert fut.result() == "ok"
    assert calls == 2
    assert com_thread._current_interval_s > 0.01


def test_server_fault_is_called_once_surfaced_and_does_not_inflate_the_interval(com_thread: ComThread) -> None:
    calls = 0

    def fn() -> None:
        nonlocal calls
        calls += 1
        raise FakeComError(SERVERFAULT)

    com_thread._current_interval_s = 0.01
    fut = _run(com_thread, fn)
    with pytest.raises(FakeComError):
        fut.result()
    assert calls == 1
    assert com_thread._current_interval_s <= 0.01
    notes = getattr(fut.exception(), "__notes__", [])
    assert any("stale control proxy" in n and "re-fetch" in n for n in notes)
    assert "re-fetch" in (describe_com_error(FakeComError(SERVERFAULT)) or "")


def test_multi_step_script_is_not_rerun_after_a_server_fault(com_thread: ComThread) -> None:
    """A sap_run_script-style callable: a fault in step 3 must not repeat steps 1-2."""
    steps: list[int] = []

    def script() -> None:
        for step in (1, 2, 3):
            steps.append(step)
            if step == 3:
                raise FakeComError(SERVERFAULT)

    with pytest.raises(FakeComError):
        _run(com_thread, script).result()
    assert steps == [1, 2, 3]


def test_batch_carrier_resumes_on_retrylater_but_not_on_server_fault(com_thread: ComThread) -> None:
    attempts = {"resume": 0, "fault": 0}

    def make(code: int, key: str) -> Any:
        def batch(resume: ComBatchInterruptedError | None = None) -> str:
            attempts[key] += 1
            if resume is None:
                raise ComBatchInterruptedError([], 0, code)
            return "done"

        return batch

    assert _run(com_thread, make(RETRYLATER, "resume")).result() == "done"
    assert attempts["resume"] == 2
    with pytest.raises(ComBatchInterruptedError):
        _run(com_thread, make(SERVERFAULT, "fault")).result()
    assert attempts["fault"] == 1


@pytest.mark.parametrize(
    ("code", "expected"),
    [(RETRYLATER, True), (CALL_REJECTED, True), (SERVERFAULT, False), (UNKNOWN_IF, False)],
)
def test_is_transient_busy_error(code: int, expected: bool) -> None:
    assert is_transient_busy_error(FakeComError(code)) is expected


@pytest.mark.parametrize("code", [RETRYLATER, CALL_REJECTED, UNKNOWN_IF, SERVERFAULT])
def test_com_tools_resumes_only_on_codes_the_thread_retries(code: int) -> None:
    assert _is_retryable_com_code(code) is (code != SERVERFAULT)
