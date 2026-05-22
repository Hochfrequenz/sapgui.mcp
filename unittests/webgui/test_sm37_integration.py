"""
Integration tests for SM37 (Job Overview) lookup tool.

These tests run against a real SAP system to verify the sap_sm37_lookup tool.
They auto-skip if not on an authorized machine.
"""

import pytest
from mcp import ClientSession

from sapguimcp.backend.webgui.models.browser_results import FillResult
from sapguimcp.models import KeyboardResult, LoginResult, StatusBarInfo, TableData, TransactionResult
from sapguimcp.models.sm37_models import SM37JobListResult

from .conftest import call_tool_typed
from .integration_helpers import (
    _wait_for_transaction_screen,
    capture_html_snapshot,
)


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
    # The system may or may not have jobs — assert consistency, not count
    assert result.job_count >= 0
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


# --- Merged from test_sap_integration.py ---


async def assert_fill_success(result: FillResult, field_name: str) -> None:
    """Assert that browser_fill succeeded for a field."""
    assert result.success, f"Failed to fill {field_name}: {result.error}"


@pytest.mark.anyio
async def test_sap_read_table_from_sm37_no_jobs(sap_mcp_client: ClientSession) -> None:
    """Test SM37 when no jobs match selection criteria.

    Uses a non-existent job name to guarantee no results,
    resulting in "Kein Job entspricht den Selektionsbedingungen" message.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")

    # Capture HTML snapshot for offline selector testing (before filling form)
    await capture_html_snapshot(sap_mcp_client, "sm37_initial")

    # Use a non-existent job name to guarantee "no jobs" result.
    # Previously used "*" (all jobs for current user), but that fails
    # when the user has any jobs (scheduled, finished, etc.).
    fill_result = await call_tool_typed(
        sap_mcp_client,
        "browser_fill",
        {"selector": "input[lsdata*='JOBNAME']", "value": "ZZZNOTEXIST_JOB_99"},
        FillResult,
    )
    assert fill_result.success, f"Failed to fill JOBNAME field: {fill_result.error}"

    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 3000})

    # Check status bar for "no jobs" message
    status_result = await call_tool_typed(sap_mcp_client, "sap_read_status_bar", {}, StatusBarInfo)
    status_text = (status_result.message or "").lower()

    # German: "Kein Job entspricht den Selektionsbedingungen"
    # English: "No job meets the selection conditions"
    no_jobs_de = "kein job" in status_text
    no_jobs_en = "no job" in status_text

    assert no_jobs_de or no_jobs_en, f"Expected 'no jobs' status message, got: {status_text}"


@pytest.mark.anyio
async def test_sap_read_table_from_sm37_all_jobs(sap_mcp_client: ClientSession) -> None:
    """Test reading table data from SM37 (Job Overview) with broad criteria.

    SM37 exists on every SAP system and shows background jobs.
    Uses wildcards for username and broad date range to find jobs.
    """
    from datetime import datetime, timedelta

    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await call_tool_typed(sap_mcp_client, "sap_transaction", {"tcode": "SM37"}, TransactionResult)
    # Wait for SM37 to load (has job name input field)
    await _wait_for_transaction_screen(sap_mcp_client, "SM37")

    # Fill job selection with wildcards and clear username restriction
    # SM37 fields use SID in lsdata: BTCH2170-JOBNAME, BTCH2170-USERNAME
    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='JOBNAME']", "value": "*"}, FillResult
    )
    await assert_fill_success(result, "JOBNAME")

    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='USERNAME']", "value": "*"}, FillResult
    )
    await assert_fill_success(result, "USERNAME")

    # Set broad date range (last 365 days) to find jobs
    # Date fields have SID in lsdata: BTCH2170-FROM_DATE, BTCH2170-TO_DATE
    today = datetime.now()
    from_date = (today - timedelta(days=365)).strftime("%d.%m.%Y")
    to_date = today.strftime("%d.%m.%Y")

    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='FROM_DATE']", "value": from_date}, FillResult
    )
    await assert_fill_success(result, f"FROM_DATE={from_date}")

    result = await call_tool_typed(
        sap_mcp_client, "browser_fill", {"selector": "input[lsdata*='TO_DATE']", "value": to_date}, FillResult
    )
    await assert_fill_success(result, f"TO_DATE={to_date}")

    # Execute (F8) and wait for list output to complete (can take a while with many jobs)
    await call_tool_typed(sap_mcp_client, "sap_press_key", {"key": "F8"}, KeyboardResult)
    await sap_mcp_client.call_tool("browser_wait", {"timeout": 30000})

    # Capture table results HTML for unit tests
    await capture_html_snapshot(sap_mcp_client, "sm37_results")

    table_result = await call_tool_typed(sap_mcp_client, "sap_read_table", {"start_row": 1, "end_row": 5}, TableData)
    assert table_result.success, f"sap_read_table failed: {table_result.error}"

    # Assert that we got actual table data with rows
    assert table_result.rows is not None, f"Expected table with 'rows', got: {table_result}"
    assert table_result.total_rows is not None, f"Expected 'total_rows' in response, got: {table_result}"

    # Verify we got some jobs
    assert table_result.total_rows > 0, f"Expected some jobs in SM37, got total_rows=0"
    assert len(table_result.rows) > 0, "Expected at least one row in SM37 results"


@pytest.mark.anyio
async def test_sm37_lookup_finished_status_filter(sap_mcp_client: ClientSession) -> None:
    """Test that SM37 status checkbox filtering actually works.

    Verifies that set_checkbox properly toggles SAP checkboxes by filtering
    for only 'finished' jobs. If checkboxes didn't work (the old fill_field("X")
    bug), all default statuses would remain and results would include non-finished jobs.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {"job_name": "*", "username": "*", "status": ["finished"]},
        SM37JobListResult,
    )

    assert result.success, f"SM37 lookup failed: {result.error}"

    # If checkboxes work, all returned jobs should have 'finished' status
    for job in result.jobs:
        status_lower = (job.status or "").lower()
        assert status_lower in ("finished", "fertig"), (
            f"Expected 'finished'/'fertig' status but got '{job.status}'. "
            "Checkbox filter may not be working (set_checkbox bug)."
        )


