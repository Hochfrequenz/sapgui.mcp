"""Integration tests for SE11 (ABAP Dictionary) on desktop backend."""

import json
import sys

import pytest

from sapwebguimcp.models.se11_models import SE11Entry, SE11Error
from sapwebguimcp.tools.se11_tools import _lookup_se11_desktop
from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se11_lookup_table_t000(backend):
    """SE11: look up T000 (clients table) returns fields with key field MANDT."""
    await backend.enter_transaction("SE11")
    await backend.wait_for_ready()
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


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se11_lookup_nonexistent(backend):
    """SE11: look up ZZZNOTEXIST99 returns SE11Error."""
    await backend.enter_transaction("SE11")
    await backend.wait_for_ready()
    result = await _lookup_se11_desktop(backend, "ZZZNOTEXIST99", "table")
    assert isinstance(result, SE11Error), f"Expected SE11Error, got {type(result).__name__}"
    assert result.name == "ZZZNOTEXIST99"
    assert result.error
    await go_home(backend)


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_se11_fields_have_types(backend):
    """SE11: all fields should have a non-empty datatype."""
    await backend.enter_transaction("SE11")
    await backend.wait_for_ready()
    result = await _lookup_se11_desktop(backend, "T000", "table")
    assert isinstance(result, SE11Entry)
    for field in result.fields:
        assert field.datatype, f"Field {field.name} should have a datatype"
        assert field.length >= 0, f"Field {field.name} should have a non-negative length"
    await go_home(backend)
