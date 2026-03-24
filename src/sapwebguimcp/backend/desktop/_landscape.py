"""Landscape XML parsing — find and parse SAPUILandscape.xml."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

__all__ = ["_find_landscape_path", "_parse_landscape_xml"]


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
