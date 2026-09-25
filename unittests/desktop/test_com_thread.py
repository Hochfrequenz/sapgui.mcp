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
            assert elapsed >= 0.35, f"Expected ≥350ms, got {elapsed * 1000:.0f}ms"
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
            assert elapsed < 0.5, f"Expected <500ms, got {elapsed * 1000:.0f}ms"
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


class _FakeComError(Exception):
    """Stand-in for pywintypes.com_error (unavailable on Linux CI).

    ``com_error`` exposes the HRESULT as ``args[0]``; that's all
    ``_get_com_error_code`` reads.
    """


class TestDescribeComError:
    """#789: known fatal COM errors get an actionable remediation hint."""

    def test_stale_interface_maps_to_relogin_hint(self):
        from sapguimcp.backend.desktop._com_thread import describe_com_error

        exc = _FakeComError(-2147023179, "Die Schnittstelle ist unbekannt.", None, None)
        hint = describe_com_error(exc)
        assert hint is not None
        assert "sap_login" in hint.lower()
        # No raw HRESULT / cryptic German leaks into the friendly message.
        assert "-2147023179" not in hint
        assert "Die Schnittstelle" not in hint

    def test_disconnected_maps_to_hint(self):
        from sapguimcp.backend.desktop._com_thread import describe_com_error

        exc = _FakeComError(-2147417848, "The object invoked has disconnected", None, None)
        assert describe_com_error(exc) is not None

    def test_unknown_code_returns_none(self):
        from sapguimcp.backend.desktop._com_thread import describe_com_error

        assert describe_com_error(_FakeComError(-42, "some other error")) is None

    def test_non_com_exception_returns_none(self):
        from sapguimcp.backend.desktop._com_thread import describe_com_error

        assert describe_com_error(RuntimeError("boom")) is None


class TestWorkerSurvivesCancelledFuture:
    """#789: a caller timing out (asyncio.wait_for) while the worker is still running
    fn() must not crash the COM worker — that would defeat the liveness probes that
    rely on the timeout to survive a slow/wedged COM call. (The worker marks the
    future running before fn(), so it can no longer be cancelled mid-call; the
    done() guards stay as a second line of defence.)"""

    @pytest.mark.anyio
    async def test_timeout_cancellation_does_not_kill_worker(self, com_thread):
        import threading

        release = threading.Event()

        def slow():
            release.wait(2.0)  # block the worker past the caller's timeout
            return "slow-done"

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await asyncio.wait_for(com_thread.run(slow), timeout=0.1)

        # Let the in-flight call complete; it will try to settle a now-cancelled
        # future. Without the guard this raises InvalidStateError in the worker.
        release.set()
        await asyncio.sleep(0.3)

        # The worker must still be alive and usable.
        assert com_thread.is_alive
        assert await com_thread.run(lambda: 42) == 42


