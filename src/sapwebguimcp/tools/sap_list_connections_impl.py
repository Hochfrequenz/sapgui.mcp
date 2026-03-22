"""Standalone implementation for sap_list_connections."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.base import ToolResult
from pydantic import Field

__all__ = ["sap_list_connections_impl", "_parse_landscape_xml"]


class ConnectionListResult(ToolResult):
    """Result from sap_list_connections tool."""

    connections: list[dict[str, Any]] = Field(default_factory=list)


def _find_landscape_path() -> Path | None:
    """Find SAPUILandscape.xml via registry or default location."""
    if sys.platform == "win32":
        try:
            import winreg  # pylint: disable=import-outside-toplevel,import-error

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SAP\SAPLogon\Options") as key:
                path, _ = winreg.QueryValueEx(key, "LandscapeFile")
                p = Path(path)
                if p.is_file():
                    return p
        except OSError:
            pass

    default = Path.home() / "AppData" / "Roaming" / "SAP" / "Common" / "SAPUILandscape.xml"
    if default.is_file():
        return default
    return None


def _parse_landscape_xml(xml_text: str) -> list[dict[str, Any]]:
    """Parse SAPUILandscape XML and return connection entries."""
    root = ET.fromstring(xml_text)
    services = root.find("Services")
    if services is None:
        return []

    result = []
    for svc in services.findall("Service"):
        entry: dict[str, Any] = {
            "name": svc.get("name", ""),
            "type": svc.get("type", ""),
            "systemid": svc.get("systemid", ""),
            "server": svc.get("server", ""),
            "client": svc.get("client", ""),
            "description": svc.get("description", ""),
        }
        result.append(entry)
    return result


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
