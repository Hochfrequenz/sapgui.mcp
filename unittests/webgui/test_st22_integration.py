"""
Integration tests for ST22 (Short Dump Analysis) tool.

Tests the sap_st22_lookup tool end-to-end against a real SAP system.
Requires:
- Chrome with remote debugging running
- SAP login credentials in .env
- SAP system reachable

Auto-skips if SAP is not available.
"""

from datetime import date, timedelta

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult
from sapguimcp.models.st22_models import ST22DumpDetailResult, ST22DumpListResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_st22_list_today(sap_mcp_client: ClientSession) -> None:
    """List today's short dumps."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_st22_lookup",
        {},
        ST22DumpListResult,
    )

    assert result.success, f"ST22 list failed: {result.error}"
    assert result.dump_count >= 0


@pytest.mark.anyio
async def test_st22_list_yesterday(sap_mcp_client: ClientSession) -> None:
    """List yesterday's short dumps."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_st22_lookup",
        {"date": yesterday},
        ST22DumpListResult,
    )

    assert result.success, f"ST22 yesterday failed: {result.error}"
    assert result.dump_count >= 0


@pytest.mark.anyio
async def test_st22_detail_first_dump(sap_mcp_client: ClientSession) -> None:
    """Get detail of the first dump (if any exist)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    # First, list dumps
    list_result = await call_tool_typed(
        sap_mcp_client,
        "sap_st22_lookup",
        {},
        ST22DumpListResult,
    )

    if list_result.dump_count == 0:
        pytest.skip("No dumps available today for detail test")

    # Now get detail of the first dump
    detail_result = await call_tool_typed(
        sap_mcp_client,
        "sap_st22_lookup",
        {"dump_index": 0},
        ST22DumpDetailResult,
    )

    assert detail_result.success, f"ST22 detail failed: {detail_result.error}"
    assert detail_result.detail is not None
    assert detail_result.detail.raw_text


@pytest.mark.anyio
async def test_st22_dump_index_out_of_range(sap_mcp_client: ClientSession) -> None:
    """dump_index out of range should return failure."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_st22_lookup",
        {"dump_index": 99999},
        ST22DumpDetailResult,
    )

    assert result.success is False
    assert "out of range" in (result.error or "").lower() or "no dumps" in (result.error or "").lower()


@pytest.mark.anyio
async def test_st22_empty_list_success(sap_mcp_client: ClientSession) -> None:
    """An empty dump list should still be a success (not an error)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    # Use a far-future date where there should be no dumps
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_st22_lookup",
        {"date": "2030-01-01"},
        ST22DumpListResult,
    )

    # An empty list is still a success - "no dumps" is not an error
    assert result.success is True
    assert result.dump_count == 0
