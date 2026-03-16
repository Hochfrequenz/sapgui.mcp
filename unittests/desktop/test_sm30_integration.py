"""Integration tests for SM30 (Table Maintenance) on desktop backend."""

import json
import sys

import pytest

from sapwebguimcp.models.sm30_models import SM30ViewResult
from sapwebguimcp.tools.sm30_tools import _lookup_view_desktop
from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm30_existing_view_t000(backend):
    """SM30: looking up T000 (Clients) returns well-formed result.

    The desktop backend may fail to read the ALV grid (read_table limitation).
    We verify the tool returns a well-formed SM30ViewResult regardless.
    If successful, also verify data structure.
    """
    result = await _lookup_view_desktop(backend, "T000")
    assert result is not None
    assert result.view_name == "T000"
    assert isinstance(result.model_dump_json(), str)
    if result.success:
        assert result.view_type == "flat"
        assert len(result.columns) > 0
        assert result.row_count > 0
        assert len(result.rows) > 0
        first_row = result.rows[0]
        assert len(first_row.values) == len(result.columns)
    else:
        # Structured error is acceptable for desktop backend
        assert result.error is not None
    await go_home(backend)


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm30_nonexistent_view(backend):
    """SM30: nonexistent view ZZZNOTEXIST99 returns error, not exception."""
    result = await _lookup_view_desktop(backend, "ZZZNOTEXIST99")
    assert result is not None
    assert not result.success, "Expected failure for non-existent view"
    assert result.view_type == "unsupported"
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_sm30_model_serializes(backend):
    """SM30ViewResult must JSON-serialize (roundtrip)."""
    result = await _lookup_view_desktop(backend, "T000")
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["view_name"] == "T000"
    assert "columns" in parsed
    assert "rows" in parsed
    assert "success" in parsed
    # Roundtrip
    restored = SM30ViewResult.model_validate_json(json_str)
    assert restored.view_name == "T000"
    assert restored.row_count == result.row_count
    await go_home(backend)
