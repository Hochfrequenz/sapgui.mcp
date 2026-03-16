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

from sapwebguimcp.models.se37_models import SE37Result
from sapwebguimcp.tools._backend_utils import _is_desktop_backend
from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


# ---------------------------------------------------------------------------
# Stub tools -- verify they return clear errors
# ---------------------------------------------------------------------------


def test_se37_stub_returns_error():
    """SE37 desktop stub returns 'not supported' error model."""
    result = SE37Result.failure("SE37 lookup is not yet supported on the desktop backend")
    assert not result.success
    assert "not" in result.error.lower() and "support" in result.error.lower()
    assert result.model_dump_json()


# ---------------------------------------------------------------------------
# Cross-cutting
# ---------------------------------------------------------------------------


@skip_not_sap
@skip_no_creds
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


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_backend_detected_as_desktop(backend):
    """_is_desktop_backend returns True for DesktopBackend."""
    assert _is_desktop_backend(backend) is True
