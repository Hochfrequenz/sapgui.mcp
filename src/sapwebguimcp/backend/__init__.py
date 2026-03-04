"""Backend abstraction layer for SAP UI interaction."""

from sapwebguimcp.backend.manager import get_backend, get_backend_manager, reset_backend_manager
from sapwebguimcp.backend.protocol import (
    CheckActivateResult,
    SapEditor,
    SapNavigation,
    SapPopup,
    SapUiBackend,
    SapUiInspection,
    SapUiPrimitives,
)
from sapwebguimcp.backend.types import AriaSnapshot

__all__ = [
    "AriaSnapshot",
    "CheckActivateResult",
    "SapEditor",
    "SapNavigation",
    "SapPopup",
    "SapUiBackend",
    "SapUiInspection",
    "SapUiPrimitives",
    "get_backend",
    "get_backend_manager",
    "reset_backend_manager",
]
