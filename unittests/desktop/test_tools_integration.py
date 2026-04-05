"""Cross-cutting integration tests and stub error tests for desktop backend.

Transaction-specific tests live in their own files:
- test_se16_integration.py
- test_sm37_integration.py
- test_sm30_integration.py
- test_se09_integration.py
- test_slg1_integration.py
- test_st22_integration.py
"""

import json
import sys

import pytest

from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_screen_info_round_trip(backend):
    """get_screen_info returns correct data, serializes as ScreenInfo model."""
    await backend.enter_transaction("SE16")
    info = await backend.get_screen_info()
    assert info.success
    assert info.transaction == "SE16"
    assert info.title
    assert info.program
    # Serializes
    parsed = json.loads(info.model_dump_json())
    assert parsed["transaction"] == "SE16"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_backend_detected_as_desktop(backend):
    """backend_type property returns 'desktop' for DesktopBackend."""
    assert backend.backend_type == "desktop"


@skip_no_sap
@pytest.mark.anyio
async def test_enter_transaction_slash_n_does_not_crash(backend):
    """GH-555: enter_transaction('/n') must succeed, not fail TCode validation."""
    result = await backend.enter_transaction("/n")
    assert result.success is True
    assert result.tcode == "/N"


@skip_no_sap
@pytest.mark.anyio
async def test_reset_first_round_trip(backend):
    """GH-555: navigate to SE16, then reset_first back to Easy Access + SE24."""
    # Navigate somewhere first
    r1 = await backend.enter_transaction("SE16")
    assert r1.success is True

    # Reset via /n (the operation that was crashing)
    r2 = await backend.enter_transaction("/n")
    assert r2.success is True

    # Now navigate to another tcode (simulates reset_first workflow)
    await backend.wait_for_ready()
    r3 = await backend.enter_transaction("SE24")
    assert r3.success is True
    assert r3.tcode == "SE24"
    await go_home(backend)
