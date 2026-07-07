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
- **RPC_S_UNKNOWN_IF** (0x800706B5): Stale COM proxy — the interface
  reference was invalidated (e.g. by a rapid screen transition). Retryable.
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
_RPC_S_UNKNOWN_IF = -2147023179  # 0x800706B5 — "The interface is unknown"

_RETRYABLE_COM_ERRORS = {_RPC_E_SERVERCALL_RETRYLATER, _RPC_E_CALL_REJECTED, _RPC_S_UNKNOWN_IF}


def _get_com_error_code(exc: Exception) -> int | None:
    """Extract the COM error code from an exception, if present."""
    code = getattr(exc, "hresult", None)
    if code is None and exc.args:
        code = exc.args[0] if isinstance(exc.args[0], int) else None
    return code


def is_transient_busy_error(exc: Exception) -> bool:
    """True if *exc* is a "server busy" COM signal, not a dead session.

    ``RPC_E_SERVERCALL_RETRYLATER`` / ``RPC_E_CALL_REJECTED`` mean the SAP GUI
    process's message loop is currently blocked and rejected the call — most
    commonly because a modal dialog (e.g. an ABAP debugger stopped at a
    breakpoint) is running its own nested message loop. That is temporary and
    usually clears once the dialog is dismissed.

    This is deliberately narrower than ``_RETRYABLE_COM_ERRORS``, which also
    includes ``RPC_S_UNKNOWN_IF`` (stale interface — the session's window is
    actually gone). Callers that need to tell "busy" apart from "dead" — e.g.
    a liveness probe deciding whether to prune a session — must use this
    instead of checking membership in ``_RETRYABLE_COM_ERRORS`` (issue #791:
    a modal debugger's busy signal was being treated as a dead session).
    """
    return _get_com_error_code(exc) in (_RPC_E_SERVERCALL_RETRYLATER, _RPC_E_CALL_REJECTED)


