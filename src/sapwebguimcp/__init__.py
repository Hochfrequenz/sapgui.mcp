"""
SAP Web GUI MCP Server - Browser automation for SAP Web GUI via Model Context Protocol.

This package provides an MCP server that enables Claude and other AI assistants
to interact with SAP Web GUI through browser automation.

Example usage with Claude Code:
    1. Configure the MCP server in your claude settings
    2. Ask Claude to login to SAP and run transactions

For extending with new tools, see: src/sapwebguimcp/server.py
For creating skills, see: src/sapwebguimcp/skills/README.md
"""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

# Lazy imports to avoid RuntimeWarning when running `python -m sapwebguimcp.server`
# The warning occurs because __init__.py imports server before runpy executes it as __main__
if TYPE_CHECKING:
    from sapwebguimcp.server import main, mcp


def __getattr__(name: str) -> object:
    """Lazy import for main and mcp to avoid early server import."""
    if name in ("main", "mcp"):
        # Import inside function to defer loading until actually needed.
        # If we import at module level, running `python -m sapwebguimcp.server`
        # causes a RuntimeWarning because this __init__.py loads server.py
        # BEFORE runpy can execute it as __main__.
        from sapwebguimcp import server  # pylint: disable=import-outside-toplevel

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["main", "mcp", "__version__"]
