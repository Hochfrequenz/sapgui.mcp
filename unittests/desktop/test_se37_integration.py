"""Integration tests for SE37 (Function Builder) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.se37_models import SE37Entry, SE37Error
from sapguimcp.tools.se37_tools import _lookup_fm_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_se37_lookup_rfc_read_table(backend):
    """SE37: look up RFC_READ_TABLE returns parameters and exceptions."""
    await backend.enter_transaction("SE37")
    await backend.wait_for_ready()
    result = await _lookup_fm_desktop(backend, "RFC_READ_TABLE")
    assert isinstance(result, SE37Entry), f"Expected SE37Entry, got {type(result).__name__}: {result}"
    assert result.function_module == "RFC_READ_TABLE"
    assert len(result.import_parameters) > 0, "Should have import parameters"
    assert len(result.exceptions) > 0, "Should have exceptions"
    # Verify JSON roundtrip
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["function_module"] == "RFC_READ_TABLE"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se37_lookup_nonexistent(backend):
    """SE37: look up ZZZFAKE_FM returns SE37Error."""
    await backend.enter_transaction("SE37")
    await backend.wait_for_ready()
    result = await _lookup_fm_desktop(backend, "ZZZFAKE_FM")
    assert isinstance(result, SE37Error), f"Expected SE37Error, got {type(result).__name__}"
    assert result.function_module == "ZZZFAKE_FM"
    assert result.error
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se37_params_have_category(backend):
    """SE37: parameters should have correct category."""
    await backend.enter_transaction("SE37")
    await backend.wait_for_ready()
    result = await _lookup_fm_desktop(backend, "RFC_READ_TABLE")
    assert isinstance(result, SE37Entry)
    for p in result.import_parameters:
        assert p.category == "import"
    for p in result.export_parameters:
        assert p.category == "export"
    await go_home(backend)
