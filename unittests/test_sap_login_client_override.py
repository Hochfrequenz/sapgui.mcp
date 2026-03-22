"""Unit tests for sap_login optional client override."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapwebguimcp.models.sap_results import LoginResult

_PATCH_GET_BACKEND = "sapwebguimcp.tools.sap_login_impl.get_backend"
_PATCH_GET_SETTINGS = "sapwebguimcp.tools.sap_login_impl.get_settings"


def _make_settings(mandant: str = "100") -> MagicMock:
    settings = MagicMock()
    settings.backend_type = "desktop"
    settings.sap_user = "testuser"
    settings.sap_password = "testpass"
    settings.sap_mandant = mandant
    settings.sap_language = "DE"
    settings.sap_url = ""
    return settings


def _make_backend(login_result: LoginResult | None = None) -> AsyncMock:
    backend = AsyncMock()
    backend.login.return_value = login_result or LoginResult(success=True, user="testuser")
    backend.start_keepalive.return_value = None
    return backend


class TestSapLoginClientOverride:
    """sap_login uses SAP_MANDANT by default but accepts an optional client override."""

    @pytest.mark.anyio
    async def test_uses_settings_mandant_by_default(self) -> None:
        """When no client arg given, login uses SAP_MANDANT from settings."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        settings = _make_settings(mandant="100")
        backend = _make_backend()

        with patch(_PATCH_GET_SETTINGS, return_value=settings), patch(
            _PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)
        ):
            await sap_login(client=None)

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["client"] == "100"

    @pytest.mark.anyio
    async def test_client_param_overrides_settings_mandant(self) -> None:
        """When client arg is provided, it overrides SAP_MANDANT from settings."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        settings = _make_settings(mandant="100")
        backend = _make_backend()

        with patch(_PATCH_GET_SETTINGS, return_value=settings), patch(
            _PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)
        ):
            await sap_login(client="200")

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["client"] == "200"


class TestSapLoginConnectionNameOverride:
    """sap_login uses SAP_CONNECTION_NAME by default but accepts an optional connection_name override."""

    @pytest.mark.anyio
    async def test_passes_none_when_no_connection_name_given(self) -> None:
        """When no connection_name arg given, None is forwarded to backend (backend resolves from settings)."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        settings = _make_settings()
        settings.sap_connection_name = "HFQ"
        backend = _make_backend()

        with patch(_PATCH_GET_SETTINGS, return_value=settings), patch(
            _PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)
        ):
            await sap_login(connection_name=None)

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] is None

    @pytest.mark.anyio
    async def test_connection_name_param_overrides_settings(self) -> None:
        """When connection_name arg is provided, it overrides SAP_CONNECTION_NAME from settings."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        settings = _make_settings()
        settings.sap_connection_name = "HFQ"
        backend = _make_backend()

        with patch(_PATCH_GET_SETTINGS, return_value=settings), patch(
            _PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)
        ):
            await sap_login(connection_name="S4U")

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "S4U"
