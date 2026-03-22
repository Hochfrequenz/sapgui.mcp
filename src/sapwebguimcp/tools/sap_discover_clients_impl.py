"""Standalone implementation for sap_discover_clients."""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.base import ToolResult
from sapwebguimcp.models.config import get_settings

__all__ = ["DiscoverClientsResult", "parse_clients_from_login_info", "sap_discover_clients_impl"]

# Matches lines like "  100  Produktionsmandant" or "100 Production"
_CLIENT_RE = re.compile(r"^\s*(\d{3})\s+(.+?)\s*$")


class DiscoverClientsResult(ToolResult):
    """Result from sap_discover_clients tool."""

    session_id: str | None = Field(default=None, description="Session ID of the open login screen (reuse for sap_login)")
    default_client: str = Field(default="", description="Client pre-filled on the login screen")
    clients: list[dict[str, Any]] = Field(default_factory=list, description="Available clients from login screen info text")
    connection_name: str = Field(default="", description="SAP connection name used")
    info_text: str = Field(default="", description="Raw information text from the login screen")


def parse_clients_from_login_info(text: str) -> list[dict[str, str]]:
    """Parse client list from SAP login screen information text.

    Looks for lines matching ``NNN  description`` where NNN is a 3-digit
    client number.  Returns a list of ``{"id": ..., "description": ...}``
    dicts.
    """
    result = []
    for line in text.splitlines():
        m = _CLIENT_RE.match(line)
        if m:
            result.append({"id": m.group(1), "description": m.group(2)})
    return result


async def sap_discover_clients_impl(connection_name: str | None) -> DiscoverClientsResult:
    """Open a SAP connection and return available clients from the login screen.

    Leaves the session open at the login screen.  The returned ``session_id``
    can be passed to ``sap_login`` to skip re-opening the connection.
    """
    settings = get_settings()
    effective_connection = connection_name or settings.sap_connection_name
    if not effective_connection:
        return DiscoverClientsResult.failure("No connection_name specified and SAP_CONNECTION_NAME not configured")

    try:
        backend = await get_backend(tool_name="sap_discover_clients")
        data = await backend.discover_clients(effective_connection)
        return DiscoverClientsResult(
            success=True,
            session_id=data.get("session_id"),
            default_client=data.get("default_client", ""),
            clients=data.get("clients", []),
            connection_name=effective_connection,
            info_text=data.get("info_text", ""),
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        return DiscoverClientsResult.failure(str(e))
