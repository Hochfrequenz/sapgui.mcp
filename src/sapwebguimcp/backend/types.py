"""Type definitions for the backend abstraction layer."""

from typing import NewType

AriaSnapshot = NewType("AriaSnapshot", str)
"""
ARIA accessibility tree snapshot from a SAP UI screen.

WebGUI backend: YAML-formatted output from Playwright's page.locator().aria_snapshot().
Future backends may use different snapshot formats with their own NewType aliases.
"""
