"""Tests for SAP identity capture during login."""

from unittest.mock import AsyncMock, patch

import pytest

from sapguimcp.models.middleware import SapIdentity

# _capture_sap_identity moved from sap_tools to WebGuiBackend.
# We test it via the backend instance method now.

_PATCH_SET_IDENTITY = "sapguimcp.backend.webgui.backend.set_sap_identity"


def _make_backend(page: AsyncMock) -> "WebGuiBackend":  # type: ignore[name-defined]
    """Create a WebGuiBackend wrapping a mock page."""
    from sapguimcp.backend.webgui.backend import WebGuiBackend

    return WebGuiBackend(page)


@pytest.mark.anyio
async def test_capture_sap_identity_success():
    """When DOM returns a username, identity should be set."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": "KLEINK"}

    backend = _make_backend(page)
    with patch(_PATCH_SET_IDENTITY) as mock_set:
        await backend._capture_sap_identity("https://sap-prod.acme.com/sap/bc/gui", "100", "session-1")

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

    backend = _make_backend(page)
    with patch(_PATCH_SET_IDENTITY) as mock_set:
        await backend._capture_sap_identity("https://sap.acme.com/path", "100", "session-1")

    mock_set.assert_not_called()


@pytest.mark.anyio
async def test_capture_sap_identity_null_user():
    """When DOM returns null user, identity should NOT be set."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": None}

    backend = _make_backend(page)
    with patch(_PATCH_SET_IDENTITY) as mock_set:
        await backend._capture_sap_identity("https://sap.acme.com/path", "100", "session-1")

    mock_set.assert_not_called()


@pytest.mark.anyio
async def test_capture_sap_identity_schemeless_url():
    """URLs without scheme should fall back to 'unknown' hostname."""
    page = AsyncMock()
    page.evaluate.return_value = {"user": "JSMITH"}

    backend = _make_backend(page)
    with patch(_PATCH_SET_IDENTITY) as mock_set:
        await backend._capture_sap_identity("sap-server/path", "200", "s1")

    identity = mock_set.call_args[0][1]
    assert identity.sap_host == "unknown"
