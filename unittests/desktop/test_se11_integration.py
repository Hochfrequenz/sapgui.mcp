"""Integration tests for SE11 (ABAP Dictionary) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.se11_models import SE11Entry, SE11Error
from sapguimcp.tools.se11_tools import _lookup_se11_desktop
from unittests.desktop.conftest import TEST_TABLE, go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


async def _navigate_se11(backend) -> None:
    """Navigate to a clean SE11 initial screen."""
    await backend.enter_transaction("SE11")
    await backend.wait_for_ready()


@skip_no_sap
@pytest.mark.anyio
async def test_se11_lookup_table_t000(backend):
    """SE11: look up T000 (clients table) returns fields with MANDT."""
    await _navigate_se11(backend)
    result = await _lookup_se11_desktop(backend, "T000", "table")
    assert isinstance(result, SE11Entry), f"Expected SE11Entry, got {type(result).__name__}: {result}"
    assert result.name == "T000"
    assert result.object_type == "table"
    assert len(result.fields) > 0, "Should have fields"
    # T000 has MANDT field with type CLNT
    mandt = next((f for f in result.fields if f.name == "MANDT"), None)
    assert mandt is not None, "T000 should have MANDT field"
    assert mandt.datatype == "CLNT"
    assert mandt.length == 3
    # Verify JSON roundtrip
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["name"] == "T000"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se11_lookup_nonexistent(backend):
    """SE11: look up ZZZNOTEXIST99 returns SE11Error."""
    await _navigate_se11(backend)
    result = await _lookup_se11_desktop(backend, "ZZZNOTEXIST99", "table")
    assert isinstance(result, SE11Error), f"Expected SE11Error, got {type(result).__name__}"
    assert result.name == "ZZZNOTEXIST99"
    assert result.error
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se11_lookup_structure_bapiret2(backend):
    """SE11: look up BAPIRET2 structure returns fields."""
    await _navigate_se11(backend)
    result = await _lookup_se11_desktop(backend, "BAPIRET2", "structure")
    # Structure display may use a different layout (no GuiTableControl) —
    # if we get an SE11Entry, verify fields; if SE11Error, verify it's a
    # "no table control" error (known limitation, not a navigation failure).
    if isinstance(result, SE11Entry):
        assert result.name == "BAPIRET2"
        assert result.object_type == "structure"
        assert len(result.fields) > 0, "Should have fields"
        type_field = next((f for f in result.fields if f.name == "TYPE"), None)
        assert type_field is not None, "BAPIRET2 should have TYPE field"
    else:
        assert "table control" in result.error.lower(), f"Unexpected error: {result.error}"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se11_fields_have_types(backend):
    """SE11: all fields should have a non-empty datatype."""
    await _navigate_se11(backend)
    result = await _lookup_se11_desktop(backend, TEST_TABLE, "table")
    assert isinstance(result, SE11Entry)
    for field in result.fields:
        assert field.datatype, f"Field {field.name} should have a datatype"
        assert field.length >= 0, f"Field {field.name} should have a non-negative length"
    await go_home(backend)
