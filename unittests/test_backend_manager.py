"""Tests for BackendManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapwebguimcp.backend.manager import BackendManager, get_backend_manager, reset_backend_manager


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
