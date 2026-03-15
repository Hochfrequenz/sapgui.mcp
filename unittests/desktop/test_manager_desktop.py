# unittests/desktop/test_manager_desktop.py
"""Tests for BackendManager desktop backend selection."""

from unittest.mock import MagicMock, patch

import pytest

from sapwebguimcp.backend.manager import BackendManager


def test_backend_type_accepts_desktop():
    """BackendManager should accept 'desktop' as a valid type."""
    manager = BackendManager(backend_type="desktop")
    assert manager.backend_type == "desktop"


def test_backend_type_rejects_invalid():
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="invalid")  # type: ignore[arg-type]
