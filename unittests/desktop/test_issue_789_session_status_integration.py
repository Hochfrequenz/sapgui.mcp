"""Integration test for issue #789 against a live SAP system.

`get_session_status` now forces a real COM round-trip (`FindById` on wnd[0])
instead of reading only the cached `session.info`, so it reports "active" only
when a real action would actually succeed. This test guards the happy path: a
genuinely logged-in session must still report "active" via the stronger probe.

The dead-handle path (stale interface -> friendly remediation message) is
covered by mocked unit tests in ``unittests/test_get_session_status_per_id.py``
and ``unittests/desktop/test_com_thread.py``; reproducing a truly wedged COM
handle live requires corrupting the connection and is intentionally not done
against the shared system.
"""

from __future__ import annotations

import sys

import pytest

from unittests.desktop.conftest import skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_live_session_reports_active(backend):
    """A logged-in session passes the real-COM-round-trip health check."""
    result = await backend.get_session_status()

    assert result.success is True
    assert result.status == "active"
    assert "Logged in as" in result.message
