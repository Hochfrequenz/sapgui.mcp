"""Backend manager — singleton entry point for tools."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any, get_args

from sapwebguimcp.models.config import BackendType, get_settings

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

_VALID_BACKEND_TYPES: set[str] = set(get_args(BackendType))


class BackendManager:  # pylint: disable=too-few-public-methods
    """Manages SapUiBackend instances across sessions.

    Wraps the existing BrowserManager/SessionRegistry for WebGUI.
    """

    def __init__(self, backend_type: BackendType = "webgui") -> None:
        if backend_type not in _VALID_BACKEND_TYPES:
            raise ValueError(f"Unknown backend type '{backend_type}'. Valid types: {_VALID_BACKEND_TYPES}")
        if backend_type == "desktop" and sys.platform != "win32":
            raise RuntimeError(
                "BACKEND_TYPE=desktop requires Windows with SAP GUI installed. "
                "On macOS/Linux, use BACKEND_TYPE=webgui (the default) instead."
            )
        self.backend_type = backend_type
        self._backends: dict[str, SapUiBackend] = {}  # Cache by session ID
        self._page_ids: dict[str, int] = {}  # Track page identity for cache invalidation
        self._com_thread: Any = None  # Lazy-init ComThread for desktop backend

    async def get_or_create(  # pylint: disable=too-many-locals
        self,
        session: str | None = None,
        agent_id: str | None = None,
        tool_name: str = "",
    ) -> SapUiBackend:
        """Get or create a backend instance for the given session.

        Caches WebGuiBackend instances by session ID. Returns cached instance
        if the underlying page is still the same, creates a new one otherwise.
        """
        if self.backend_type == "webgui":
            from sapwebguimcp.backend.webgui.backend import WebGuiBackend  # pylint: disable=import-outside-toplevel
            from sapwebguimcp.backend.webgui.browser import (  # pylint: disable=import-outside-toplevel
                get_browser_manager,
            )

            browser_manager = await get_browser_manager()
            page = await browser_manager.get_or_create_session_page_checked(session, agent_id, tool_name)
            session_key = session or "s1"
            cached = self._backends.get(session_key)
            if cached is not None and self._page_ids.get(session_key) == id(page):
                return cached
            backend = WebGuiBackend(page)
            self._backends[session_key] = backend
            self._page_ids[session_key] = id(page)
            return backend
        if self.backend_type == "desktop":
            from sapwebguimcp.backend.desktop import (  # pylint: disable=import-outside-toplevel
                DesktopBackend,
                _current_session_id,
            )
            from sapwebguimcp.backend.desktop._com_thread import ComThread  # pylint: disable=import-outside-toplevel

            # Single shared DesktopBackend — session routing via ContextVar
            cached = self._backends.get("desktop")
            if cached is not None:
                _current_session_id.set(session or "s1")
                if isinstance(cached, DesktopBackend):
                    cached._registry.check_binding(  # pylint: disable=protected-access
                        session or "s1", agent_id, tool_name
                    )
                return cached
            if self._com_thread is None:
                self._com_thread = ComThread(min_interval_ms=get_settings().com_min_interval_ms)
            new_backend = DesktopBackend(com_thread=self._com_thread)
            self._backends["desktop"] = new_backend
            _current_session_id.set(session or "s1")
            return new_backend
        raise ValueError(f"No implementation for backend '{self.backend_type}'")

    async def close(self) -> None:
        """Shut down the active backend and release resources."""
        if self.backend_type == "webgui":
            from sapwebguimcp.backend.webgui.browser import (  # pylint: disable=import-outside-toplevel
                close_browser_manager,
            )

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
) -> SapUiBackend:
    """Convenience: get a backend instance for the given session.

    This is the primary entry point for all tools.
    """
    manager = get_backend_manager()
    return await manager.get_or_create(session, agent_id, tool_name)


async def close_backend() -> None:
    """Shut down the active backend (called during server shutdown)."""
    if _backend_manager is not None:
        await _backend_manager.close()


def reset_backend_manager() -> None:
    """Reset the singleton (for testing)."""
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    _backend_manager = None
