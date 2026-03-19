"""Dedicated background thread for SAP GUI COM calls.

All COM calls must happen on the same apartment-threaded context.
This thread runs CoInitialize() once at startup and processes work
items from a queue. Async callers submit callables and await the
result via concurrent.futures.Future + asyncio.wrap_future.

Rate limiting: A configurable minimum interval between COM calls
prevents overloading SAP GUI when multiple parallel agents fire
rapid-fire operations. Default is 50ms — enough to prevent COM
disconnection under load while keeping single-agent usage fast.
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


class ComThread:
    """Dedicated thread for all SAP GUI COM calls.

    All operations are serialized through a single thread with CoInitialize.
    An optional minimum interval between calls prevents COM overload when
    multiple parallel agents submit rapid-fire operations.
    """

    def __init__(self, *, init_com: bool = True, min_interval_ms: int = 50) -> None:
        self._init_com = init_com
        self._min_interval_s = min_interval_ms / 1000.0
        self._queue: queue.Queue[tuple[Callable[[], Any], concurrent.futures.Future[Any]] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sapgui-com-worker")
        self._thread.start()
        logger.debug("com_thread_started", extra={"min_interval_ms": min_interval_ms})

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

                # Rate limiting: ensure minimum interval between COM calls
                if self._min_interval_s > 0:
                    elapsed = time.monotonic() - last_call
                    if elapsed < self._min_interval_s:
                        time.sleep(self._min_interval_s - elapsed)

                try:
                    result = fn()
                    cf_future.set_result(result)
                except Exception as exc:
                    # Detect COM disconnection (RPC_E_DISCONNECTED = -2147417848)
                    # and provide actionable guidance instead of a raw COM error.
                    error_code = getattr(exc, "hresult", None)
                    if error_code is None and exc.args:
                        error_code = exc.args[0]
                    if error_code == -2147417848:
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
                finally:
                    last_call = time.monotonic()
        except Exception:
            logger.exception("com_thread_crashed")
        finally:
            if self._init_com:
                import pythoncom  # pylint: disable=import-outside-toplevel

                pythoncom.CoUninitialize()

    async def run(self, fn: Callable[[], T]) -> T:
        """Submit a callable to the COM thread and await its result."""
        if not self._thread.is_alive():
            raise RuntimeError("COM worker thread is dead")
        cf_future: concurrent.futures.Future[T] = concurrent.futures.Future()
        self._queue.put((fn, cf_future))
        return await asyncio.wrap_future(cf_future)

    def shutdown(self) -> None:
        """Signal the worker thread to exit and wait for cleanup."""
        logger.debug("com_thread_stopped")
        self._queue.put(None)
        self._thread.join(timeout=5)
