"""Integration tests for SE09 (Transport Organizer) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.se09_models import TransportListResult
from sapguimcp.tools.se09_tools import _lookup_transports_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_se09_default_lookup(backend):
    """SE09: default params returns TransportListResult (may be empty)."""
    result = await _lookup_transports_desktop(backend, username=None, request_type="all", status="modifiable")
    assert result is not None
    assert result.success, f"SE09 failed: {result.error}"
    assert isinstance(result.requests, list)
    assert result.request_count >= 0
    assert result.request_count == len(result.requests)
    # If transports exist, verify structure
    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        # Note: desktop parser may not extract owner from tree control
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_model_serializes(backend):
    """TransportListResult must JSON-serialize (roundtrip)."""
    result = await _lookup_transports_desktop(backend, username=None, request_type="all", status="modifiable")
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    assert "requests" in parsed
    assert "request_count" in parsed
    # Roundtrip
    restored = TransportListResult.model_validate_json(json_str)
    assert restored.request_count == result.request_count
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_screen_elements(backend):
    """SE09: screen has expected elements (transaction field, etc.)."""
    await backend.enter_transaction("SE09")
    info = await backend.get_screen_info()
    assert info.success
    assert info.transaction == "SE09"
    assert info.title, "SE09 should have a screen title"
    await go_home(backend)


# ---------------------------------------------------------------------------
# SE09 filter variations
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_se09_workbench_only(backend):
    """SE09: request_type='workbench' filters to workbench requests only."""
    result = await _lookup_transports_desktop(backend, username=None, request_type="workbench", status="modifiable")
    assert result.success, f"SE09 failed: {result.error}"
    assert isinstance(result.requests, list)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_customizing_only(backend):
    """SE09: request_type='customizing' filters to customizing requests only."""
    result = await _lookup_transports_desktop(backend, username=None, request_type="customizing", status="modifiable")
    assert result.success, f"SE09 failed: {result.error}"
    assert isinstance(result.requests, list)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_released_only(backend):
    """SE09: status='released' filters to released requests only."""
    result = await _lookup_transports_desktop(backend, username=None, request_type="all", status="released")
    assert result.success, f"SE09 failed: {result.error}"
    assert isinstance(result.requests, list)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_all_status(backend):
    """SE09: status='all' returns both modifiable and released requests."""
    result = await _lookup_transports_desktop(backend, username=None, request_type="all", status="all")
    assert result.success, f"SE09 failed: {result.error}"
    assert isinstance(result.requests, list)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_no_results_fake_user(backend):
    """SE09: username='ZZZFAKEUSER' returns 0 requests."""
    result = await _lookup_transports_desktop(backend, username="ZZZFAKEUSER", request_type="all", status="modifiable")
    assert result.request_count == 0
    assert len(result.requests) == 0
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se09_include_objects_desktop(backend):
    """SE09: include_objects=True expands request nodes to reveal tasks.

    After expanding, each request should have a tasks list (possibly empty
    if the request has no tasks). At least one request should have tasks
    if the system has typical workbench activity.
    """
    result = await _lookup_transports_desktop(
        backend, username=None, request_type="all", status="modifiable", include_objects=True
    )
    assert result.success, f"SE09 failed: {result.error}"
    assert isinstance(result.requests, list)
    assert result.request_count > 0, "Expected at least one transport request"

    # Check that tasks were populated on at least some requests
    requests_with_tasks = [r for r in result.requests if r.tasks]
    # Note: it's valid for all requests to have 0 tasks (e.g. if all are single-task requests)
    # but we log it for visibility
    if requests_with_tasks:
        # Verify task structure
        for req in requests_with_tasks:
            for task in req.tasks:
                assert len(task.task_number) == 10, f"Task number should be 10 chars: {task.task_number}"
                assert task.task_number != req.request_number, "Task should differ from parent request"

    # Verify JSON roundtrip
    json_str = result.model_dump_json()
    restored = TransportListResult.model_validate_json(json_str)
    assert restored.request_count == result.request_count
    await go_home(backend)
