"""Tests for Chrome CDP detection at startup."""

import logging

import pytest
import respx
from httpx import ConnectError, Response

from sapguimcp.server import _check_cdp_available


class TestCdpCheck:
    """Tests for the CDP availability check."""

    @respx.mock
    @pytest.mark.anyio
    async def test_cdp_check_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """Returns True and logs [OK] when Chrome CDP is reachable."""
        respx.get("http://localhost:9222/json/version").mock(return_value=Response(200, json={"Browser": "Chrome/120"}))
        with caplog.at_level(logging.INFO):
            result = await _check_cdp_available("http://localhost:9222")
        assert result is True
        assert "[OK]" in caplog.text
        assert "reachable" in caplog.text

    @respx.mock
    @pytest.mark.anyio
    async def test_cdp_check_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """Returns False and logs info when Chrome CDP is not reachable."""
        respx.get("http://localhost:9222/json/version").mock(side_effect=ConnectError("Connection refused"))
        with caplog.at_level(logging.INFO):
            result = await _check_cdp_available("http://localhost:9222")
        assert result is False
        assert "not detected" in caplog.text
        assert "auto-launch" in caplog.text
