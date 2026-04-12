"""Type definitions for the WebGUI backend."""

from __future__ import annotations


class AriaSnapshot(str):
    """ARIA accessibility tree snapshot from Playwright (WebGUI backend).

    YAML-formatted output from page.locator().aria_snapshot(). Parsers under
    backend/webgui/parsers/ accept this type and rely on its ARIA structure.
    isinstance(x, AriaSnapshot) works at runtime.
    """
