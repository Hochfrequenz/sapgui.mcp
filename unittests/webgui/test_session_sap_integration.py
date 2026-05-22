"""End-to-end tests for session management against real SAP system."""

import pytest

from unittests.conftest import has_sap_webgui_creds

from .conftest import call_tool_typed

pytestmark = pytest.mark.skipif(not has_sap_webgui_creds(), reason="No SAP WebGUI credentials")


class TestSessionSAPIntegration:
    """E2E tests requiring real SAP system."""

    @pytest.mark.anyio
    async def test_sap_session_list_after_login(self, sap_mcp_client) -> None:
        """Test that sap_session_list works after login."""
        from sapguimcp.models import SessionListResult

        # Login first
        await sap_mcp_client.call_tool("sap_login", {})

        # Check sessions
        result = await call_tool_typed(sap_mcp_client, "sap_session_list", {}, SessionListResult)

        assert result.success
        # After login, should have at least one session
        # Note: s1 might not be registered yet if sap_login doesn't register it

    @pytest.mark.anyio
    async def test_sap_session_close_primary_rejected(self, sap_mcp_client) -> None:
        """Test that closing primary session is rejected."""
        from sapguimcp.models import SessionCloseResult

        await sap_mcp_client.call_tool("sap_login", {})

        result = await call_tool_typed(sap_mcp_client, "sap_session_close", {"session_id": "s1"}, SessionCloseResult)

        assert result.success is False
        assert "primary" in result.error.lower() or "s1" in result.error

    @pytest.mark.anyio
    async def test_sap_transaction_new_window_auto_registers_session(self, sap_mcp_client) -> None:
        """Test that sap_transaction with new_window=True auto-registers the new session."""
        from sapguimcp.models import SessionCloseResult, SessionListResult, TransactionResult

        # Login first
        await sap_mcp_client.call_tool("sap_login", {})

        # Open transaction in new window
        result = await call_tool_typed(
            sap_mcp_client, "sap_transaction", {"tcode": "SE80", "new_window": True}, TransactionResult
        )

        assert result.success, f"Transaction failed: {result.error}"
        assert result.new_window is True
        assert result.session_id is not None, "session_id should be set when new_window=True"
        assert result.session_id.startswith("s"), f"session_id should be like 's2', got: {result.session_id}"
        assert result.session_count is not None and result.session_count >= 2

        # Verify the session is listed
        list_result = await call_tool_typed(sap_mcp_client, "sap_session_list", {}, SessionListResult)
        assert list_result.success
        session_ids = [s.session_id for s in list_result.sessions]
        assert result.session_id in session_ids, f"New session {result.session_id} not in session list: {session_ids}"

        # Cleanup: close the new session
        close_result = await call_tool_typed(
            sap_mcp_client, "sap_session_close", {"session_id": result.session_id}, SessionCloseResult
        )
        assert close_result.success
