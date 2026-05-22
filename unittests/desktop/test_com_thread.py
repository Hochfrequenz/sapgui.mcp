# unittests/desktop/test_com_thread.py
"""Tests for _ComThread — dedicated COM worker thread."""

import asyncio

import pytest

from sapguimcp.backend.desktop._com_thread import ComThread


@pytest.fixture
def com_thread():
    """Create a ComThread for testing (no real COM — just the threading mechanism)."""
    thread = ComThread(init_com=False, min_interval_ms=0)  # skip CoInitialize + throttle for unit tests
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
    async def test_rpc_unknown_if_is_retried(self, com_thread):
        """RPC_S_UNKNOWN_IF (-2147023179 / 0x800706B5) should be retried, not fatal."""

        class FakeComError(Exception):
            def __init__(self, hr):
                super().__init__(hr)
                self.hresult = hr

        call_count = 0

        def fail_once_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise FakeComError(-2147023179)  # RPC_S_UNKNOWN_IF
            return "recovered"

        result = await com_thread.run(fail_once_then_succeed)
        assert result == "recovered"
        assert call_count == 2, f"Expected 2 calls (1 failure + 1 retry), got {call_count}"

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
            assert elapsed < 0.5, f"Expected <500ms, got {elapsed*1000:.0f}ms"
        finally:
            thread.shutdown()

    def test_shutdown(self):
        thread = ComThread(init_com=False)
        assert thread._thread.is_alive()
        thread.shutdown()
        assert not thread._thread.is_alive()

    def test_is_alive_property(self):
        """Public is_alive property tracks worker thread liveness."""
        thread = ComThread(init_com=False)
        assert thread.is_alive is True
        thread.shutdown()
        assert thread.is_alive is False

    @pytest.mark.anyio
    async def test_run_after_shutdown_raises_neutral_message(self):
        """Dead-worker error must not lie about sap_login being a fix.

        Regression for issue #628: the previous message told users to
        "call sap_login to reconnect", but the dead ComThread instance
        cannot be revived in place — only BackendManager can rebuild it.
        """
        thread = ComThread(init_com=False)
        thread.shutdown()
        assert not thread.is_alive
        with pytest.raises(RuntimeError, match="cannot be revived") as exc_info:
            await thread.run(lambda: 42)
        # The old, misleading guidance must be gone.
        assert "call sap_login" not in str(exc_info.value)