class ComThread:  # pylint: disable=too-many-instance-attributes
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
        # Forensic counters/state — populated by ``_execute_with_retry`` and
        # surfaced when the worker dies. Without these, ``com_thread_crashed``
        # logs are blind: we can't correlate the death with what was happening
        # right before. See issue #628 for the motivating incident.
        self._created_at = time.monotonic()
        self._calls_succeeded = 0
        self._calls_failed = 0
        self._last_success_at: float | None = None
        self._last_error_at: float | None = None
        self._last_error_repr: str | None = None
        # Each work item carries an optional per-call max_retries override.
        # ``None`` means "use ``self._max_retries``"; ``0`` means "fail fast on
        # retryable errors" — used by liveness probes where ``RPC_S_UNKNOWN_IF``
        # signals "this session is dead", not "try again".
        self._queue: queue.Queue[tuple[Callable[[], Any], concurrent.futures.Future[Any], int | None] | None] = (
            queue.Queue()
        )
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

            pythoncom.CoInitialize()  # pylint: disable=no-member
        last_call = 0.0
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                fn, cf_future, retries_override = item
                # Resolve the per-call retry budget here so _execute_with_retry
                # stays under the local-variable cap (pylint too-many-locals).
                max_retries = self._max_retries if retries_override is None else retries_override
                self._execute_with_retry(fn, cf_future, last_call, max_retries)
                last_call = time.monotonic()
        except Exception:
            # Forensic snapshot — without this, we can't tell *why* the worker
            # died (issue #628). Pair this with ``com_thread_dead_call_attempted``
            # in ``run()`` to bracket the failure window.
            logger.exception(
                "com_thread_crashed",
                extra=self._forensic_snapshot(last_call),
            )
        finally:
            if self._init_com:
                import pythoncom  # pylint: disable=import-outside-toplevel

                pythoncom.CoUninitialize()  # pylint: disable=no-member

    def _forensic_snapshot(self, last_call: float = 0.0) -> dict[str, Any]:
        """Return a dict of operational state for crash/dead-thread logs.

        All times are absolute monotonic seconds, not wall clock — meaningful
        for relative ordering only. Use ``age_s`` for the worker's lifetime
        and ``s_since_last_*`` to bracket the failure window.
        """
        now = time.monotonic()
        return {
            "age_s": round(now - self._created_at, 3),
            "calls_succeeded": self._calls_succeeded,
            "calls_failed": self._calls_failed,
            "queue_depth": self._queue.qsize(),
            "current_interval_ms": int(self._current_interval_s * 1000),
            "avg_latency_ms": int(self._avg_latency_s * 1000),
            "s_since_last_success": (
                round(now - self._last_success_at, 3) if self._last_success_at is not None else None
            ),
            "s_since_last_error": (round(now - self._last_error_at, 3) if self._last_error_at is not None else None),
            "s_since_last_call": round(now - last_call, 3) if last_call else None,
            "last_error_repr": self._last_error_repr,
        }

    def _execute_with_retry(
        self,
        fn: Callable[[], Any],
        cf_future: concurrent.futures.Future[Any],
        last_call: float,
        max_retries: int,
    ) -> None:
        """Execute a COM call with adaptive throttling and retry on transient errors.

        ``max_retries`` is the per-call retry budget — the caller resolves it
        from ``self._max_retries`` or a per-call override (``0`` is used by
        reconciliation probes that must fail fast on ``RPC_S_UNKNOWN_IF``).
        """
        for attempt in range(max_retries + 1):
            # Throttle: wait at least current_interval since last call
            elapsed = time.monotonic() - last_call
            if elapsed < self._current_interval_s:
                time.sleep(self._current_interval_s - elapsed)

            start = time.monotonic()
            try:
                result = fn()
                duration = time.monotonic() - start

                # Detect latency spike BEFORE updating the average
                is_spike = duration > 5 * self._avg_latency_s and self._avg_latency_s > 0.005

                # Update latency tracking (exponential moving average, alpha=0.2)
                self._avg_latency_s = 0.8 * self._avg_latency_s + 0.2 * duration

                if is_spike:
                    self._increase_interval("latency_spike", duration)
                else:
                    self._decrease_interval()

                self._calls_succeeded += 1
                self._last_success_at = time.monotonic()
                cf_future.set_result(result)
                return

            except Exception as exc:
                duration = time.monotonic() - start
                error_code = _get_com_error_code(exc)
                self._last_error_at = time.monotonic()
                self._last_error_repr = repr(exc)[:200]

                if error_code in _RETRYABLE_COM_ERRORS and attempt < max_retries:
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

                self._calls_failed += 1
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

    async def run(self, fn: Callable[[], T], *, max_retries: int | None = None) -> T:
        """Submit a callable to the COM thread and await its result.

        Args:
            fn: Callable to execute on the dedicated COM thread.
            max_retries: Per-call override of the retry budget. ``None`` uses
                the default ``self._max_retries``. Pass ``0`` for liveness
                probes where retryable errors like ``RPC_S_UNKNOWN_IF`` mean
                "this session is dead", not "transient — try again".
        """
        if not self._thread.is_alive():
            # Pair this with ``com_thread_crashed`` from ``_run`` to bracket
            # the failure. ``s_since_last_success`` and ``last_error_repr``
            # are usually the most useful fields for diagnosis (issue #628).
            logger.error(
                "com_thread_dead_call_attempted",
                extra=self._forensic_snapshot(),
            )
            raise RuntimeError(
                "COM worker thread is dead — the worker exited and this ComThread instance "
                "cannot be revived. The BackendManager must rebuild it."
            )
        cf_future: concurrent.futures.Future[T] = concurrent.futures.Future()
        self._queue.put((fn, cf_future, max_retries))
        return await asyncio.wrap_future(cf_future)

    @property
    def is_alive(self) -> bool:
        """Whether the underlying worker thread is still running.

        Returns False after the thread crashed or was shut down. A dead
        ``ComThread`` cannot be revived — callers must construct a new
        instance (the ``BackendManager`` does this transparently).
        """
        return self._thread.is_alive()

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
