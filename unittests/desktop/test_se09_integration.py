"""Integration tests for SE09 (Transport Organizer) on desktop backend."""

import json
import sys

import pytest

from sapwebguimcp.models.se09_models import TransportListResult
from sapwebguimcp.tools.se09_tools import _lookup_transports_desktop
from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_not_sap
@skip_no_creds
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


@skip_not_sap
@skip_no_creds
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


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se09_screen_elements(backend):
    """SE09: screen has expected elements (transaction field, etc.)."""
    await backend.enter_transaction("SE09")
    info = await backend.get_screen_info()
    assert info.success
    assert info.transaction == "SE09"
    assert info.title, "SE09 should have a screen title"
    await go_home(backend)
