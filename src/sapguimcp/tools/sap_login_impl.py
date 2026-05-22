"""Standalone implementation for sap_login, extracted for testability."""

from typing import Optional

from sapguimcp.backend.manager import get_backend
from sapguimcp.models import LoginResult
from sapguimcp.models.config import get_sap_config, get_settings

__all__ = ["sap_login_impl"]

# WebGUI ICF service path appended to a system's host to form the login URL.
_WEBGUI_PATH = "/sap/bc/gui/sap/its/webgui"


def _webgui_url_from_host(host: str) -> str:
    """Return the WebGUI login URL for *host*, or ``""`` if *host* is empty."""
    return f"{host}{_WEBGUI_PATH}" if host else ""


async def sap_login_impl(
    url: Optional[str] = None,
    client: Optional[str] = None,
    system_key: Optional[str] = None,
    session_id: Optional[str] = None,
) -> LoginResult:
    """
    Log into SAP.

    Args:
        url: SAP Web GUI URL (WebGUI only). If not provided, derives from the
            selected system's ``host`` in systems.json, falling back to ``SAP_URL``.
        client: SAP client/mandant (3-digit string). If not provided, uses shared config.
        system_key: Dictionary key from systems.json (e.g. "dev-100"). Overrides default_system.
        session_id: Session ID for multi-session support.

    Returns:
        LoginResult indicating login success or what action is needed.
    """
    settings = get_settings()
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
    # systems.json is the source of truth: when the chosen system has a host
    # configured we use it. ``settings.sap_url`` (legacy ``SAP_URL`` env var)
    # is only a fallback for systems with no ``host`` set, otherwise it would
    # silently override a non-default ``system_key`` and route the user to the
    # default system instead (issue #659).
    effective_url = url or _webgui_url_from_host(system.host) or settings.sap_url
    language = system.language

    # URL check only applies to WebGUI -- Desktop uses the SAP Logon entry instead
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
        connection_name=system.connection_name,
    )

    if result.success:
        await backend.start_keepalive()

    return result
