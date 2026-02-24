"""
Integration tests for SM37 (Job Overview) lookup tool.

These tests run against a real SAP system to verify the sap_sm37_lookup tool.
They auto-skip if not on an authorized machine.
"""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import LoginResult
from sapwebguimcp.models.sm37_models import SM37JobListResult

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_sm37_lookup_all_jobs(sap_mcp_client: ClientSession) -> None:
    """Test sap_sm37_lookup with default filters (all jobs, all users)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {"job_name": "*", "username": "*"},
        SM37JobListResult,
    )

    assert result.success, f"SM37 lookup failed: {result.error}"
    assert result.job_count > 0, "Should find at least one job"
    assert len(result.jobs) == result.job_count

    for job in result.jobs:
        assert job.job_name, "Job name should not be empty"
        assert job.status in ("Scheduled", "Released", "Ready", "Active", "Finished", "Canceled")
        assert job.user, "User should not be empty"


@pytest.mark.anyio
async def test_sm37_lookup_no_jobs_found(sap_mcp_client: ClientSession) -> None:
    """Test sap_sm37_lookup with a job name that doesn't exist."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {"job_name": "ZZZNOTEXIST_JOB_99", "username": "*"},
        SM37JobListResult,
    )

    assert result.success, f"SM37 lookup failed: {result.error}"
    assert result.job_count == 0, "Should find no jobs"
    assert len(result.jobs) == 0
