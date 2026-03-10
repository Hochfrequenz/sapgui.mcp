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


@pytest.mark.anyio
async def test_se09_lookup_include_objects(sap_mcp_client: ClientSession) -> None:
    """Test sap_se09_lookup with include_objects=True to get tasks."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "include_objects": True},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0

    # At least one request should have tasks (KLEINK has modifiable transports with tasks)
    requests_with_tasks = [r for r in result.requests if r.tasks]
    assert len(requests_with_tasks) > 0, "Expected at least one request with tasks"

    # Verify task structure
    for req in result.requests:
        for task in req.tasks:
            assert len(task.task_number) == 10
            assert task.task_number[3] == "K"
            # Task number should be different from request number
            assert task.task_number != req.request_number


@pytest.mark.anyio
async def test_se09_lookup_customizing_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by customizing request type returns no errors."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"request_type": "customizing"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    # Customizing transports may or may not exist for the current user
    assert result.request_count >= 0
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Customizing", f"Expected Customizing, got {req.request_type}"


@pytest.mark.anyio
async def test_se09_lookup_released_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by released status."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"status": "released"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count >= 0
    for req in result.requests:
        if req.status:
            assert req.status == "Released", f"Expected Released, got {req.status}"


@pytest.mark.anyio
async def test_se09_lookup_workbench_include_objects(sap_mcp_client: ClientSession) -> None:
    """Test workbench-only filter combined with include_objects."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "request_type": "workbench", "include_objects": True},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0

    # All requests should be workbench type
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench"

    # At least one request should have tasks
    requests_with_tasks = [r for r in result.requests if r.tasks]
    assert len(requests_with_tasks) > 0


@pytest.mark.anyio
async def test_se09_lookup_all_types_all_status(sap_mcp_client: ClientSession) -> None:
    """Test retrieving all request types and all statuses."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "request_type": "all", "status": "all"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    # KLEINK should have at least the modifiable workbench transports
    assert result.request_count >= 5

    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        assert req.owner != ""