class TestHaltedByDebugger:
    """A COM call that triggered ABAP which stopped at a breakpoint blocks until a human
    finishes in the ABAP debugger. The single COM worker must not stay wedged behind it:
    the watchdog cancels the stuck call once a debugger is open in a watched connection."""

    _CANCELLED = -2147418110  # RPC_E_CALL_CANCELED, what CoCancelCall makes the blocked call raise

    def _thread_with_fakes(self, debuggers: dict[str, str], *, cancel_results: list[bool] | None = None):
        """ComThread whose debugger scan and CoCancelCall are fakes.

        ``cancel_results`` lets a test make COM refuse the first cancel requests
        (e.g. the worker was between two calls); afterwards cancels succeed.
        """
        import threading

        thread = ComThread(init_com=False, min_interval_ms=0, halt_check_after_s=0.2)
        cancelled = threading.Event()
        scans: list[int] = []
        pending_results = list(cancel_results or [])

        def fake_scan(*_args) -> dict[str, str]:
            scans.append(1)
            return dict(debuggers)

        def fake_cancel() -> bool:
            if pending_results and not pending_results.pop(0):
                return False
            cancelled.set()
            return True

        thread._list_debugger_sessions = fake_scan  # type: ignore[method-assign]
        thread._cancel_worker_call = fake_cancel  # type: ignore[method-assign]
        thread._debugger_window_open = lambda: bool(debuggers)  # type: ignore[method-assign]
        return thread, cancelled, scans

    def _blocking_call(self, cancelled, *, max_wait: float = 5.0):
        def blocked():
            if cancelled.wait(max_wait):
                raise _FakeComError(self._CANCELLED, "Aufruf wurde durch Messagefilter abgebrochen.", None, None)
            return "completed without cancel"

        return blocked

    @pytest.mark.anyio
    async def test_call_stuck_behind_debugger_is_cancelled(self):
        from sapguimcp.backend.desktop._com_thread import SapSessionHaltedError

        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)  (exklusiv)"})
        thread.watch_connection("/app/con[1]")
        try:
            with pytest.raises(SapSessionHaltedError, match="ABAP Debugger") as exc_info:
                await asyncio.wait_for(thread.run(self._blocking_call(cancelled)), timeout=4.0)
            assert "human" in str(exc_info.value).lower()
            assert cancelled.is_set()
            # The worker is free again and keeps serving calls.
            assert await asyncio.wait_for(thread.run(lambda: 42), timeout=2.0) == 42
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_slow_call_without_debugger_is_not_cancelled(self):
        import time as _time

        thread, cancelled, scans = self._thread_with_fakes({})
        thread._debugger_window_open = lambda: True  # type: ignore[method-assign]  # e.g. the user's own debugger
        thread.watch_connection("/app/con[1]")
        try:

            def slow():
                _time.sleep(0.8)  # well past halt_check_after_s
                return "done"

            assert await asyncio.wait_for(thread.run(slow), timeout=4.0) == "done"
            assert scans, "the watchdog should have looked for a debugger"
            assert not cancelled.is_set()
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_debugger_in_unwatched_connection_is_ignored(self):
        """A debugger the user opened in their own connection must not cancel our calls."""
        thread, cancelled, _ = self._thread_with_fakes({"/app/con[0]": "ABAP Debugger(1)"})
        thread.watch_connection("/app/con[1]")
        try:
            result = await asyncio.wait_for(thread.run(self._blocking_call(cancelled, max_wait=0.8)), timeout=4.0)
            assert result == "completed without cancel"
            assert not cancelled.is_set()
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_no_scan_without_watched_connections(self):
        thread, cancelled, scans = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        try:
            result = await asyncio.wait_for(thread.run(self._blocking_call(cancelled, max_wait=0.6)), timeout=4.0)
            assert result == "completed without cancel"
            assert not scans
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_halted_connections_reports_only_watched(self):
        thread, _, _ = self._thread_with_fakes({"/app/con[0]": "ABAP Debugger(1)", "/app/con[1]": "ABAP Debugger(2)"})
        thread.watch_connection("/app/con[1]")
        try:
            assert await thread.halted_connections() == {"/app/con[1]": "ABAP Debugger(2)"}
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_missed_cancel_is_retried(self):
        """COM refuses a cancel while the worker is between two calls; the watchdog tries again."""
        from sapguimcp.backend.desktop._com_thread import SapSessionHaltedError

        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"}, cancel_results=[False])
        thread.watch_connection("/app/con[1]")
        try:
            with pytest.raises(SapSessionHaltedError):
                await asyncio.wait_for(thread.run(self._blocking_call(cancelled)), timeout=4.0)
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_swallowed_cancel_still_reports_halted(self):
        """A callable that catches the cancelled call's error must not return a bogus result."""
        from sapguimcp.backend.desktop._com_thread import SapSessionHaltedError

        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        thread.watch_connection("/app/con[1]")
        blocked = self._blocking_call(cancelled)

        def swallowing():
            try:
                return blocked()
            except _FakeComError:
                return []  # e.g. "no dropdown options"

        try:
            with pytest.raises(SapSessionHaltedError):
                await asyncio.wait_for(thread.run(swallowing), timeout=4.0)
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_only_calls_to_the_halted_connection_are_cancelled(self):
        """A slow call on a healthy connection must survive while another one is halted."""
        from sapguimcp.backend.desktop._com_thread import SapSessionHaltedError, com_call_target

        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        thread.watch_connection("/app/con[1]")
        thread.watch_connection("/app/con[2]")
        try:
            token = com_call_target.set("/app/con[2]")
            try:
                result = await asyncio.wait_for(thread.run(self._blocking_call(cancelled, max_wait=0.8)), timeout=4.0)
            finally:
                com_call_target.reset(token)
            assert result == "completed without cancel"
            assert not cancelled.is_set()

            token = com_call_target.set("/app/con[1]")
            try:
                with pytest.raises(SapSessionHaltedError):
                    await asyncio.wait_for(thread.run(self._blocking_call(cancelled)), timeout=4.0)
            finally:
                com_call_target.reset(token)
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_calls_without_a_session_are_never_cancelled(self):
        """e.g. sap_login opening a new connection while another connection is halted."""
        from sapguimcp.backend.desktop._com_thread import NO_SESSION_TARGET, com_call_target

        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        thread.watch_connection("/app/con[1]")
        token = com_call_target.set(NO_SESSION_TARGET)
        try:
            result = await asyncio.wait_for(thread.run(self._blocking_call(cancelled, max_wait=0.8)), timeout=4.0)
            assert result == "completed without cancel"
        finally:
            com_call_target.reset(token)
            thread.shutdown()

    @pytest.mark.anyio
    async def test_unwatched_connection_is_ignored_again(self):
        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        thread.watch_connection("/app/con[1]")
        thread.unwatch_connection("/app/con[1]")
        try:
            result = await asyncio.wait_for(thread.run(self._blocking_call(cancelled, max_wait=0.6)), timeout=4.0)
            assert result == "completed without cancel"
            assert await thread.halted_connections() == {}
        finally:
            thread.shutdown()

    @pytest.mark.anyio
    async def test_watchdog_survives_a_scan_whose_caller_timed_out(self):
        import time as _time

        from sapguimcp.backend.desktop._com_thread import SapSessionHaltedError

        thread, cancelled, _ = self._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        slow_scan = thread._list_debugger_sessions

        def slow(*args):
            _time.sleep(0.4)
            return slow_scan(*args)

        thread._list_debugger_sessions = slow  # type: ignore[method-assign]
        thread.watch_connection("/app/con[1]")
        try:
            with pytest.raises((asyncio.TimeoutError, TimeoutError)):
                await asyncio.wait_for(thread.halted_connections(), timeout=0.1)
            await asyncio.sleep(0.6)  # let the watchdog finish the abandoned scan
            assert thread._watchdog.is_alive()
            with pytest.raises(SapSessionHaltedError):
                await asyncio.wait_for(thread.run(self._blocking_call(cancelled)), timeout=5.0)
        finally:
            thread.shutdown()


