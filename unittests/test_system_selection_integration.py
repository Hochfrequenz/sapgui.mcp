"""Integration tests for system selection through the MCP protocol.

These tests exercise the full stack: config → server → MCP protocol → tool invocation,
with the SAP backend mocked at the boundary.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from pydantic import SecretStr
from sap_mcp_config import Config, SAPSystem

from sapguimcp.models.sap_results import LoginResult


def _multi_system_config() -> Config:
    return Config(
        default_system="dev",
        systems={
            "dev": SAPSystem(
                connection_name="DEV - ERP Development",
                host="https://dev-sap.example.com:44300",
                client="100",
                user="dev_user",
                password=SecretStr("dev_pass"),
                language="DE",
            ),
            "qa": SAPSystem(
                connection_name="QA System",
                host="https://qa-sap.example.com:44300",
                client="200",
                user="qa_user",
                password=SecretStr("qa_pass"),
                language="EN",
            ),
        },
    )


@pytest.fixture()
def _patch_config():
    """Patch the global SAP config singleton with a multi-system config."""
    cfg = _multi_system_config()
    with patch("sapguimcp.models.config._sap_config", cfg):
        yield cfg


@pytest.fixture()
def _mock_backend():
    """Mock the backend so sap_login doesn't try to connect to a real SAP system."""
    backend = AsyncMock()
    backend.login.return_value = LoginResult(success=True, user="test_user")
    backend.start_keepalive.return_value = None
    with patch("sapguimcp.tools.sap_login_impl.get_backend", new=AsyncMock(return_value=backend)):
        yield backend


class TestChooseToolRegistered:
    """The choose tool from the Choice provider is available via MCP."""

    @pytest.mark.anyio
    async def test_choose_tool_listed(self) -> None:
        from sapguimcp.server import mcp

        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "choose" in names

    @pytest.mark.anyio
    async def test_sap_login_tool_listed(self) -> None:
        from sapguimcp.server import mcp

        async with Client(mcp) as client:
            tools = await client.list_tools()
            names = [t.name for t in tools]
            assert "sap_login" in names
            assert "sap_discover_clients" not in names


class TestSapLoginViaMCP:
    """sap_login called through MCP protocol resolves system_key to SAP Logon entry."""

    @pytest.mark.anyio
    async def test_login_default_system(self, _patch_config, _mock_backend) -> None:
        """sap_login() with no args uses default system and its SAP Logon entry."""
        from sapguimcp.server import mcp

        async with Client(mcp) as client:
            result = await client.call_tool("sap_login", {})

        _mock_backend.login.assert_called_once()
        _, kwargs = _mock_backend.login.call_args
        assert kwargs["connection_name"] == "DEV - ERP Development"
        assert kwargs["client"] == "100"
        assert kwargs["username"] == "dev_user"

    @pytest.mark.anyio
    async def test_login_explicit_system_key(self, _patch_config, _mock_backend) -> None:
        """sap_login(system_key="qa") resolves to QA system's SAP Logon entry."""
        from sapguimcp.server import mcp

        async with Client(mcp) as client:
            result = await client.call_tool("sap_login", {"system_key": "qa"})

        _mock_backend.login.assert_called_once()
        _, kwargs = _mock_backend.login.call_args
        assert kwargs["connection_name"] == "QA System"
        assert kwargs["client"] == "200"
        assert kwargs["username"] == "qa_user"

    @pytest.mark.anyio
    async def test_login_returns_success(self, _patch_config, _mock_backend) -> None:
        """sap_login returns a successful LoginResult through MCP."""
        from sapguimcp.server import mcp

        async with Client(mcp) as client:
            result = await client.call_tool("sap_login", {"system_key": "dev"})

        assert not result.is_error
        assert "success=True" in str(result.data)
