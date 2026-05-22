"""Standalone implementation for sap_list_connections."""

from typing import Any

from pydantic import Field

from sapguimcp.backend.desktop._landscape import _find_landscape_path, _parse_landscape_xml
from sapguimcp.backend.manager import get_backend
from sapguimcp.models.base import ToolResult
from sapguimcp.models.config import get_sap_config

__all__ = ["sap_list_connections_impl", "_parse_landscape_xml"]


class ConnectionListResult(ToolResult):
    """Result from sap_list_connections tool."""

    connections: list[dict[str, Any]] = Field(default_factory=list)
    configured_systems: list[dict[str, str]] = Field(default_factory=list)


def _get_configured_systems() -> list[dict[str, str]]:
    """Return systems from systems.json without sensitive fields."""
    try:
        sap_cfg = get_sap_config()
    except (FileNotFoundError, ValueError):
        return []
    result = []
    for key, system in sap_cfg.systems.items():
        result.append(
            {
                "key": key,
                "sap_logon_entry": system.connection_name,
                "host": system.host,
                "client": system.client,
                "language": system.language,
            }
        )
    return result


async def sap_list_connections_impl() -> ConnectionListResult:
    """List available SAP Logon connections from the landscape file or backend."""
    configured_systems = _get_configured_systems()
    try:
        backend = await get_backend(tool_name="sap_list_connections")
        connections = await backend.list_connections()
        return ConnectionListResult(
            success=True,
            connections=connections,
            configured_systems=configured_systems,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Fall back to reading the landscape file directly
        path = _find_landscape_path()
        if path is None:
            return ConnectionListResult(
                success=True,
                connections=[],
                configured_systems=configured_systems,
            )
        connections = _parse_landscape_xml(path.read_text(encoding="utf-8"))
        return ConnectionListResult(
            success=True,
            connections=connections,
            configured_systems=configured_systems,
        )
