"""Type definitions for the desktop backend."""

from __future__ import annotations


class ComTreeSnapshot(str):
    """COM element tree snapshot from SAP GUI Scripting (desktop backend).

    Indented text from dump_tree() — Type[Name]: 'text' lines. NOT parseable
    as ARIA. Used for LLM context only, not structured parsing.
    isinstance(x, ComTreeSnapshot) works at runtime.
    """
