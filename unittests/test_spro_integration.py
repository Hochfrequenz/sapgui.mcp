"""
Integration tests for SPRO (Customizing IMG) search tool.

These tests run against a real SAP system to verify the end-to-end
sap_spro_search tool workflow.
"""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.spro_models import SPROSearchResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_spro_search_with_results(sap_mcp_client: ClientSession) -> None:
    """Search for 'Land' which returns results in DE."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_spro_search",
        {"query": "Land"},
        SPROSearchResult,
    )
    assert result.success, f"Search failed: {result.error}"
    assert result.activity_count > 0
    assert len(result.activities) > 0
    assert result.query == "Land"

    # Verify activities have names
    for activity in result.activities:
        assert activity.activity_name


@pytest.mark.anyio
async def test_spro_search_no_results(sap_mcp_client: ClientSession) -> None:
    """Search for a term unlikely to return results."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_spro_search",
        {"query": "zzznonexistentterm999"},
        SPROSearchResult,
    )
    # Should succeed but with no results
    assert result.success
    assert result.activity_count == 0
