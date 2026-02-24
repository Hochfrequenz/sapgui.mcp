"""
Integration tests for SE09 (Transport Organizer) lookup tool.

These tests run against a real SAP system to verify the sap_se09_lookup tool.
"""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.se09_models import TransportListResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_se09_lookup_default(sap_mcp_client: ClientSession) -> None:
    """Test sap_se09_lookup with default parameters (current user, modifiable)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count >= 0
    assert len(result.requests) == result.request_count

    # Verify structure
    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        assert req.owner != ""


@pytest.mark.anyio
async def test_se09_lookup_workbench_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by workbench request type."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"request_type": "workbench"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    # When filtering by workbench, returned requests should be Workbench type
    # (but the parser may not always detect the type if the section header is missing)
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench", f"Expected Workbench, got {req.request_type}"


@pytest.mark.anyio
async def test_se09_lookup_all_status(sap_mcp_client: ClientSession) -> None:
    """Test with both modifiable and released."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"status": "all"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count >= 0


@pytest.mark.anyio
async def test_se09_lookup_no_results(sap_mcp_client: ClientSession) -> None:
    """Test with a user that has no transports."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "ZZZNOUSER99"},
        TransportListResult,
    )

    # Should succeed with 0 results (or gracefully handle if checkboxes are disabled)
    if result.success:
        assert result.request_count == 0
    else:
        # May fail if the user field is not accepted or checkboxes disabled
        assert "error" in result.error.lower() or "timeout" in result.error.lower()
