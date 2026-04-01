"""Unit tests for system selection: system_key resolution and server instructions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from sap_mcp_config import Config, SAPSystem

from sapwebguimcp.models.sap_results import LoginResult

_PATCH_GET_BACKEND = "sapwebguimcp.tools.sap_login_impl.get_backend"
_PATCH_GET_SETTINGS = "sapwebguimcp.tools.sap_login_impl.get_settings"
_PATCH_GET_SAP_CONFIG = "sapwebguimcp.tools.sap_login_impl.get_sap_config"


def _multi_system_config() -> Config:
    """Config with two systems sharing the same host but different clients."""
    return Config(
        default_system="dev-100",
        systems={
            "dev-100": SAPSystem(
                connection_name="DEV - ERP Development",
                host="https://dev-sap.example.com:44300",
                client="100",
                user="dev_user",
                password=SecretStr("dev_pass"),
                language="DE",
            ),
            "dev-200": SAPSystem(
                connection_name="DEV - ERP Development",
                host="https://dev-sap.example.com:44300",
                client="200",
                user="qa_user",
                password=SecretStr("qa_pass"),
                language="EN",
            ),
        },
    )


def _make_settings(backend_type: str = "desktop") -> MagicMock:
    settings = MagicMock()
    settings.backend_type = backend_type
    settings.sap_url = ""
    return settings


def _make_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.login.return_value = LoginResult(success=True, user="test")
    backend.start_keepalive.return_value = None
    return backend


class TestSystemKeyResolution:
    """sap_login resolves system_key to SAP Logon entry and passes it to the backend."""

    @pytest.mark.anyio
    async def test_default_system_uses_sap_logon_entry(self) -> None:
        """Default system's SAP Logon entry is passed to backend, not the dict key."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl()

        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"
        assert kwargs["client"] == "100"
        assert kwargs["username"] == "dev_user"

    @pytest.mark.anyio
    async def test_explicit_key_resolves_to_sap_logon_entry(self) -> None:
        """Passing a system_key resolves to that system's SAP Logon entry."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl(system_key="dev-200")

        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"
        assert kwargs["client"] == "200"
        assert kwargs["username"] == "qa_user"

    @pytest.mark.anyio
    async def test_same_sap_logon_entry_different_clients(self) -> None:
        """Two system keys sharing the same SAP Logon entry but different clients work correctly."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()

        for key, expected_client in [("dev-100", "100"), ("dev-200", "200")]:
            backend = _make_backend()
            with (
                patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
                patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
                patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
            ):
                await sap_login_impl(system_key=key)

            _, kwargs = backend.login.call_args
            assert kwargs["connection_name"] == "DEV - ERP Development"
            assert kwargs["client"] == expected_client

    @pytest.mark.anyio
    async def test_webgui_backend_receives_sap_logon_entry(self) -> None:
        """WebGUI backend also receives the SAP Logon entry (even though it ignores it)."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()
        backend = _make_backend()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("webgui")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
            patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        ):
            await sap_login_impl(system_key="dev-200")

        _, kwargs = backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"

    @pytest.mark.anyio
    async def test_unknown_system_key_returns_error(self) -> None:
        """Passing an unknown system_key returns a failure instead of silently falling back."""
        from sapwebguimcp.tools.sap_login_impl import sap_login_impl

        cfg = _multi_system_config()

        with (
            patch(_PATCH_GET_SETTINGS, return_value=_make_settings("desktop")),
            patch(_PATCH_GET_SAP_CONFIG, return_value=cfg),
        ):
            result = await sap_login_impl(system_key="nonexistent")

        assert result.success is False
        assert "nonexistent" in result.error
        assert "dev-100" in result.error


class TestServerInstructions:
    """Server instructions include available system keys so the LLM can offer choices."""

    def test_instructions_contain_system_keys(self) -> None:
        from sapwebguimcp.server import _build_instructions

        cfg = _multi_system_config()
        with patch("sapwebguimcp.server.get_sap_config", return_value=cfg):
            instructions = _build_instructions()

        assert "dev-100" in instructions
        assert "dev-200" in instructions
        assert "Default: 'dev-100'" in instructions

    def test_instructions_mention_choose_tool(self) -> None:
        from sapwebguimcp.server import _build_instructions

        cfg = _multi_system_config()
        with patch("sapwebguimcp.server.get_sap_config", return_value=cfg):
            instructions = _build_instructions()

        assert "choose" in instructions

    def test_instructions_graceful_when_config_missing(self) -> None:
        from sapwebguimcp.server import _build_instructions

        with patch("sapwebguimcp.server.get_sap_config", side_effect=FileNotFoundError):
            instructions = _build_instructions()

        assert "AVAILABLE SYSTEMS" not in instructions
        assert "sap_login" in instructions  # base instructions still present
