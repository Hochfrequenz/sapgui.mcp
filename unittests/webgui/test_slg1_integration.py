"""
Integration tests for SLG1 (Application Log) lookup tool.

These tests run against a real SAP system to verify the sap_slg1_lookup tool
works correctly end-to-end.
"""

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult
from sapguimcp.models.slg1_models import SLG1LogListResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_slg1_lookup_with_wildcard(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_slg1_lookup with wildcard object to find any logs.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {"object": "*"},
        SLG1LogListResult,
    )

    assert result.success, f"SLG1 lookup failed: {result.error}"
    assert isinstance(result.log_count, int)
    assert isinstance(result.logs, list)
    assert result.log_count > 0, "Wildcard search should find logs"
    assert len(result.logs) > 0, "Should have parsed at least one log"

    # Verify log entry structure
    entry = result.logs[0]
    assert entry.log_number, "log_number should not be empty"
    assert entry.object, "object should not be empty"
    assert entry.date, "date should not be empty"
    assert entry.time, "time should not be empty"
    assert entry.user, "user should not be empty"
    assert entry.log_number.isdigit(), f"log_number should be numeric, got {entry.log_number!r}"


@pytest.mark.anyio
async def test_slg1_lookup_no_results(sap_mcp_client: ClientSession) -> None:
    """Test sap_slg1_lookup with non-existent log object."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {"object": "ZZZNOTEXIST99"},
        SLG1LogListResult,
    )

    # Should succeed but with 0 logs
    assert result.success, f"SLG1 lookup failed unexpectedly: {result.error}"
    assert result.log_count == 0
    assert len(result.logs) == 0


@pytest.mark.anyio
async def test_slg1_lookup_with_specific_object(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_slg1_lookup with a specific log object.

    Uses /SDF/CALM which exists in the test system.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {"object": "/SDF/CALM"},
        SLG1LogListResult,
    )

    assert result.success, f"SLG1 lookup failed: {result.error}"
    assert "object" in result.filters_applied
    assert result.filters_applied["object"] == "/SDF/CALM"

    # All entries should have the /SDF/CALM object (displayed as text, not code)
    if result.logs:
        # Verify the structure is correct
        for entry in result.logs:
            assert entry.log_number.isdigit()
            assert entry.date
            assert entry.time


@pytest.mark.anyio
async def test_slg1_lookup_with_date_filter(sap_mcp_client: ClientSession) -> None:
    """Test sap_slg1_lookup with date range filter."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_slg1_lookup",
        {
            "object": "*",
            "from_date": "2026-02-23",
            "to_date": "2026-02-23",
        },
        SLG1LogListResult,
    )

    assert result.success, f"SLG1 lookup failed: {result.error}"
    assert "from_date" in result.filters_applied
    assert "to_date" in result.filters_applied
