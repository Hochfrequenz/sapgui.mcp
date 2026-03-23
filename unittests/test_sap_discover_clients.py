"""Unit tests for sap_discover_clients tool."""

from unittest.mock import AsyncMock, patch

import pytest

_PATCH_GET_BACKEND = "sapwebguimcp.tools.sap_discover_clients_impl.get_backend"
_PATCH_GET_SETTINGS = "sapwebguimcp.tools.sap_discover_clients_impl.get_settings"


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
            result = await sap_discover_clients_impl("HFQ")

        backend.discover_clients.assert_called_once_with("HFQ")
        assert result.success is True
        assert result.session_id == "s1"
        assert result.default_client == "100"
        assert result.clients == [{"id": "100", "description": "Produktion"}]
        assert result.connection_name == "HFQ"

    @pytest.mark.anyio
    async def test_uses_settings_when_no_connection_name(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        backend = AsyncMock()
        backend.discover_clients.return_value = {
            "session_id": "s1",
            "default_client": "100",
            "clients": [],
            "info_text": "",
        }

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            with patch(_PATCH_GET_SETTINGS) as mock_settings:
                mock_settings.return_value.sap_connection_name = "HFQ"
                result = await sap_discover_clients_impl(None)

        backend.discover_clients.assert_called_once_with("HFQ")
        assert result.success is True

    @pytest.mark.anyio
    async def test_returns_failure_when_no_connection_configured(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        with patch(_PATCH_GET_SETTINGS) as mock_settings:
            mock_settings.return_value.sap_connection_name = ""
            result = await sap_discover_clients_impl(None)

        assert result.success is False
        assert "connection" in result.error.lower()

    @pytest.mark.anyio
    async def test_returns_failure_on_backend_exception(self) -> None:
        from sapwebguimcp.tools.sap_discover_clients_impl import sap_discover_clients_impl

        backend = AsyncMock()
        backend.discover_clients.side_effect = RuntimeError("SAP not running")

        with patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)):
            result = await sap_discover_clients_impl("HFQ")

        assert result.success is False
        assert "SAP not running" in result.error
