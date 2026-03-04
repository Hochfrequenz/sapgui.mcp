"""Tests for BackendManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapwebguimcp.backend.manager import BackendManager
from sapwebguimcp.backend.webgui.backend import WebGuiBackend


def test_backend_manager_default_type() -> None:
    """Default backend type should be 'webgui'."""
    manager = BackendManager()
    assert manager.backend_type == "webgui"


def test_backend_manager_unknown_type_raises() -> None:
    """Unknown backend type should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="unknown")
