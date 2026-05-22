"""Backend manager — singleton entry point for tools."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any, get_args

from sapguimcp.backend.webgui.backend import WebGuiBackend
from sapguimcp.backend.webgui.browser import close_browser_manager, get_browser_manager
from sapguimcp.models.config import BackendType, get_settings

if sys.platform == "win32" or TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend, _current_session_id
    from sapguimcp.backend.desktop._com_thread import ComThread

logger = logging.getLogger(__name__)

_VALID_BACKEND_TYPES: set[str] = set(get_args(BackendType))


class BackendManager:  # pylint: disable=too-few-public-methods
    """Manages backend instances across sessions."""

    def __init__(self, backend_type: BackendType = "webgui") -> None:
        if backend_type not in _VALID_BACKEND_TYPES:
            raise ValueError(f"Unknown backend type '{backend_type}'. Valid types: {_VALID_BACKEND_TYPES}")
        if backend_type == "desktop" and sys.platform != "win32":
            raise RuntimeError(
                "BACKEND_TYPE=desktop requires Windows with SAP GUI installed. "
                "On macOS/Linux, use BACKEND_TYPE=webgui (the default) instead."
            )
        self.backend_type = backend_type
        self._backends: dict[str, WebGuiBackend | DesktopBackend] = {}  # Cache by session ID
        self._page_ids: dict[str, int] = {}  # Track page identity for cache invalidation
        self._com_thread: Any = None  # Lazy-init ComThread for desktop backend
        # Serializes desktop dead-thread recovery so concurrent callers don't
        # all rebuild the ComThread + DesktopBackend at once. Safe to construct
        # without a running loop on Python 3.10+ (which we require).
        self._desktop_recovery_lock: asyncio.Lock = asyncio.Lock()

    async def get_or_create(  # pylint: disable=too-many-locals,used-before-assignment,possibly-used-before-assignment
        self,
        session: str | None = None,
        agent_id: str | None = None,
        tool_name: str = "",
    ) -> WebGuiBackend | DesktopBackend:
        """Get or create a backend instance for the given session.

        Caches WebGuiBackend instances by session ID. Returns cached instance
        if the underlying page is still the same, creates a new one otherwise.
        """
        if self.backend_type == "webgui":
            browser_manager = await get_browser_manager()
            page = await browser_manager.get_or_create_session_page_checked(session, agent_id, tool_name)
            session_key = session or browser_manager.registry.primary_session
            cached = self._backends.get(session_key)
            if cached is not None and self._page_ids.get(session_key) == id(page):
                return cached
            backend = WebGuiBackend(page)
            self._backends[session_key] = backend
            self._page_ids[session_key] = id(page)
            return backend
        if self.backend_type == "desktop":
            # Single shared DesktopBackend — session routing via ContextVar.
            # If the cached ComThread's worker has died, the cached backend
            # is unusable: drop it and rebuild before serving the request.
            await self._recover_desktop_if_dead()
            cached = self._backends.get("desktop")
            if cached is not None:
                assert isinstance(cached, DesktopBackend)
                effective = session or cached.registry.primary_session
                _current_session_id.set(effective)
                cached.registry.check_binding(effective, agent_id, tool_name)
                return cached
            if self._com_thread is None:
                interval = get_settings().com_min_interval_ms
                self._com_thread = ComThread(min_interval_ms=interval)
            new_backend = DesktopBackend(com_thread=self._com_thread)
            self._backends["desktop"] = new_backend
            effective = session or new_backend.registry.primary_session
            _current_session_id.set(effective)
            return new_backend
        raise ValueError(f"No implementation for backend '{self.backend_type}'")

    async def _recover_desktop_if_dead(self) -> None:
        """If the cached desktop ComThread worker died, drop and rebuild.

        Once a ``ComThread`` worker exits (crash or shutdown), the instance
        cannot be revived — its ``threading.Thread`` is one-shot. Without
        this recovery the cached ``DesktopBackend`` keeps a stale reference
        to the dead thread and every subsequent ``sap_login`` (or any other
        desktop tool) raises ``COM worker thread is dead`` until the
        process restarts (issue #628).

        Recovery clears the cached ``ComThread`` and ``DesktopBackend``
        (the latter drops the now-stale ``DesktopSessionRegistry`` whose
        ``GuiSession`` COM proxies are also dead) and resets the per-task
        ``_current_session_id`` ContextVar so the next call doesn't try
        to look up a stale ``s1``/``s2`` against the empty registry.

        Serialized by an ``asyncio.Lock`` so concurrent callers don't race
        on the rebuild — the second caller's re-check inside the lock
        finds a fresh, alive worker and falls through.
        """
        if self._com_thread is None or self._com_thread.is_alive:
            return
        async with self._desktop_recovery_lock:
            # Re-check under the lock: another coroutine may have rebuilt
            # the ComThread while we were waiting for the lock.
            if self._com_thread is not None and self._com_thread.is_alive:
                return
            logger.warning(
                "desktop_com_thread_dead_rebuilding",
                extra={"had_cached_backend": "desktop" in self._backends},
            )
            self._com_thread = None
            self._backends.pop("desktop", None)
            # Reset ContextVar so a stale session id from before the crash
            # doesn't hit the freshly empty registry on the next lookup.
            _current_session_id.set(None)

    async def close(self) -> None:
        """Shut down the active backend and release resources."""
        if self.backend_type == "webgui":
            await close_browser_manager()
        elif self.backend_type == "desktop":
            if self._com_thread is not None:
                self._com_thread.shutdown()
        self._backends.clear()
        self._page_ids.clear()


# -- Singleton --

_backend_manager: BackendManager | None = None  # pylint: disable=invalid-name


def get_backend_manager() -> BackendManager:
    """Get the global BackendManager singleton (lazy init).

    Reads ``backend_type`` from settings on first call.
    """
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    if _backend_manager is None:
        settings = get_settings()
        _backend_manager = BackendManager(backend_type=settings.backend_type)
    return _backend_manager


async def get_backend(
    session: str | None = None,
    agent_id: str | None = None,
    tool_name: str = "",
) -> WebGuiBackend | DesktopBackend:
    """Convenience: get a backend instance for the given session.

    This is the primary entry point for all tools.
    """
    manager = get_backend_manager()
    return await manager.get_or_create(session, agent_id, tool_name)


async def get_desktop_backend(
    session: str | None = None,
    agent_id: str | None = None,
    tool_name: str = "",
) -> DesktopBackend:
    """Get a DesktopBackend instance. Asserts backend_type is desktop."""
    backend = await get_backend(session, agent_id, tool_name)
    assert isinstance(backend, DesktopBackend)
    return backend


async def get_webgui_backend(
    session: str | None = None,
    agent_id: str | None = None,
    tool_name: str = "",
) -> WebGuiBackend:
    """Get a WebGuiBackend instance. Asserts backend_type is webgui."""
    backend = await get_backend(session, agent_id, tool_name)
    assert isinstance(backend, WebGuiBackend)
    return backend


async def close_backend() -> None:
    """Shut down the active backend (called during server shutdown)."""
    if _backend_manager is not None:
        await _backend_manager.close()


def reset_backend_manager() -> None:
    """Reset the singleton (for testing)."""
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    _backend_manager = None
