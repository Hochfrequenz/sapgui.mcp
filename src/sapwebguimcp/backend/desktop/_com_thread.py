"""Dedicated background thread for SAP GUI COM calls.

All COM calls must happen on the same apartment-threaded context.
This thread runs CoInitialize() once at startup and processes work
items from a queue. Async callers submit callables and await the
result via concurrent.futures.Future + asyncio.wrap_future.

Adaptive throttling: The thread measures call latency and COM error
signals to automatically adjust the interval between calls. Under
low load (single agent), calls fire at full speed. Under high load
(multiple parallel agents), the interval increases to prevent COM
disconnection. Key signals:

- **RPC_E_SERVERCALL_RETRYLATER** (0x80010105): COM is busy — back off.
  This is the leading indicator before a full disconnect.
- **RPC_E_DISCONNECTED** (-2147417848): Connection dead — fatal.
- **Call latency spikes**: If a call takes 5x longer than the moving
  average, COM is under pressure.
"""

# pylint: disable=broad-exception-caught
# pylint: disable=import-error  # pythoncom is from pywin32 (Windows-only, not available in CI linting env)

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import queue
import threading
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# COM error codes
_RPC_E_DISCONNECTED = -2147417848
_RPC_E_SERVERCALL_RETRYLATER = -2147417851  # 0x80010105
_RPC_E_CALL_REJECTED = -2147418111  # 0x80010001

_RETRYABLE_COM_ERRORS = {_RPC_E_SERVERCALL_RETRYLATER, _RPC_E_CALL_REJECTED}


def _get_com_error_code(exc: Exception) -> int | None:
    """Extract the COM error code from an exception, if present."""
    code = getattr(exc, "hresult", None)
    if code is None and exc.args:
        code = exc.args[0] if isinstance(exc.args[0], int) else None
    return code


class ComThread:
    """Dedicated thread for all SAP GUI COM calls.

    All operations are serialized through a single thread with CoInitialize.
    Adaptive throttling adjusts the interval between calls based on COM
    pressure signals (retryable errors and latency spikes).
    """

    def __init__(
        self,
        *,
        init_com: bool = True,
        min_interval_ms: int = 100,
        max_interval_ms: int = 2000,
        max_retries: int = 3,
    ) -> None:
        self._init_com = init_com
        self._min_interval_s = min_interval_ms / 1000.0
        self._max_interval_s = max_interval_ms / 1000.0
        self._current_interval_s = self._min_interval_s
        self._max_retries = max_retries
        # Latency tracking (exponential moving average)
        self._avg_latency_s = 0.01  # initial estimate: 10ms
        self._queue: queue.Queue[tuple[Callable[[], Any], concurrent.futures.Future[Any]] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sapgui-com-worker")
        self._thread.start()
        logger.info(
            "com_thread_started",
            extra={"min_interval_ms": min_interval_ms, "max_interval_ms": max_interval_ms},
        )

    def _run(self) -> None:
        """Worker loop: CoInitialize, process queue, CoUninitialize on exit."""
        if self._init_com:
            import pythoncom  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

            pythoncom.CoInitialize()
        last_call = 0.0
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                fn, cf_future = item
                self._execute_with_retry(fn, cf_future, last_call)
                last_call = time.monotonic()
        except Exception:
            logger.exception("com_thread_crashed")
        finally:
            if self._init_com:
                import pythoncom  # pylint: disable=import-outside-toplevel

                pythoncom.CoUninitialize()

    def _execute_with_retry(
        self,
        fn: Callable[[], Any],
        cf_future: concurrent.futures.Future[Any],
        last_call: float,
    ) -> None:
        """Execute a COM call with adaptive throttling and retry on transient errors."""
        for attempt in range(self._max_retries + 1):
            # Throttle: wait at least current_interval since last call
            elapsed = time.monotonic() - last_call
            if elapsed < self._current_interval_s:
                time.sleep(self._current_interval_s - elapsed)

            start = time.monotonic()
            try:
                result = fn()
                duration = time.monotonic() - start

                # Update latency tracking (exponential moving average, alpha=0.2)
                self._avg_latency_s = 0.8 * self._avg_latency_s + 0.2 * duration

                # Detect latency spike: if call took 5x the average, COM is under pressure
                if duration > 5 * self._avg_latency_s and self._avg_latency_s > 0.005:
                    self._increase_interval("latency_spike", duration)
                else:
                    self._decrease_interval()

                cf_future.set_result(result)
                return

            except Exception as exc:
                duration = time.monotonic() - start
                error_code = _get_com_error_code(exc)

                if error_code in _RETRYABLE_COM_ERRORS and attempt < self._max_retries:
                    # COM is busy — back off and retry
                    backoff = self._current_interval_s * (2**attempt)
                    self._increase_interval("com_busy", backoff)
                    logger.warning(
                        "com_call_retry",
                        extra={
                            "attempt": attempt + 1,
                            "error_code": error_code,
                            "backoff_ms": int(backoff * 1000),
                            "interval_ms": int(self._current_interval_s * 1000),
                        },
                    )
                    time.sleep(backoff)
                    last_call = time.monotonic()
                    continue

                if error_code == _RPC_E_DISCONNECTED:
                    wrapped = RuntimeError(
                        "SAP GUI COM connection lost (RPC_E_DISCONNECTED). "
                        "This typically happens when too many parallel agents "
                        "overload the COM interface or SAP GUI was closed. "
                        "Call sap_login to re-establish the connection."
                    )
                    wrapped.__cause__ = exc
                    cf_future.set_exception(wrapped)
                else:
                    cf_future.set_exception(exc)
                return

        # Exhausted retries
        cf_future.set_exception(
            RuntimeError(f"COM call failed after {self._max_retries} retries (last error code: {error_code})")
        )

    def _increase_interval(self, reason: str, observed_delay: float) -> None:
        """Increase the throttle interval (back off)."""
        old = self._current_interval_s
        # Double the interval, capped at max
        self._current_interval_s = min(self._current_interval_s * 2, self._max_interval_s)
        if self._current_interval_s != old:
            logger.debug(
                "com_throttle_increase",
                extra={
                    "reason": reason,
                    "old_ms": int(old * 1000),
                    "new_ms": int(self._current_interval_s * 1000),
                    "observed_ms": int(observed_delay * 1000),
                },
            )

    def _decrease_interval(self) -> None:
        """Gradually decrease the throttle interval (speed up)."""
        if self._current_interval_s > self._min_interval_s:
            # Decay slowly: reduce by 10%
            self._current_interval_s = max(self._current_interval_s * 0.9, self._min_interval_s)

    async def run(self, fn: Callable[[], T]) -> T:
        """Submit a callable to the COM thread and await its result."""
        if not self._thread.is_alive():
            raise RuntimeError("COM worker thread is dead — call sap_login to reconnect")
        cf_future: concurrent.futures.Future[T] = concurrent.futures.Future()
        self._queue.put((fn, cf_future))
        return await asyncio.wrap_future(cf_future)

    @property
    def current_interval_ms(self) -> int:
        """Current throttle interval in milliseconds (for diagnostics)."""
        return int(self._current_interval_s * 1000)

    @property
    def queue_depth(self) -> int:
        """Number of pending calls in the queue (for diagnostics)."""
        return self._queue.qsize()

    def shutdown(self) -> None:
        """Signal the worker thread to exit and wait for cleanup."""
        logger.info(
            "com_thread_stopped",
            extra={
                "final_interval_ms": int(self._current_interval_s * 1000),
                "avg_latency_ms": int(self._avg_latency_s * 1000),
            },
        )
        self._queue.put(None)
        self._thread.join(timeout=5)
