"""Tests for Chrome CDP detection at startup."""

import logging

import pytest
import respx
from httpx import ConnectError, Response

from sapwebguimcp.server import _check_cdp_available


class TestCdpCheck:
    """Tests for the CDP availability check."""

    @respx.mock
    @pytest.mark.anyio
    async def test_cdp_check_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logs info when Chrome CDP is reachable."""
        respx.get("http://localhost:9222/json/version").mock(return_value=Response(200, json={"Browser": "Chrome/120"}))
        with caplog.at_level(logging.INFO):
            await _check_cdp_available("http://localhost:9222")
        assert "Chrome CDP detected" in caplog.text

    @respx.mock
    @pytest.mark.anyio
    async def test_cdp_check_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logs warning with guidance when Chrome CDP is not reachable."""
        respx.get("http://localhost:9222/json/version").mock(side_effect=ConnectError("Connection refused"))
        with caplog.at_level(logging.WARNING):
            await _check_cdp_available("http://localhost:9222")
        assert "Chrome not detected" in caplog.text
        assert "--remote-debugging-port=9222" in caplog.text
