# unittests/desktop/test_com_thread.py
"""Tests for _ComThread — dedicated COM worker thread."""

import asyncio

import pytest

from sapwebguimcp.backend.desktop._com_thread import ComThread


@pytest.fixture
def com_thread():
    """Create a ComThread for testing (no real COM — just the threading mechanism)."""
    thread = ComThread(init_com=False)  # skip CoInitialize for unit tests
    yield thread
    thread.shutdown()


class TestComThread:
    @pytest.mark.anyio
    async def test_run_returns_result(self, com_thread):
        result = await com_thread.run(lambda: 42)
        assert result == 42

    @pytest.mark.anyio
    async def test_run_returns_string(self, com_thread):
        result = await com_thread.run(lambda: "hello")
        assert result == "hello"

    @pytest.mark.anyio
    async def test_run_propagates_exception(self, com_thread):
        def failing():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await com_thread.run(failing)

    @pytest.mark.anyio
    async def test_run_preserves_exception_type(self, com_thread):
        def failing():
            raise KeyError("missing")

        with pytest.raises(KeyError):
            await com_thread.run(failing)

    @pytest.mark.anyio
    async def test_multiple_calls_sequential(self, com_thread):
        results = []
        for i in range(5):
            r = await com_thread.run(lambda i=i: i * 2)
            results.append(r)
        assert results == [0, 2, 4, 6, 8]

    @pytest.mark.anyio
    async def test_all_calls_same_thread(self, com_thread):
        """All COM calls must run on the same thread."""
        import threading

        ids = []
        for _ in range(3):
            tid = await com_thread.run(lambda: threading.current_thread().ident)
            ids.append(tid)
        assert len(set(ids)) == 1, "All calls should be on the same thread"
        assert ids[0] != threading.current_thread().ident, "Should be a different thread"

    @pytest.mark.anyio
    async def test_rpc_disconnected_wraps_with_cause(self, com_thread):
        """RPC_E_DISCONNECTED (-2147417848) is wrapped with actionable message."""

        class FakeComError(Exception):
            def __init__(self, hr):
                super().__init__(hr)
                self.hresult = hr

        def disconnected():
            raise FakeComError(-2147417848)

        with pytest.raises(RuntimeError, match="COM connection lost") as exc_info:
            await com_thread.run(disconnected)
        assert isinstance(exc_info.value.__cause__, FakeComError)

    @pytest.mark.anyio
    async def test_other_exceptions_not_wrapped(self, com_thread):
        """Non-disconnect exceptions propagate unchanged."""

        def fail():
            raise KeyError("some_key")

        with pytest.raises(KeyError, match="some_key"):
            await com_thread.run(fail)

    @pytest.mark.anyio
    async def test_rate_limiting_enforces_min_interval(self):
        """Rapid calls are throttled by min_interval_ms."""
        import time

        thread = ComThread(init_com=False, min_interval_ms=100)
        try:
            start = time.monotonic()
            for _ in range(5):
                await thread.run(lambda: None)
            elapsed = time.monotonic() - start
            # 5 calls with 100ms interval → at least 400ms total (first call is immediate)
            assert elapsed >= 0.35, f"Expected ≥350ms, got {elapsed*1000:.0f}ms"
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_rate_limiting_disabled_with_zero(self):
        """min_interval_ms=0 disables rate limiting."""
        import time

        thread = ComThread(init_com=False, min_interval_ms=0)
        try:
            start = time.monotonic()
            for _ in range(10):
                await thread.run(lambda: None)
            elapsed = time.monotonic() - start
            # 10 calls with no throttle should be very fast
            assert elapsed < 0.1, f"Expected <100ms, got {elapsed*1000:.0f}ms"
        finally:
            thread.shutdown()

    def test_shutdown(self):
        thread = ComThread(init_com=False)
        assert thread._thread.is_alive()
        thread.shutdown()
        assert not thread._thread.is_alive()
