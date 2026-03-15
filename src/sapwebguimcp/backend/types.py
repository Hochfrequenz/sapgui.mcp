"""Type definitions for the backend abstraction layer."""

from typing import NewType, Union

AriaSnapshot = NewType("AriaSnapshot", str)
"""ARIA accessibility tree snapshot from Playwright (WebGUI backend).

YAML-formatted output from page.locator().aria_snapshot(). Parsers under
backend/webgui/parsers/ accept this type and rely on its ARIA structure.
"""

ComTreeSnapshot = NewType("ComTreeSnapshot", str)
"""COM element tree snapshot from SAP GUI Scripting (desktop backend).

Indented text from dump_tree() — Type[Name]: 'text' lines. NOT parseable
as ARIA. Used for LLM context only, not structured parsing.
"""

ScreenSnapshot = Union[AriaSnapshot, ComTreeSnapshot]
"""Union type returned by get_snapshot() — backend determines the format.

WebGUI returns AriaSnapshot, desktop returns ComTreeSnapshot. Tools that
pass snapshots to the LLM should accept ScreenSnapshot. Parsers that need
a specific format should accept the concrete type (AriaSnapshot).
"""
