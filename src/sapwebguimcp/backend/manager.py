"""Backend manager — singleton entry point for tools."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sapwebguimcp.backend.webgui.backend import WebGuiBackend

if TYPE_CHECKING:
    from sapwebguimcp.backend.protocol import SapUiBackend

logger = logging.getLogger(__name__)

_VALID_BACKEND_TYPES = {"webgui"}


class BackendManager:  # pylint: disable=too-few-public-methods
    """Manages SapUiBackend instances across sessions.

    Wraps the existing BrowserManager/SessionRegistry for WebGUI.
    """

    def __init__(self, backend_type: str = "webgui") -> None:
        if backend_type not in _VALID_BACKEND_TYPES:
            raise ValueError(f"Unknown backend type '{backend_type}'. Valid types: {_VALID_BACKEND_TYPES}")
        self.backend_type = backend_type
        self._backends: dict[str, SapUiBackend] = {}  # Cache by session ID
        self._page_ids: dict[str, int] = {}  # Track page identity for cache invalidation

    async def get_or_create(
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
        raise ValueError(f"No implementation for backend '{self.backend_type}'")


# -- Singleton --

_backend_manager: BackendManager | None = None  # pylint: disable=invalid-name


def get_backend_manager() -> BackendManager:
    """Get the global BackendManager singleton (lazy init)."""
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    if _backend_manager is None:
        _backend_manager = BackendManager(backend_type="webgui")
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


def reset_backend_manager() -> None:
    """Reset the singleton (for testing)."""
    global _backend_manager  # noqa: PLW0603  # pylint: disable=global-statement
    _backend_manager = None
