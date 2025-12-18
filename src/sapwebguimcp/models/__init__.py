"""
Data models for SAP Web GUI MCP Server.

This module contains Pydantic models and configuration classes.
"""

from sapwebguimcp.models.browser import (
    BrowserManager,
    close_browser_manager,
    get_browser_manager,
)
from sapwebguimcp.models.config import (
    BrowserMode,
    BrowserType,
    SapWebGuiSettings,
    get_settings,
)

__all__ = [
    # Config models
    "BrowserMode",
    "BrowserType",
    "SapWebGuiSettings",
    "get_settings",
    # Browser manager
    "BrowserManager",
    "get_browser_manager",
    "close_browser_manager",
]
