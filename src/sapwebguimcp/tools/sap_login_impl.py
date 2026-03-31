"""Standalone implementation for sap_login, extracted for testability."""

from typing import Optional

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.config import get_sap_config, get_settings

__all__ = ["sap_login_impl"]


async def sap_login_impl(
    url: Optional[str] = None,
    client: Optional[str] = None,
    connection_name: Optional[str] = None,
    session_id: Optional[str] = None,
) -> LoginResult:
    """
    Log into SAP.

    Args:
        url: SAP Web GUI URL (WebGUI only). If not provided, derives from shared config or SAP_URL.
        client: SAP client/mandant (3-digit string). If not provided, uses shared config.
        connection_name: SAP Logon entry name (Desktop only, e.g. 'S4U'). Overrides default_system.
        session_id: Session ID for multi-session support.

    Returns:
        LoginResult indicating login success or what action is needed.
    """
    settings = get_settings()
    sap_cfg = get_sap_config()

    effective_connection = connection_name or sap_cfg.default_system
    system = sap_cfg.systems.get(effective_connection) or sap_cfg.get_default()
    user, password = system.user, system.password.get_secret_value()
    effective_client = client or system.client
    effective_url = url or settings.sap_url or (system.host + "/sap/bc/gui/sap/its/webgui")
    language = system.language

    # URL check only applies to WebGUI -- Desktop uses connection_name instead
    if settings.backend_type == "webgui" and not effective_url:
        return LoginResult.failure(
            "No SAP URL provided. Either pass a URL parameter or set SAP_URL, "
            "or configure 'host' in ~/.config/sap-mcp/systems.json."
        )

    if not all([user, password, effective_client]):
        return LoginResult.failure(
            "Credentials not configured. Check user/password/client in ~/.config/sap-mcp/systems.json."
        )

    backend = await get_backend(tool_name="sap_login")
    result = await backend.login(
        url=effective_url or "",
        username=user,
        password=password,
        client=effective_client,
        language=language,
        session_id=session_id,
        connection_name=connection_name,
    )

    if result.success:
        await backend.start_keepalive()

    return result
