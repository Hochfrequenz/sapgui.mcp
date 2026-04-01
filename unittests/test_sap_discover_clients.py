"""Unit tests for sap_discover_clients tool."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr
from sap_mcp_config import Config, SAPSystem

_PATCH_GET_BACKEND = "sapwebguimcp.tools.sap_discover_clients_impl.get_backend"
_PATCH_GET_SAP_CONFIG = "sapwebguimcp.tools.sap_discover_clients_impl.get_sap_config"


def _make_sap_config(default_system: str = "HFQ") -> Config:
    return Config(
        default_system=default_system,
        systems={
            default_system: SAPSystem(
                host="https://sap.example.com",
                client="100",
                user="testuser",
                password=SecretStr("testpass"),
                language="DE",
            ),
        },
    )


class TestSapDiscoverClientsImpl:
    """sap_discover_clients_impl calls backend.discover_clients and wraps the result."""

    @pytest.mark.anyio
    async def test_calls_backend_with_connection_name(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        backend = AsyncMock()
        backend.discover_clients.return_value = {
            "session_id": "s1",
            "default_client": "100",
            "clients": [{"id": "100", "description": "Produktion"}],
            "info_text": "100 Produktion",
        }

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            with patch(_PATCH_GET_SAP_CONFIG, return_value=_make_sap_config()):
                result = await sap_discover_clients_impl("HFQ")

        backend.discover_clients.assert_called_once_with("HFQ")
        assert result.success is True
        assert result.session_id == "s1"
        assert result.default_client == "100"
        assert result.clients == [{"id": "100", "description": "Produktion"}]
        assert result.connection_name == "HFQ"

    @pytest.mark.anyio
    async def test_uses_default_system_when_no_connection_name(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        backend = AsyncMock()
        backend.discover_clients.return_value = {
            "session_id": "s1",
            "default_client": "100",
            "clients": [],
            "info_text": "",
        }

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            with patch(_PATCH_GET_SAP_CONFIG, return_value=_make_sap_config("HFQ")):
                result = await sap_discover_clients_impl(None)

        backend.discover_clients.assert_called_once_with("HFQ")
        assert result.success is True

    @pytest.mark.anyio
    async def test_returns_failure_when_no_connection_configured(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        cfg = Config(
            default_system="",
            systems={"": SAPSystem(host="https://x.com", user="u", password=SecretStr("p"))},
        )
        with patch(_PATCH_GET_SAP_CONFIG, return_value=cfg):
            result = await sap_discover_clients_impl(None)

        assert result.success is False
        assert "connection" in result.error.lower() or "default" in result.error.lower()

    @pytest.mark.anyio
    async def test_returns_failure_on_backend_exception(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        backend = AsyncMock()
        backend.discover_clients.side_effect = RuntimeError("SAP not running")

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            with patch(_PATCH_GET_SAP_CONFIG, return_value=_make_sap_config()):
                result = await sap_discover_clients_impl("HFQ")

        assert result.success is False
        assert "SAP not running" in result.error
