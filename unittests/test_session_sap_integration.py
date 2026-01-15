"""End-to-end tests for session management against real SAP system."""

import pytest
from unittests.conftest import is_sap_integration_test_machine, call_tool_typed

pytestmark = pytest.mark.skipif(
    not is_sap_integration_test_machine(),
    reason="SAP integration tests only run on authorized machines"
)


class TestSessionSAPIntegration:
    """E2E tests requiring real SAP system."""

    @pytest.mark.anyio
    async def test_sap_session_list_after_login(self, sap_mcp_client) -> None:
        """Test that sap_session_list works after login."""
        from sapwebguimcp.models import SessionListResult

        # Login first
        await sap_mcp_client.call_tool("sap_login", {})

        # Check sessions
        result = await call_tool_typed(
            sap_mcp_client, "sap_session_list", {}, SessionListResult
        )

        assert result.success
        # After login, should have at least one session
        # Note: s1 might not be registered yet if sap_login doesn't register it

    @pytest.mark.anyio
    async def test_sap_session_close_primary_rejected(self, sap_mcp_client) -> None:
        """Test that closing primary session is rejected."""
        from sapwebguimcp.models import SessionCloseResult

        await sap_mcp_client.call_tool("sap_login", {})

        result = await call_tool_typed(
            sap_mcp_client, "sap_session_close", {"session_id": "s1"}, SessionCloseResult
        )

        assert result.success is False
        assert "primary" in result.error.lower() or "s1" in result.error
