"""Backend manager — singleton entry point for tools."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any

from sapguimcp.models.config import get_settings
from sapguimcp.session_language import set_session_language

if sys.platform == "win32" or TYPE_CHECKING:
    from sapguimcp.backend.desktop import DesktopBackend, _current_session_id
    from sapguimcp.backend.desktop._com_thread import ComThread

logger = logging.getLogger(__name__)


def _require_windows() -> None:
    """Raise when not running on Windows: the desktop backend needs SAP GUI for Windows (COM)."""
    if sys.platform != "win32":
        raise RuntimeError("sapgui.mcp requires Windows with SAP GUI for Windows installed.")


class BackendManager:  # pylint: disable=too-few-public-methods
    """Manages backend instances across sessions."""

    def __init__(self) -> None:
        self.backend_type = "desktop"
        self._backends: dict[str, DesktopBackend] = {}  # Cache by session ID
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
    ) -> DesktopBackend:
        """Get or create the desktop backend for the given session."""
        _require_windows()
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
            set_session_language(cached.registry.language_of(effective))
            return cached
        if self._com_thread is None:
            interval = get_settings().com_min_interval_ms
            self._com_thread = ComThread(min_interval_ms=interval)
        new_backend = DesktopBackend(com_thread=self._com_thread)
        self._backends["desktop"] = new_backend
        effective = session or new_backend.registry.primary_session
        _current_session_id.set(effective)
        # The fresh registry is empty, so this clears any stale value.
        set_session_language(new_backend.registry.language_of(effective))
        return new_backend

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
            # The language belonged to a session of the dropped registry.
            set_session_language(None)

    async def close(self) -> None:
        """Shut down the active backend and release resources."""
        if self._com_thread is not None:
            self._com_thread.shutdown()
        self._backends.clear()


# -- Singleton --

_backend_manager: BackendManager | None = None  # pylint: disable=invalid-name


def get_backend_manager() -> BackendManager:
    """Get the global BackendManager singleton (lazy init)."""
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    if _backend_manager is None:
        _backend_manager = BackendManager()
    return _backend_manager


async def get_backend(
    session: str | None = None,
    agent_id: str | None = None,
    tool_name: str = "",
) -> DesktopBackend:
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


async def close_backend() -> None:
    """Shut down the active backend (called during server shutdown)."""
    if _backend_manager is not None:
        await _backend_manager.close()


def reset_backend_manager() -> None:
    """Reset the singleton (for testing)."""
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    _backend_manager = None
