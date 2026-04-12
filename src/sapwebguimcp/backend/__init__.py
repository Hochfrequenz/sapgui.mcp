"""Backend abstraction layer for SAP UI interaction."""

from sapwebguimcp.backend.desktop.types import ComTreeSnapshot
from sapwebguimcp.backend.manager import (
    close_backend,
    get_backend,
    get_backend_manager,
    get_desktop_backend,
    get_webgui_backend,
    reset_backend_manager,
)
from sapwebguimcp.backend.types import CheckActivateResult
from sapwebguimcp.backend.webgui.types import AriaSnapshot

__all__ = [
    "AriaSnapshot",
    "ComTreeSnapshot",
    "CheckActivateResult",
    "close_backend",
    "get_backend",
    "get_backend_manager",
    "get_desktop_backend",
    "get_webgui_backend",
    "reset_backend_manager",
]
