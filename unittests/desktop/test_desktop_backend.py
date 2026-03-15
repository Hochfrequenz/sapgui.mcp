"""Tests for DesktopBackend — Navigation methods."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from unittests.desktop.conftest import make_mock_session


class TestDesktopBackendLogin:
    @pytest.mark.anyio
    async def test_login_calls_login_helper(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        mock_settings = MagicMock()
        mock_settings.sap_connection_name = "TEST_CONN"

        async def mock_run(fn):
            return fn()

        with (
            patch("sapwebguimcp.backend.desktop._login_mod.login", return_value=session),
            patch("sapwebguimcp.models.config.get_settings", return_value=mock_settings),
        ):
            backend = DesktopBackend(com_thread=MagicMock())
            backend._com.run = mock_run
            result = await backend.login("ignored", "user", "pass", "100", "EN")
            assert result.success is True
            assert result.user == "TESTUSER"


class TestDesktopBackendEnterTransaction:
    @pytest.mark.anyio
    async def test_enter_transaction(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        # Make com.run actually execute the function
        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.enter_transaction("SE16")
        assert result.success is True
        assert result.tcode == "SE16"


class TestDesktopBackendSessionStatus:
    @pytest.mark.anyio
    async def test_get_session_status_active(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.get_session_status()
        assert result.success is True
        assert result.status == "active"


class TestDesktopBackendPressKey:
    @pytest.mark.anyio
    async def test_press_enter(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.press_key("Enter")
        assert result.success is True
        assert result.key == "Enter"
        wnd.send_v_key.assert_called_once_with(0)

    @pytest.mark.anyio
    async def test_press_f5(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        result = await backend.press_key("F5")
        wnd.send_v_key.assert_called_once_with(5)
