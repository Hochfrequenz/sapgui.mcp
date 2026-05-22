# unittests/desktop/test_manager_desktop.py
"""Tests for BackendManager desktop backend selection."""

import sys

import pytest

from sapguimcp.backend.manager import BackendManager


@pytest.mark.skipif(sys.platform != "win32", reason="desktop backend requires Windows")
def test_backend_type_accepts_desktop():
    """BackendManager should accept 'desktop' as a valid type."""
    manager = BackendManager(backend_type="desktop")
    assert manager.backend_type == "desktop"


def test_backend_type_rejects_invalid():
    with pytest.raises(ValueError, match="Unknown backend type"):
        BackendManager(backend_type="invalid")  # type: ignore[arg-type]


@pytest.mark.skipif(sys.platform == "win32", reason="only fails on non-Windows")
def test_backend_type_desktop_rejected_on_non_windows():
    """BackendManager should reject 'desktop' on non-Windows platforms."""
    with pytest.raises(RuntimeError, match="requires Windows"):
        BackendManager(backend_type="desktop")
