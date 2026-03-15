"""Dedicated background thread for SAP GUI COM calls.

All COM calls must happen on the same apartment-threaded context.
This thread runs CoInitialize() once at startup and processes work
items from a queue. Async callers submit callables and await the
result via concurrent.futures.Future + asyncio.wrap_future.
"""

# pylint: disable=broad-exception-caught
# pylint: disable=import-error  # pythoncom is from pywin32 (Windows-only, not available in CI linting env)

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import queue
import threading
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ComThread:
    """Dedicated thread for all SAP GUI COM calls."""

    def __init__(self, *, init_com: bool = True) -> None:
        self._init_com = init_com
        self._queue: queue.Queue[tuple[Callable[[], Any], concurrent.futures.Future[Any]] | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True, name="sapgui-com-worker")
        self._thread.start()
        logger.debug("com_thread_started")

    def _run(self) -> None:
        """Worker loop: CoInitialize, process queue, CoUninitialize on exit."""
        if self._init_com:
            import pythoncom  # type: ignore[import-untyped]  # pylint: disable=import-outside-toplevel

            pythoncom.CoInitialize()
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                fn, cf_future = item
                try:
                    result = fn()
                    cf_future.set_result(result)
                except Exception as exc:
                    cf_future.set_exception(exc)
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
