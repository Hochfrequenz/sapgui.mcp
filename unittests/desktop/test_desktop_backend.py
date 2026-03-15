"""Tests for DesktopBackend — Navigation + Phase 2 primitives."""

from __future__ import annotations

from types import SimpleNamespace
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


def _make_backend_with_finder(session, finder_patch_target, finder_return):
    """Helper to create a backend with a mocked element finder function."""
    from sapwebguimcp.backend.desktop import DesktopBackend

    backend = DesktopBackend.__new__(DesktopBackend)
    backend._session = session

    async def mock_run(fn):
        return fn()

    backend._com = MagicMock()
    backend._com.run = mock_run
    return backend


class TestDesktopBackendFillField:
    @pytest.mark.anyio
    async def test_fill_field_sets_text(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        field_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_field_by_label",
            return_value=field_mock,
        ):
            await backend.fill_field("Material", "123")
            assert field_mock.text == "123"

    @pytest.mark.anyio
    async def test_fill_field_raises_when_not_found(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_field_by_label",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Field not found"):
                await backend.fill_field("Missing", "val")


class TestDesktopBackendClickButton:
    @pytest.mark.anyio
    async def test_click_button_calls_press(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        btn_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_button_by_label",
            return_value=btn_mock,
        ):
            await backend.click_button("Execute")
            btn_mock.press.assert_called_once()

    @pytest.mark.anyio
    async def test_click_button_raises_when_not_found(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_button_by_label",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Button not found"):
                await backend.click_button("Missing")


class TestDesktopBackendClickTab:
    @pytest.mark.anyio
    async def test_click_tab_calls_select(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        tab_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_tab_by_label",
            return_value=tab_mock,
        ):
            await backend.click_tab("Address")
            tab_mock.select.assert_called_once()


class TestDesktopBackendSetCheckbox:
    @pytest.mark.anyio
    async def test_set_checkbox_true(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        chk_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_checkbox_by_label",
            return_value=chk_mock,
        ):
            await backend.set_checkbox("Active", True)
            assert chk_mock.selected is True


class TestDesktopBackendSetRadioButton:
    @pytest.mark.anyio
    async def test_set_radio_button(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        rad_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_radio_by_label",
            return_value=rad_mock,
        ):
            await backend.set_radio_button("Option A")
            assert rad_mock.selected is True


class TestDesktopBackendFillForm:
    @pytest.mark.anyio
    async def test_fill_form_fills_fields(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        field1 = MagicMock()
        field2 = MagicMock()

        def mock_find(session, label):
            return {"Material": field1, "Plant": field2}.get(label)

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_field_by_label",
            side_effect=mock_find,
        ):
            result = await backend.fill_form({"Material": "123", "Plant": "1000"})
            assert result.success is True
            assert result.filled == ["Material", "Plant"]
            assert field1.text == "123"
            assert field2.text == "1000"

    @pytest.mark.anyio
    async def test_fill_form_reports_not_found(self):
        from sapwebguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend._com = MagicMock()
        backend._com.run = mock_run

        with patch(
            "sapwebguimcp.backend.desktop.find_field_by_label",
            return_value=None,
        ):
            result = await backend.fill_form({"Missing": "val"})
            assert result.success is False
            assert "Missing" in result.not_found
