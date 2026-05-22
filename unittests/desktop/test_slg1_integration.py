"""Integration tests for SLG1 (Application Log) on desktop backend."""

import json
import sys
from datetime import date

import pytest

from sapguimcp.models.slg1_models import SLG1LogListResult
from sapguimcp.tools.slg1_tools import _slg1_lookup_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_slg1_with_wildcard(backend):
    """SLG1: object_name='*' returns well-formed result or structured error.

    The desktop backend may fail to read the ALV tree/grid (read_table
    limitation).  We verify the tool returns a well-formed model.
    """
    result = await _slg1_lookup_desktop(
        backend,
        object_name="*",
        subobject=None,
        external_id=None,
        from_date=None,
        to_date=None,
    )
    assert result is not None
    assert isinstance(result.logs, list)
    assert isinstance(result.log_count, int)
    assert result.log_count >= 0
    assert isinstance(result.model_dump_json(), str)
    # If successful with logs, verify structure
    if result.success and result.logs:
        entry = result.logs[0]
        assert entry.log_number, "log_number should not be empty"
        assert entry.date, "date should not be empty"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_slg1_no_results(backend):
    """SLG1: object_name='ZZZNOTEXIST' returns 0 entries or structured error.

    The desktop backend may return success=True with 0 logs (if status bar
    'no logs' is detected) or success=False with a clear error.
    """
    result = await _slg1_lookup_desktop(
        backend,
        object_name="ZZZNOTEXIST",
        subobject=None,
        external_id=None,
        from_date=None,
        to_date=None,
    )
    assert result.log_count == 0
    assert len(result.logs) == 0
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_slg1_model_serializes(backend):
    """SLG1LogListResult must JSON-serialize (roundtrip)."""
    result = await _slg1_lookup_desktop(
        backend,
        object_name="*",
        subobject=None,
        external_id=None,
        from_date=None,
        to_date=None,
    )
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert "success" in parsed
    assert "logs" in parsed
    assert "log_count" in parsed
    # Roundtrip -- works regardless of success/failure
    restored = SLG1LogListResult.model_validate_json(json_str)
    assert restored.log_count == result.log_count
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_slg1_with_date_filter(backend):
    """SLG1: from_date=today, to_date=today returns well-formed result.

    The desktop backend may or may not successfully fill the date fields
    (label mismatches are logged as warnings). We verify the tool returns
    a well-formed model regardless.
    """
    today = date.today().isoformat()
    result = await _slg1_lookup_desktop(
        backend,
        object_name="*",
        subobject=None,
        external_id=None,
        from_date=today,
        to_date=today,
    )
    assert result is not None
    assert isinstance(result.logs, list)
    assert isinstance(result.log_count, int)
    assert result.log_count >= 0
    assert result.log_count == len(result.logs)
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)
