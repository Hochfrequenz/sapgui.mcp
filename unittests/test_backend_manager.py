"""Tests for BackendManager."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from sapwebguimcp.backend.manager import (
    BackendManager,
    close_backend,
    get_backend_manager,
    reset_backend_manager,
)


def test_backend_manager_default_type() -> None:
    """Default backend type should be 'webgui'."""
    manager = BackendManager()
    assert manager.backend_type == "webgui"


def test_backend_manager_unknown_type_raises() -> None:
    """Unknown backend type should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="unknown")  # type: ignore[arg-type]


def test_get_backend_manager_reads_settings() -> None:
    """get_backend_manager should read backend_type from settings."""
    reset_backend_manager()
    manager = get_backend_manager()
    assert manager.backend_type == "webgui"
    reset_backend_manager()


def test_close_backend_no_manager() -> None:
    """close_backend should be a no-op when no manager exists."""
    reset_backend_manager()
    asyncio.run(close_backend())  # Should not raise
    reset_backend_manager()


def test_backend_manager_close_clears_caches() -> None:
    """BackendManager.close() should clear internal caches and call close_browser_manager."""
    manager = BackendManager()
    # Simulate cached state
    manager._backends["s1"] = "fake_backend"  # type: ignore[assignment]
    manager._page_ids["s1"] = 12345

    with patch(
        "sapwebguimcp.backend.webgui.browser.close_browser_manager",
        new_callable=AsyncMock,
    ) as mock_close:
        asyncio.run(manager.close())
        mock_close.assert_called_once()

    assert manager._backends == {}
    assert manager._page_ids == {}
