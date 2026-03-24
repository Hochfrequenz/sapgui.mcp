"""Standalone implementation for sap_list_connections."""

from typing import Any

from pydantic import Field

from sapwebguimcp.backend.desktop._landscape import _find_landscape_path, _parse_landscape_xml
from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.base import ToolResult

__all__ = ["sap_list_connections_impl", "_parse_landscape_xml"]


class ConnectionListResult(ToolResult):
    """Result from sap_list_connections tool."""

    connections: list[dict[str, Any]] = Field(default_factory=list)


async def sap_list_connections_impl() -> ConnectionListResult:
    """List available SAP Logon connections from the landscape file or backend."""
    try:
        backend = await get_backend(tool_name="sap_list_connections")
        connections = await backend.list_connections()
        return ConnectionListResult(success=True, connections=connections)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Fall back to reading the landscape file directly
        path = _find_landscape_path()
        if path is None:
            return ConnectionListResult.failure(f"Could not find SAPUILandscape.xml: {e}")
        connections = _parse_landscape_xml(path.read_text(encoding="utf-8"))
        return ConnectionListResult(success=True, connections=connections)
