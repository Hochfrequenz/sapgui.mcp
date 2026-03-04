"""Backend abstraction layer for SAP UI interaction."""

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
]
