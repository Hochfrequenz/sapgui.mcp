"""Backend abstraction layer for SAP UI interaction."""

from sapwebguimcp.backend.manager import close_backend, get_backend, get_backend_manager, reset_backend_manager
from sapwebguimcp.backend.protocol import (
    CheckActivateResult,
    SapEditor,
    SapNavigation,
    SapPopup,
    SapUiBackend,
    SapUiInspection,
    SapUiPrimitives,
)
from sapwebguimcp.backend.types import AriaSnapshot, ComTreeSnapshot, ScreenSnapshot

__all__ = [
    "AriaSnapshot",
    "ComTreeSnapshot",
    "ScreenSnapshot",
    "CheckActivateResult",
    "SapEditor",
    "SapNavigation",
    "SapPopup",
    "SapUiBackend",
    "SapUiInspection",
    "SapUiPrimitives",
    "close_backend",
    "get_backend",
    "get_backend_manager",
    "reset_backend_manager",
]
