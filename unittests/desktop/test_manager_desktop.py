# unittests/desktop/test_manager_desktop.py
"""Tests for BackendManager: the server always uses the desktop backend."""

import sys

import pytest

from sapguimcp.backend.manager import BackendManager


def test_backend_manager_is_desktop():
    """BackendManager has no backend selection: it is always the desktop backend."""
    assert BackendManager().backend_type == "desktop"


@pytest.mark.anyio
@pytest.mark.skipif(sys.platform == "win32", reason="only fails on non-Windows")
async def test_get_or_create_rejected_on_non_windows():
    """The desktop backend is rejected on non-Windows platforms."""
    with pytest.raises(RuntimeError, match="requires Windows"):
        await BackendManager().get_or_create()
