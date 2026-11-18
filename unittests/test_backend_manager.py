"""Tests for BackendManager."""

import asyncio
from unittest.mock import MagicMock

from sapguimcp.backend.manager import (
    BackendManager,
    close_backend,
    get_backend_manager,
    reset_backend_manager,
)


def test_backend_manager_is_desktop() -> None:
    """The backend type is fixed to 'desktop'."""
    assert BackendManager().backend_type == "desktop"


def test_get_backend_manager_is_singleton() -> None:
    """get_backend_manager should lazily create one shared manager."""
    reset_backend_manager()
    manager = get_backend_manager()
    assert manager.backend_type == "desktop"
    assert get_backend_manager() is manager
    reset_backend_manager()


def test_close_backend_no_manager() -> None:
    """close_backend should be a no-op when no manager exists."""
    reset_backend_manager()
    asyncio.run(close_backend())  # Should not raise
    reset_backend_manager()


def test_backend_manager_close_clears_caches_and_stops_com_thread() -> None:
    """BackendManager.close() should clear the cache and shut down the COM thread."""
    manager = BackendManager()
    manager._backends["desktop"] = "fake_backend"  # type: ignore[assignment]
    com_thread = MagicMock()
    manager._com_thread = com_thread

    asyncio.run(manager.close())

    com_thread.shutdown.assert_called_once()
    assert manager._backends == {}
