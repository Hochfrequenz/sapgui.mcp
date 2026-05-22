"""Integration tests for SM30 (Table Maintenance) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.sm30_models import SM30ViewResult
from sapguimcp.tools.sm30_tools import _lookup_view_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_sm30_existing_view_v_t005(backend):
    """SM30: looking up V_T005 (Countries) returns well-formed result.

    V_T005 is a proper SM30 maintenance view (unlike T000 which is a table).
    The desktop backend may fail to read the ALV grid (read_table limitation).
    We verify the tool returns a well-formed SM30ViewResult regardless.
    If successful, also verify columns and rows are non-empty.
    """
    result = await _lookup_view_desktop(backend, "V_T005")
    assert result is not None
    assert result.view_name == "V_T005"
    assert isinstance(result.model_dump_json(), str)
    if result.success:
        assert len(result.columns) > 0, "Columns should be non-empty for V_T005"
        assert result.row_count > 0, "V_T005 should have rows (countries)"
        assert len(result.rows) > 0, "Rows list should be non-empty"
        first_row = result.rows[0]
        assert len(first_row.values) == len(result.columns)
    else:
        # Structured error is acceptable for desktop backend
        assert result.error is not None
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm30_nonexistent_view(backend):
    """SM30: nonexistent view ZZZNOTEXIST99 returns error, not exception."""
    result = await _lookup_view_desktop(backend, "ZZZNOTEXIST99")
    assert result is not None
    assert not result.success, "Expected failure for non-existent view"
    assert result.view_type == "unsupported"
    assert isinstance(result.model_dump_json(), str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_sm30_model_serializes(backend):
    """SM30ViewResult must JSON-serialize (roundtrip)."""
    result = await _lookup_view_desktop(backend, "V_T005")
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["view_name"] == "V_T005"
    assert "columns" in parsed
    assert "rows" in parsed
    assert "success" in parsed
    # Roundtrip
    restored = SM30ViewResult.model_validate_json(json_str)
    assert restored.view_name == "V_T005"
    assert restored.row_count == result.row_count
    await go_home(backend)
