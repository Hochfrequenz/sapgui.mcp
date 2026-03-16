"""Integration tests for ST22 (ABAP Dump Analysis) on desktop backend."""

import json
import sys
from datetime import date, timedelta

import pytest

from sapwebguimcp.models.st22_models import ST22DumpListResult
from sapwebguimcp.tools.st22_tools import _st22_lookup_desktop
from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_not_sap
@skip_no_creds
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


@skip_not_sap
@skip_no_creds
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


@skip_not_sap
@skip_no_creds
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
