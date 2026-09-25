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

Halted sessions: a COM call that makes SAP run ABAP (``SendVKey``, ``Press``,
...) does not return until that ABAP finishes. When it stops at a breakpoint,
the call blocks until a human is done in the ABAP debugger — and since every
COM call goes through this one worker, the whole server would freeze. A
watchdog thread therefore looks for an open ABAP debugger in the watched SAP
connections whenever a call runs longer than ``halt_check_after_s``, and if it
finds one, cancels the blocked call with ``CoCancelCall``. The caller gets a
:class:`SapSessionHaltedError`; SAP keeps the program halted, and the session
works again once the debugger is continued.
"""

# pylint: disable=broad-exception-caught
# pylint: disable=import-error  # pythoncom is from pywin32 (Windows-only, not available in CI linting env)

from __future__ import annotations

import asyncio
import concurrent.futures
import ctypes
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

#: Program of an ABAP debugger session. The debugger runs in its own session of the
#: halted session's connection (window "ABAP Debugger(1)  (exklusiv) ...").
_DEBUGGER_PROGRAMS = frozenset({"RSTPDAMAIN"})
_DEBUGGER_TITLE_PREFIXES = ("ABAP Debugger", "ABAP-Debugger")


class SapSessionHaltedError(RuntimeError):
    """A COM call was cancelled because its SAP session stopped at an ABAP breakpoint."""

    def __init__(self, debugger_titles: list[str]) -> None:
        windows = ", ".join(f"'{title}'" for title in debugger_titles)
        super().__init__(
            f"The SAP session stopped at an ABAP breakpoint: the ABAP debugger is open in SAP GUI "
            f"(window {windows}). The MCP cannot drive the debugger — a human must continue (F8) or exit "
            "it in SAP GUI. Until then this session stays busy and calls to it fail with this error; "
            "other sessions keep working. Remove the breakpoint with sap_breakpoint_delete when it is no "
            "longer needed."
        )
        self.debugger_titles = debugger_titles


def _get_com_error_code(exc: Exception) -> int | None:
    """Extract the COM error code from an exception, if present."""
    code = getattr(exc, "hresult", None)
    if code is None and exc.args:
        code = exc.args[0] if isinstance(exc.args[0], int) else None
    return code


#: Actionable, human-readable hints for known connection-level COM errors — the
#: raw HRESULT + localized COM message (e.g. ``-2147023179 'Die Schnittstelle ist
#: unbekannt.'``) is meaningless to an agent/operator. Keyed by HRESULT.
_FATAL_COM_ERROR_HINTS: dict[int, str] = {
    _RPC_S_UNKNOWN_IF: (
        "The SAP GUI session handle is stale or no longer valid (interface unknown). This can be a "
        "transient stale proxy or a genuinely gone session. Retry the operation; if it persists, run "
        "sap_login to open a fresh session, and restart SAP Logon if that still fails."
    ),
    _RPC_E_DISCONNECTED: (
        "The SAP GUI connection was lost (RPC disconnected). Run sap_login to reconnect; "
        "if that fails, restart SAP Logon."
    ),
}


def describe_com_error(exc: Exception) -> str | None:
    """Return an actionable remediation hint for a known connection-level COM error.

    Maps cryptic HRESULTs like ``-2147023179`` ("Die Schnittstelle ist
    unbekannt." / interface unknown) to a plain-language message telling the
    caller what to do, so tools can surface that instead of the raw
    ``pywintypes.com_error`` tuple (issue #789). Returns ``None`` for errors
    that aren't a recognised connection-level COM code.
    """
    code = _get_com_error_code(exc)
    if code is None:
        return None
    return _FATAL_COM_ERROR_HINTS.get(code)


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
        halt_check_after_s: float = 3.0,
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
        # Halt watchdog state (see module docstring). ``_state_lock`` guards the
        # in-flight call bookkeeping shared between the worker and the watchdog.
        self._halt_check_after_s = halt_check_after_s
        self._state_lock = threading.Lock()
        self._call_seq = 0
        self._in_flight_seq: int | None = None
        self._in_flight_since: float | None = None
        self._halted_calls: dict[int, list[str]] = {}
        self._worker_tid: int | None = None
        self._watched_connections: set[str] = set()
        self._scan_requests: queue.Queue[concurrent.futures.Future[dict[str, str]]] = queue.Queue()
        self._stopping = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sapgui-com-worker")
        self._thread.start()
        self._watchdog = threading.Thread(target=self._watch, daemon=True, name="sapgui-com-halt-watchdog")
        self._watchdog.start()
        logger.info(
            "com_thread_started",
            extra={"min_interval_ms": min_interval_ms, "max_interval_ms": max_interval_ms},
        )

    def _run(self) -> None:
        """Worker loop: CoInitialize, process queue, CoUninitialize on exit."""
        if self._init_com:
            import pythoncom  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

            pythoncom.CoInitialize()  # pylint: disable=no-member
            _enable_call_cancellation()
        self._worker_tid = threading.get_native_id()
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
                result = self._invoke_tracked(fn)
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
                # Guard against a caller that already gave up: asyncio.wait_for
                # (used by the liveness probes in get_session_status /
                # _reconcile_locked) cancels the wrapping future on timeout, and
                # since this worker never calls set_running_or_notify_cancel the
                # concurrent.futures.Future is cancellable while we run fn(). A
                # set_result on a cancelled future raises InvalidStateError,
                # which would crash the worker loop — precisely the wedged-COM
                # scenario those probes exist to survive (issue #789).
                if not cf_future.done():
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
                    wrapped: BaseException = RuntimeError(
                        "SAP GUI COM connection lost (RPC_E_DISCONNECTED). "
                        "This typically happens when too many parallel agents "
                        "overload the COM interface or SAP GUI was closed. "
                        "Call sap_login to re-establish the connection."
                    )
                    wrapped.__cause__ = exc
                else:
                    wrapped = exc
                # See the set_result guard above — a cancelled caller future
                # must not crash the worker with InvalidStateError.
                if not cf_future.done():
                    cf_future.set_exception(wrapped)
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
        self._stopping.set()
        self._queue.put(None)
        self._thread.join(timeout=5)
        self._watchdog.join(timeout=2)

    # ---- Halted sessions (ABAP breakpoint) ----

    def watch_connection(self, connection_id: str) -> None:
        """Watch a SAP GUI connection (e.g. ``/app/con[1]``) for an ABAP debugger.

        Only watched connections are considered, so a debugger the user opened in
        a connection of their own never cancels the server's calls.
        """
        with self._state_lock:
            self._watched_connections.add(connection_id)
        logger.info("com_watch_connection", extra={"connection_id": connection_id})

    async def halted_connections(self) -> dict[str, str]:
        """Watched connections with an open ABAP debugger, mapped to its window title.

        Runs on the watchdog thread, which never touches a halted session beyond its
        ``Busy`` flag — so this answers even while the worker is blocked.
        """
        with self._state_lock:
            if not self._watched_connections:
                return {}
        request: concurrent.futures.Future[dict[str, str]] = concurrent.futures.Future()
        self._scan_requests.put(request)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(request), timeout=5.0)
        except Exception:
            logger.warning("com_halt_scan_failed", exc_info=True)
            return {}

    def _invoke_tracked(self, fn: Callable[[], Any]) -> Any:
        """Run *fn* on the worker, visible to the watchdog while it is in flight."""
        with self._state_lock:
            self._call_seq += 1
            seq = self._call_seq
            self._in_flight_seq = seq
            self._in_flight_since = time.monotonic()
        try:
            return fn()
        except Exception as exc:
            with self._state_lock:
                debugger_titles = self._halted_calls.get(seq)
            if debugger_titles is not None:
                raise SapSessionHaltedError(debugger_titles) from exc
            raise
        finally:
            with self._state_lock:
                self._in_flight_seq = None
                self._in_flight_since = None
                self._halted_calls.pop(seq, None)

    def _watch(self) -> None:
        """Watchdog loop: answer scan requests, cancel calls stuck behind a debugger."""
        if self._init_com:
            import pythoncom  # pylint: disable=import-outside-toplevel

            pythoncom.CoInitialize()  # pylint: disable=no-member
        tick_s = max(0.05, min(0.5, self._halt_check_after_s / 2))
        try:
            while not self._stopping.is_set():
                request: concurrent.futures.Future[dict[str, str]] | None
                try:
                    request = self._scan_requests.get(timeout=tick_s)
                except queue.Empty:
                    request = None
                if request is not None and not request.done():
                    request.set_result(self._halted_watched_connections())
                self._cancel_if_halted()
        except Exception:
            logger.exception("com_halt_watchdog_crashed")
        finally:
            if self._init_com:
                import pythoncom  # pylint: disable=import-outside-toplevel

                pythoncom.CoUninitialize()  # pylint: disable=no-member

    def _cancel_if_halted(self) -> None:
        """Cancel the in-flight call if it runs long and a watched connection is halted."""
        with self._state_lock:
            seq, since = self._in_flight_seq, self._in_flight_since
            watching = bool(self._watched_connections)
        if seq is None or since is None or not watching:
            return
        if time.monotonic() - since < self._halt_check_after_s:
            return
        halted = self._halted_watched_connections()
        if not halted:
            return
        with self._state_lock:
            if self._in_flight_seq != seq or seq in self._halted_calls:
                return  # finished meanwhile, or already cancelled
            self._halted_calls[seq] = sorted(halted.values())
            # Under the lock, so the worker can't finish this call and start the next
            # one before the cancel request reaches the call it is meant for.
            self._cancel_worker_call()
        logger.warning(
            "com_call_cancelled_halted_at_breakpoint",
            extra={"halted_connections": halted, "call_running_s": round(time.monotonic() - since, 1)},
        )

    def _halted_watched_connections(self) -> dict[str, str]:
        with self._state_lock:
            watched = set(self._watched_connections)
        if not watched:
            return {}
        try:
            found = self._list_debugger_sessions(watched)
        except Exception:
            logger.debug("com_debugger_scan_failed", exc_info=True)
            return {}
        return {connection_id: title for connection_id, title in found.items() if connection_id in watched}

    def _list_debugger_sessions(self, connection_ids: set[str]) -> dict[str, str]:
        """Find an ABAP debugger session in the given SAP GUI connections (watchdog thread).

        A halted session blocks every COM call except ``Busy``, so busy sessions are
        skipped — the debugger session itself is idle while it waits for the human.
        """
        import win32com.client  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

        found: dict[str, str] = {}
        app = win32com.client.GetObject("SAPGUI").GetScriptingEngine
        for connection_index in range(app.Children.Count):
            connection = app.Children(connection_index)
            connection_id = str(connection.Id)
            if connection_id not in connection_ids:
                continue
            for session_index in range(connection.Children.Count):
                session = connection.Children(session_index)
                if session.Busy:
                    continue
                title = str(session.Children(0).Text)
                if str(session.Info.Program) in _DEBUGGER_PROGRAMS or title.startswith(_DEBUGGER_TITLE_PREFIXES):
                    found[connection_id] = title
                    break
        return found

    def _cancel_worker_call(self) -> None:
        """Ask COM to cancel the worker's pending outbound call (it raises RPC_E_CALL_CANCELED)."""
        if self._worker_tid is None:
            return
        try:
            _ole32().CoCancelCall(self._worker_tid, 0)
        except Exception:
            logger.warning("com_cancel_call_failed", exc_info=True)


def _enable_call_cancellation() -> None:
    """Let other threads cancel this thread's pending COM calls (see ``_cancel_worker_call``)."""
    try:
        _ole32().CoEnableCallCancellation(None)
    except Exception:
        logger.warning("com_enable_call_cancellation_failed", exc_info=True)


def _ole32() -> Any:
    """``ctypes.windll.ole32`` — Windows only; raises AttributeError elsewhere."""
    return ctypes.windll.ole32  # type: ignore[attr-defined,unused-ignore]