class TestAbandonedCallsAreSkipped:
    @pytest.mark.anyio
    async def test_call_whose_caller_gave_up_is_not_run(self, com_thread):
        import threading

        release = threading.Event()
        ran: list[str] = []
        blocker = asyncio.ensure_future(com_thread.run(lambda: release.wait(2.0)))
        await asyncio.sleep(0.05)  # the worker is now busy with the blocker

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await asyncio.wait_for(com_thread.run(lambda: ran.append("probe")), timeout=0.1)

        release.set()
        await blocker
        assert await com_thread.run(lambda: 42) == 42
        assert ran == []


class TestNoComAccessWithoutDebugger:
    @pytest.mark.anyio
    async def test_no_com_scan_without_a_debugger_window(self):
        """Without an ABAP debugger window, the watchdog must not touch SAP GUI at all:
        reading its objects from a second thread while the worker drives them made
        sessions die in long runs."""
        thread, cancelled, scans = TestHaltedByDebugger()._thread_with_fakes({"/app/con[1]": "ABAP Debugger(1)"})
        thread._debugger_window_open = lambda: False  # type: ignore[method-assign]
        thread.watch_connection("/app/con[1]")
        try:
            result = await asyncio.wait_for(
                thread.run(TestHaltedByDebugger()._blocking_call(cancelled, max_wait=0.8)), timeout=4.0
            )
            assert result == "completed without cancel"
            assert await thread.halted_connections() == {}
            assert not scans
        finally:
            thread.shutdown()
