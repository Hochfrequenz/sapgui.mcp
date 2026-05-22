"""Integration tests for SE93 (Transaction Maintenance) on desktop backend."""

import json
import sys

import pytest

from sapguimcp.models.se93_models import SE93Entry, SE93Error
from sapguimcp.tools.se93_tools import _lookup_tcode_desktop
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_se93_lookup_se16(backend):
    """SE93: look up SE16 returns a dialog transaction with program and screen."""
    await backend.enter_transaction("SE93")
    await backend.wait_for_ready()
    result = await _lookup_tcode_desktop(backend, "SE16")
    assert isinstance(result, SE93Entry), f"Expected SE93Entry, got {type(result).__name__}: {result}"
    assert result.tcode == "SE16"
    assert result.description, "SE16 should have a description"
    assert result.program, "SE16 should have a program"
    assert result.transaction_type == "dialog"
    assert result.screen_number, "Dialog transaction should have screen number"
    # Verify JSON roundtrip
    json_str = result.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["tcode"] == "SE16"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se93_lookup_nonexistent(backend):
    """SE93: look up ZZZFAKE99 returns SE93Error."""
    await backend.enter_transaction("SE93")
    await backend.wait_for_ready()
    result = await _lookup_tcode_desktop(backend, "ZZZFAKE99")
    assert isinstance(result, SE93Error), f"Expected SE93Error, got {type(result).__name__}"
    assert result.tcode == "ZZZFAKE99"
    assert result.error, "Should have an error message"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_se93_gui_capabilities(backend):
    """SE93: SE16 should report GUI capability flags."""
    await backend.enter_transaction("SE93")
    await backend.wait_for_ready()
    result = await _lookup_tcode_desktop(backend, "SE16")
    assert isinstance(result, SE93Entry)
    # Verify GUI flags are booleans (actual values depend on system config)
    assert isinstance(result.gui_html, bool)
    assert isinstance(result.gui_java, bool)
    assert isinstance(result.gui_windows, bool)
    await go_home(backend)
