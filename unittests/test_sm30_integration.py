"""
Integration tests for SM30 (Table Maintenance View) lookup tool.

These tests run against a real SAP system to verify the sap_sm30_lookup tool
works correctly end-to-end.
"""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.sm30_models import SM30ViewResult

from .conftest import call_tool_typed

# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.anyio
async def test_sm30_lookup_v_t005_countries(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_sm30_lookup with V_T005 (Countries) - a well-known flat table view.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm30_lookup",
        {"view_name": "V_T005"},
        SM30ViewResult,
    )

    assert result.success, f"SM30 lookup failed: {result.error}"
    assert result.view_name == "V_T005"
    assert result.view_type == "flat"
    assert len(result.columns) > 0
    assert result.row_count > 0
    assert len(result.rows) > 0

    # V_T005 should have country-related columns
    first_row = result.rows[0]
    assert len(first_row.values) == len(result.columns)


@pytest.mark.anyio
async def test_sm30_lookup_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_sm30_lookup with a non-existent view.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm30_lookup",
        {"view_name": "ZZZNOTEXIST99"},
        SM30ViewResult,
    )

    assert not result.success, "Expected failure for non-existent view"
    assert result.view_type == "unsupported"
