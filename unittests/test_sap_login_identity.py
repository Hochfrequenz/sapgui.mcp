"""Tests for SAP identity capture during login."""

from unittest.mock import AsyncMock, patch

import pytest

from sapwebguimcp.models.middleware import SapIdentity

# Import the helper function - it's module-level in sap_tools
# We need to test it directly since testing full sap_login requires browser setup


@pytest.mark.anyio
async def test_capture_sap_identity_success():
    """When DOM returns a username, identity should be set."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": "KLEINK"}

    with patch("sapwebguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        from sapwebguimcp.tools.sap_tools import _capture_sap_identity

        await _capture_sap_identity(page, "https://sap-prod.acme.com/sap/bc/gui", "100", "session-1")

    mock_set.assert_called_once()
    identity = mock_set.call_args[0][1]
    assert identity.sap_user == "KLEINK"
    assert identity.sap_host == "sap-prod.acme.com"
    assert identity.sap_mandant == "100"


@pytest.mark.anyio
async def test_capture_sap_identity_dom_fails():
    """When DOM extraction fails, identity should NOT be set."""
    page = AsyncMock()
    page.evaluate.side_effect = Exception("Element not found")

    with patch("sapwebguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        from sapwebguimcp.tools.sap_tools import _capture_sap_identity

        await _capture_sap_identity(page, "https://sap.acme.com/path", "100", "session-1")

    mock_set.assert_not_called()


@pytest.mark.anyio
async def test_capture_sap_identity_null_user():
    """When DOM returns null user, identity should NOT be set."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": None}

    with patch("sapwebguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        from sapwebguimcp.tools.sap_tools import _capture_sap_identity

        await _capture_sap_identity(page, "https://sap.acme.com/path", "100", "session-1")

    mock_set.assert_not_called()


@pytest.mark.anyio
async def test_capture_sap_identity_schemeless_url():
    """URLs without scheme should fall back to 'unknown' hostname."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": "JSMITH"}

    with patch("sapwebguimcp.tools.sap_tools.set_sap_identity") as mock_set:
        from sapwebguimcp.tools.sap_tools import _capture_sap_identity

        await _capture_sap_identity(page, "sap-server/path", "200", "s1")

    identity = mock_set.call_args[0][1]
    assert identity.sap_host == "unknown"
