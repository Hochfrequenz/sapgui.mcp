"""Integration tests for ST22 (ABAP Dump Analysis) on desktop backend."""

import json
import sys
from datetime import date, timedelta

import pytest

from sapguimcp.models.st22_models import ST22DumpListResult
from sapguimcp.tools.st22_tools import _st22_lookup_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_st22_today(backend):
    """ST22: dump list for today returns ST22DumpListResult."""
    result = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=None)
    assert result is not None
    assert result.success, f"ST22 failed: {result.error}"
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    assert parsed["dump_count"] >= 0
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_st22_model_serializes(backend):
    """ST22DumpListResult must JSON-serialize (roundtrip)."""
    result = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=None)
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    assert "dumps" in parsed
    assert "dump_count" in parsed
    # Roundtrip
    restored = ST22DumpListResult.model_validate_json(json_str)
    assert restored.dump_count == result.dump_count
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_st22_specific_date(backend):
    """ST22: past date returns whatever dumps exist."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = await _st22_lookup_desktop(backend, target_date=yesterday, dump_index=None)
    assert result is not None
    assert result.success, f"ST22 yesterday failed: {result.error}"
    assert result.dump_count >= 0
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_st22_future_date_empty(backend):
    """ST22: far-future date should return 0 dumps.

    The backend may return success=True with 0 dumps or success=False
    with an error (e.g., "no dumps found"). Either is acceptable as long
    as dump_count is 0.
    """
    result = await _st22_lookup_desktop(backend, target_date="2030-01-01", dump_index=None)
    assert result is not None
    assert result.dump_count == 0, f"Expected 0 dumps in 2030, got {result.dump_count}"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_st22_dump_detail(backend):
    """ST22: if today has dumps, fetch detail for dump_index=0."""
    list_result = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=None)
    await go_home(backend)
    if list_result.dump_count == 0:
        pytest.skip("No dumps today to fetch detail for")
    detail = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=0)
    assert detail is not None
    assert detail.success, f"ST22 detail failed: {detail.error}"
    # Verify detail model fields
    assert hasattr(detail, "detail")
    assert detail.detail is not None
    assert detail.detail.raw_text, "raw_text should be non-empty"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_st22_dump_index_out_of_range(backend):
    """ST22: dump_index=9999 returns failure with out-of-range error."""
    list_result = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=None)
    await go_home(backend)
    if list_result.dump_count == 0:
        pytest.skip("No dumps today to test out-of-range")
    result = await _st22_lookup_desktop(backend, target_date=date.today().isoformat(), dump_index=9999)
    assert result.success is False
    assert "out of range" in (result.error or "")
    await go_home(backend)
