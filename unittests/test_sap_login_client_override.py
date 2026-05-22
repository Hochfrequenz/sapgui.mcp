"""Unit tests for sap_login optional client override."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from sap_mcp_config import Config, SAPSystem

from sapguimcp.models.sap_results import LoginResult

_PATCH_GET_BACKEND = "sapguimcp.tools.sap_login_impl.get_backend"
_PATCH_GET_SETTINGS = "sapguimcp.tools.sap_login_impl.get_settings"
_PATCH_GET_SAP_CONFIG = "sapguimcp.tools.sap_login_impl.get_sap_config"


def _make_sap_config(default_system: str = "HFQ", client: str = "100", connection_name: str = "HF S/4") -> Config:
    return Config(
        default_system=default_system,
        systems={
            default_system: SAPSystem(
                connection_name=connection_name,
                host="https://sap.example.com",
                client=client,
                user="testuser",
                password=SecretStr("testpass"),
                language="DE",
            ),
        },
    )


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.backend_type = "desktop"
    settings.sap_url = ""
    return settings


def _make_backend(login_result: LoginResult | None = None) -> AsyncMock:
    backend = AsyncMock()
    backend.login.return_value = login_result or LoginResult(success=True, user="testuser")
    backend.start_keepalive.return_value = None
    return backend


class TestSapLoginClientOverride:
    """sap_login uses shared config client by default but accepts an optional client override."""

    @pytest.mark.anyio
    async def test_uses_config_client_by_default(self) -> None:
        """When no client arg given, login uses client from shared config."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        sap_cfg = _make_sap_config(client="100")
        settings = _make_settings()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=sap_cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login(client=None)

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["client"] == "100"

    @pytest.mark.anyio
    async def test_client_param_overrides_config_client(self) -> None:
        """When client arg is provided, it overrides client from shared config."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        sap_cfg = _make_sap_config(client="100")
        settings = _make_settings()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=sap_cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login(client="200")

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["client"] == "200"


class TestSapLoginSystemKeyOverride:
    """sap_login uses default_system by default but accepts an optional system_key override."""

    @pytest.mark.anyio
    async def test_uses_default_system_sap_logon_entry(self) -> None:
        """When no system_key given, default system's SAP Logon entry is passed to backend."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        sap_cfg = _make_sap_config(default_system="HFQ", connection_name="HF S/4")
        settings = _make_settings()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=sap_cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login(system_key=None)

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "HF S/4"

    @pytest.mark.anyio
    async def test_system_key_param_overrides_default(self) -> None:
        """When system_key is provided, it selects that system instead of default_system."""
        from sapguimcp.tools.sap_login_impl import sap_login_impl as sap_login

        sap_cfg = Config(
            default_system="HFQ",
            systems={
                "HFQ": SAPSystem(
                    connection_name="HF S/4",
                    host="https://sap.example.com",
                    client="100",
                    user="testuser",
                    password=SecretStr("testpass"),
                    language="DE",
                ),
                "S4U": SAPSystem(
                    connection_name="S4 Utility",
                    host="https://s4u.example.com",
                    client="200",
                    user="s4user",
                    password=SecretStr("s4pass"),
                    language="EN",
                ),
            },
        )
        settings = _make_settings()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=settings),
            patch(_PATCH_GET_SAP_CONFIG, return_value=sap_cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login(system_key="S4U")

        backend.login.assert_called_once()
        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "S4 Utility"
        assert kwargs["username"] == "s4user"
        assert kwargs["client"] == "200"
