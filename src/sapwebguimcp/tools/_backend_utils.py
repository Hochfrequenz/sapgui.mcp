"""Shared backend detection utilities for transaction tools."""

from sapwebguimcp.backend.protocol import SapUiBackend


def _is_desktop_backend(backend: SapUiBackend) -> bool:
    """Check if we're using the desktop (COM) backend."""
    return backend.backend_type == "desktop"