@pytest.mark.anyio
async def test_sm37_lookup_canceled_status_filter(sap_mcp_client: ClientSession) -> None:
    """Test SM37 with 'canceled' status filter to verify checkbox unchecking works.

    'Canceled' is NOT checked by default in SAP. If set_checkbox works, only
    canceled jobs should appear. If checkboxes silently fail, we'd get the
    default mix (all except 'scheduled').
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {"job_name": "*", "username": "*", "status": ["canceled"]},
        SM37JobListResult,
    )

    assert result.success, f"SM37 lookup failed: {result.error}"

    # Even if no canceled jobs exist, the query should succeed
    # If there ARE results, they must all be canceled
    for job in result.jobs:
        status_lower = (job.status or "").lower()
        assert status_lower in ("canceled", "abgebrochen"), (
            f"Expected 'canceled'/'abgebrochen' status but got '{job.status}'. " "Checkbox filter may not be working."
        )


@pytest.mark.anyio
async def test_sm37_lookup_with_date_filter(sap_mcp_client: ClientSession) -> None:
    """
    Test sap_sm37_lookup with date range filter.

    Verifies that the from_date and to_date parameters are correctly filled
    into the SM37 selection screen date fields. Uses a narrow date range
    (today only) to verify the fields are found and set without error.

    This test covers the fix for GitHub issue #304 where the ARIA labels
    for date fields were wrong (e.g., "von (Datum/Uhrzeit)" instead of "von Datum").

    Works in both DE and EN via the language-aware label lookup.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    # Use today's date as both from and to — guarantees a valid range
    from datetime import UTC, datetime

    today = datetime.now(UTC).strftime("%Y-%m-%d")

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_sm37_lookup",
        {
            "job_name": "*",
            "username": "*",
            "from_date": today,
            "to_date": today,
        },
        SM37JobListResult,
    )

    assert result.success, f"sap_sm37_lookup with date filter failed: {result.error}"
    assert (
        result.filters_applied.get("from_date") == today
    ), f"Expected from_date='{today}' in filters, got {result.filters_applied}"
    assert (
        result.filters_applied.get("to_date") == today
    ), f"Expected to_date='{today}' in filters, got {result.filters_applied}"
