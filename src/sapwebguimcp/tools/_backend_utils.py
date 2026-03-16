"""Shared backend detection utilities for transaction tools."""

from sapwebguimcp.backend.protocol import SapUiBackend


def _is_desktop_backend(backend: SapUiBackend) -> bool:
    """Check if we're using the desktop (COM) backend."""
    try:
        from sapwebguimcp.backend.desktop import DesktopBackend  # pylint: disable=import-outside-toplevel

        return isinstance(backend, DesktopBackend)
    except ImportError:
        return False
