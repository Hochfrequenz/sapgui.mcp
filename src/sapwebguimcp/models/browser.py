"""Backward-compatibility shim — canonical location is ``backend.webgui.browser``.

All symbols are re-exported so existing ``from sapwebguimcp.models.browser import …``
continues to work and resolves to the **same** module-level singletons.
"""

from sapwebguimcp.backend.webgui.browser import (  # noqa: F401  -- re-export
    BrowserManager,
    close_browser_manager,
    get_browser_manager,
)

__all__ = [
    "BrowserManager",
    "get_browser_manager",
    "close_browser_manager",
]
