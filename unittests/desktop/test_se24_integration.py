"""Integration tests for SE24 (Class Builder) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.se24_models import SE24Entry, SE24Error
from sapguimcp.tools.se24_tools import _lookup_class_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_se24_lookup_class(backend):
    """SE24: look up CL_ABAP_CHAR_UTILITIES returns methods and attributes."""
    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()
    result = await _lookup_class_desktop(backend, "CL_ABAP_CHAR_UTILITIES")
    assert isinstance(result, SE24Entry), f"Expected SE24Entry, got {type(result).__name__}: {result}"
    assert result.class_name == "CL_ABAP_CHAR_UTILITIES"
    assert len(result.methods) > 0, "Should have methods"
    assert len(result.attributes) > 0, "Should have attributes"
    # Verify JSON roundtrip
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["class_name"] == "CL_ABAP_CHAR_UTILITIES"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se24_lookup_nonexistent(backend):
    """SE24: look up ZZZFAKE_CLASS returns SE24Error."""
    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()
    result = await _lookup_class_desktop(backend, "ZZZFAKE_CLASS")
    assert isinstance(result, SE24Error), f"Expected SE24Error, got {type(result).__name__}"
    assert result.class_name == "ZZZFAKE_CLASS"
    assert result.error
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se24_methods_have_visibility(backend):
    """SE24: methods should have visibility (public/protected/private)."""
    await backend.enter_transaction("SE24")
    await backend.wait_for_ready()
    result = await _lookup_class_desktop(backend, "CL_ABAP_CHAR_UTILITIES")
    assert isinstance(result, SE24Entry)
    for method in result.methods:
        assert method.visibility in ("public", "protected", "private")
    await go_home(backend)
