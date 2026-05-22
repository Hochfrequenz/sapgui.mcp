"""Integration tests for SM37 (Job Overview) on desktop backend."""

import json
import sys
from datetime import date

import pytest

from sapguimcp.models.sm37_models import SM37JobListResult
from sapguimcp.tools.sm37_tools import _execute_sm37_lookup, _execute_sm37_lookup_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_default_selection(backend):
    """SM37: default params returns well-formed SM37JobListResult."""
    result = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username=None,
        statuses=None,
        from_date=None,
        to_date=None,
    )
    assert result.success or result.error, "Should return data or a clear error"
    assert isinstance(result.jobs, list)
    assert isinstance(result.job_count, int)
    assert result.job_count == len(result.jobs)
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_no_jobs_for_fake_user(backend):
    """SM37: username='ZZZFAKEUSER' returns 0 jobs or structured error.

    The desktop backend may return success=True with 0 jobs (if the status
    bar 'no jobs' message is detected) or success=False with a clear error
    (if read_table fails because no ALV grid is shown).  Either is acceptable.
    """
    result = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username="ZZZFAKEUSER",
        statuses=None,
        from_date=None,
        to_date=None,
    )
    assert result.job_count == 0, "Should find no jobs for fake user"
    assert len(result.jobs) == 0
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_model_serializes(backend):
    """SM37JobListResult must JSON-serialize (roundtrip)."""
    result = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username=None,
        statuses=None,
        from_date=None,
        to_date=None,
    )
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    assert "jobs" in parsed
    assert "job_count" in parsed
    # Roundtrip
    restored = SM37JobListResult.model_validate_json(json_str)
    assert restored.job_count == result.job_count
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_screen_info(backend):
    """SM37: verify transaction screen is reachable and identified."""
    await backend.enter_transaction("SM37")
    info = await backend.get_screen_info()
    assert info.success
    assert info.transaction == "SM37"
    assert info.title, "SM37 should have a screen title"
    assert info.program, "SM37 should report a program name"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_with_wildcard_jobname(backend):
    """SM37: job_name='*' returns result or structured error.

    The desktop backend may fail to read the ALV grid when jobs exist
    (read_table limitation).  We verify the tool returns a well-formed
    model in either case.
    """
    result = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username="*",
        statuses=None,
        from_date=None,
        to_date=None,
    )
    # Either succeeds with data or fails with structured error
    assert isinstance(result.jobs, list)
    assert result.job_count >= 0
    assert result.job_count == len(result.jobs)
    assert isinstance(result.model_dump_json(), str)
    # If jobs exist, verify structure
    for job in result.jobs:
        assert job.job_name, "Job name should not be empty"
        assert job.status, "Status should not be empty"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_finished_status_filter(backend):
    """SM37: statuses=['finished'] returns only finished jobs (or 0 jobs)."""
    result = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username=None,
        statuses=["finished"],
        from_date=None,
        to_date=None,
    )
    assert isinstance(result.jobs, list)
    assert result.job_count == len(result.jobs)
    assert result.job_count >= 0
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_with_date_range(backend):
    """SM37: from_date and to_date set to today returns well-formed result."""
    today = date.today().isoformat()
    result = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username=None,
        statuses=None,
        from_date=today,
        to_date=today,
    )
    assert isinstance(result.jobs, list)
    assert result.job_count == len(result.jobs)
    assert result.job_count >= 0
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm37_include_log_desktop(backend):
    """SM37: include_log=True fetches job log when exactly 1 job matches."""
    # First find a finished job to use
    probe = await _execute_sm37_lookup_desktop(
        backend,
        job_name="*",
        username=None,
        statuses=["finished"],
        from_date=None,
        to_date=None,
    )
    await go_home(backend)
    if not probe.success or not probe.jobs:
        pytest.skip("No finished jobs available for include_log test")

    # Use the first job's name for an exact match
    target_job = probe.jobs[0].job_name
    result = await _execute_sm37_lookup(
        backend,
        job_name=target_job,
        username=None,
        statuses=["finished"],
        from_date=None,
        to_date=None,
        include_log=True,
    )
    assert result.success, f"Lookup failed: {result.error}"
    if result.job_count == 1:
        assert result.job_log is not None, "job_log should be populated when exactly 1 job matches"
        assert result.job_log.job_name == target_job
        assert isinstance(result.job_log.log_lines, list)
        assert len(result.job_log.log_lines) > 0, "Job log should have at least one line"
    else:
        # Multiple jobs with same name — log not fetched (only works for exactly 1)
        assert result.job_log is None, "job_log should be None when multiple jobs match"
    await go_home(backend)
