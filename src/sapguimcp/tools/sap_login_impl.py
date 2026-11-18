"""Standalone implementation for sap_login, extracted for testability."""

from typing import Optional

from sapguimcp.backend.manager import get_backend
from sapguimcp.models import LoginResult
from sapguimcp.models.config import get_sap_config

__all__ = ["sap_login_impl"]


async def sap_login_impl(
    url: Optional[str] = None,
    client: Optional[str] = None,
    system_key: Optional[str] = None,
    session_id: Optional[str] = None,
) -> LoginResult:
    """
    Log into SAP.

    Args:
        url: Ignored (the desktop backend connects through the system's ``connection_name``).
        client: SAP client/mandant (3-digit string). If not provided, uses shared config.
        system_key: Dictionary key from systems.json (e.g. "dev-100"). Overrides default_system.
        session_id: Session ID for multi-session support.

    Returns:
        LoginResult indicating login success or what action is needed.
    """
    sap_cfg = get_sap_config()

    effective_key = system_key or sap_cfg.default_system
    system = sap_cfg.systems.get(effective_key)
    if system is None:
        if system_key is not None:
            return LoginResult.failure(
                f"System key {system_key!r} not found in systems.json. "
                f"Available system keys: {list(sap_cfg.systems.keys())}"
            )
        system = sap_cfg.get_default()

    user, password = system.user, system.password.get_secret_value()
    effective_client = client or system.client
    language = system.language

    if not all([user, password, effective_client]):
        return LoginResult.failure(
            "Credentials not configured. Check user/password/client in ~/.config/sap-mcp/systems.json."
        )

    backend = await get_backend(tool_name="sap_login")
    result = await backend.login(
        url=url or "",
        username=user,
        password=password,
        client=effective_client,
        language=language,
        session_id=session_id,
        connection_name=system.connection_name,
    )

    if result.success:
        # Never start keepalive for attached (user-owned) sessions unless the user asks (issue #1009).
        await backend.start_keepalive()

    return result
