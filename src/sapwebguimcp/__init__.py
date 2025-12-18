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

__version__ = "0.1.0"

from sapwebguimcp.server import main, mcp

__all__ = ["main", "mcp", "__version__"]
