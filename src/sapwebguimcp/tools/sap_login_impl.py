"""Standalone implementation for sap_login, extracted for testability."""

from typing import Optional

from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.config import get_settings

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
        url: SAP Web GUI URL (WebGUI only). If not provided, uses SAP_URL from environment.
        client: SAP client/mandant (3-digit string). If not provided, uses SAP_MANDANT from environment.
        connection_name: SAP Logon entry name (Desktop only, e.g. 'S4U'). Overrides SAP_CONNECTION_NAME.
        session_id: Session ID for multi-session support.

    Returns:
        LoginResult indicating login success or what action is needed.
    """
    settings = get_settings()
    effective_url = url or settings.sap_url
    effective_client = client or settings.sap_mandant

    # URL check only applies to WebGUI — Desktop uses SAP_CONNECTION_NAME instead
    if settings.backend_type == "webgui" and not effective_url:
        return LoginResult.failure(
            "No SAP URL provided. Either pass a URL parameter or set the SAP_URL environment variable."
        )

    if not all([settings.sap_user, settings.sap_password, effective_client]):
        return LoginResult.failure("Credentials not configured (SAP_USER, SAP_PASSWORD, SAP_MANDANT).")

    backend = await get_backend(tool_name="sap_login")
    result = await backend.login(
        url=effective_url or "",
        username=settings.sap_user,
        password=settings.sap_password,
        client=effective_client,
        language=settings.sap_language,
        session_id=session_id,
        connection_name=connection_name,
    )

    if result.success:
        await backend.start_keepalive()

    return result
