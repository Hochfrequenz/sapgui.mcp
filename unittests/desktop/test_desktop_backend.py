"""Tests for DesktopBackend — Navigation + Phase 2 primitives + Phase 3 Editor/Popup."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from unittests.desktop.conftest import make_mock_session

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


class TestDesktopBackendType:
    def test_backend_type_is_desktop(self):
        from sapguimcp.backend.desktop import DesktopBackend

        backend = DesktopBackend.__new__(DesktopBackend)
        assert backend.backend_type == "desktop"


class TestDesktopBackendLogin:
    @pytest.mark.anyio
    async def test_login_calls_login_helper(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()

        async def mock_run(fn):
            return fn()

        with patch("sapguimcp.backend.desktop._sapsucker_login", return_value=session):
            backend = DesktopBackend(com_thread=MagicMock())
            backend.com.run = mock_run
            result = await backend.login("ignored", "user", "pass", "100", "EN", connection_name="TEST_CONN")
            assert result.success is True
            assert result.user == "TESTUSER"


class TestDesktopBackendEnterTransaction:
    @pytest.mark.anyio
    async def test_enter_transaction(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        # Make com.run actually execute the function
        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.enter_transaction("SE16")
        assert result.success is True
        assert result.tcode == "SE16"

    @pytest.mark.anyio
    async def test_enter_transaction_pure_navigation_slash_n(self):
        """GH-555: /n (reset to Easy Access) must not fail TCode validation."""
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.enter_transaction("/n")
        assert result.success is True
        assert result.tcode == "/N"

    @pytest.mark.anyio
    async def test_enter_transaction_slash_n_with_tcode(self):
        """/nSE24 should strip prefix and use SE24 as tcode."""
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.enter_transaction("/nSE24")
        assert result.success is True
        assert result.tcode == "SE24"


class TestDesktopBackendSessionStatus:
    @pytest.mark.anyio
    async def test_get_session_status_active(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.get_session_status()
        assert result.success is True
        assert result.status == "active"


class TestDesktopBackendPressKey:
    @pytest.mark.anyio
    async def test_press_enter(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.press_key("Enter")
        assert result.success is True
        assert result.key == "Enter"
        wnd.send_v_key.assert_called_once_with(0)

    @pytest.mark.anyio
    async def test_press_f5(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.press_key("F5")
        wnd.send_v_key.assert_called_once_with(5)


def _make_backend_with_finder(session, finder_patch_target, finder_return):
    """Helper to create a backend with a mocked element finder function."""
    from sapguimcp.backend.desktop import DesktopBackend

    backend = DesktopBackend.__new__(DesktopBackend)
    backend._session = session

    async def mock_run(fn):
        return fn()

    backend.com = MagicMock()
    backend.com.run = mock_run
    return backend


class TestDesktopBackendFillField:
    @pytest.mark.anyio
    async def test_fill_field_sets_text(self):
        from sapguimcp.backend.desktop import DesktopBackend

        field_mock = MagicMock()
        field_mock.com = field_mock  # unwrap returns self
        field_mock.Type = "GuiTextField"  # not a combobox
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch("sapguimcp.backend.desktop._dump_flat_tree", return_value=[]):
            with patch(
                "sapguimcp.backend.desktop.find_field_by_label",
                return_value=field_mock,
            ):
                await backend.fill_field("Material", "123")
                assert field_mock.Text == "123"

    @pytest.mark.anyio
    async def test_fill_field_raises_when_not_found(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch("sapguimcp.backend.desktop._dump_flat_tree", return_value=[]):
            with patch(
                "sapguimcp.backend.desktop.find_field_by_label",
                return_value=None,
            ):
                with pytest.raises(ValueError, match="Field not found"):
                    await backend.fill_field("Missing", "val")


class TestDesktopBackendClickButton:
    @pytest.mark.anyio
    async def test_click_button_calls_press(self):
        from sapguimcp.backend.desktop import DesktopBackend

        btn_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch(
            "sapguimcp.backend.desktop.find_button_by_label",
            return_value=btn_mock,
        ):
            await backend.click_button("Execute")
            btn_mock.press.assert_called_once()

    @pytest.mark.anyio
    async def test_click_button_raises_when_not_found(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch(
            "sapguimcp.backend.desktop.find_button_by_label",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="Button not found"):
                await backend.click_button("Missing")


class TestDesktopBackendClickTab:
    @pytest.mark.anyio
    async def test_click_tab_calls_select(self):
        from sapguimcp.backend.desktop import DesktopBackend

        tab_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch(
            "sapguimcp.backend.desktop.find_tab_by_label",
            return_value=tab_mock,
        ):
            await backend.click_tab("Address")
            tab_mock.select.assert_called_once()


class TestDesktopBackendSetCheckbox:
    @pytest.mark.anyio
    async def test_set_checkbox_true(self):
        from sapguimcp.backend.desktop import DesktopBackend

        chk_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch(
            "sapguimcp.backend.desktop.find_checkbox_by_label",
            return_value=chk_mock,
        ):
            await backend.set_checkbox("Active", True)
            assert chk_mock.selected is True


class TestDesktopBackendSetRadioButton:
    @pytest.mark.anyio
    async def test_set_radio_button(self):
        from sapguimcp.backend.desktop import DesktopBackend

        rad_mock = MagicMock()
        session = make_mock_session()

        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch(
            "sapguimcp.backend.desktop.find_radio_by_label",
            return_value=rad_mock,
        ):
            await backend.set_radio_button("Option A")
            assert rad_mock.selected is True


class TestDesktopBackendFillForm:
    @pytest.mark.anyio
    async def test_fill_form_fills_fields(self):
        from sapguimcp.backend.desktop import DesktopBackend

        field1 = MagicMock()
        field1.com = field1
        field1.Type = "GuiTextField"
        field2 = MagicMock()
        field2.com = field2
        field2.Type = "GuiTextField"

        def mock_find(session, label, flat_tree, **kwargs):
            return {"Material": field1, "Plant": field2}.get(label)

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch("sapguimcp.backend.desktop._dump_flat_tree", return_value=[]):
            with patch(
                "sapguimcp.backend.desktop.find_field_by_label",
                side_effect=mock_find,
            ):
                result = await backend.fill_form({"Material": "123", "Plant": "1000"})
                assert result.success is True
                assert result.filled == ["Material", "Plant"]
                assert field1.Text == "123"
                assert field2.Text == "1000"

    @pytest.mark.anyio
    async def test_fill_form_reports_not_found(self):
        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        with patch("sapguimcp.backend.desktop._dump_flat_tree", return_value=[]):
            with patch(
                "sapguimcp.backend.desktop.find_field_by_label",
                return_value=None,
            ):
                result = await backend.fill_form({"Missing": "val"})
                assert result.success is False
                assert "Missing" in result.not_found


# ---- Phase 3: Editor + Popup ----


def _make_backend(session):
    """Create a DesktopBackend wired to a mock session with async mock_run."""
    from sapguimcp.backend.desktop import DesktopBackend

    backend = DesktopBackend.__new__(DesktopBackend)
    backend._session = session

    async def mock_run(fn):
        return fn()

    backend.com = MagicMock()
    backend.com.run = mock_run
    return backend


def _make_session_with_popup(popup_text="Information", popup_buttons=None, popup_labels=None):
    """Create a mock session where wnd[1] exists as a popup."""
    session = make_mock_session()
    popup = MagicMock()
    popup.text = popup_text

    # Build mock dump_tree elements
    elems = []
    for btn_text, btn_id in popup_buttons or []:
        elem = SimpleNamespace(
            type_as_number=40,
            text=btn_text,
            id=btn_id,
            name=btn_text,
            children=[],
        )
        elems.append(elem)
    for lbl_text in popup_labels or []:
        elem = SimpleNamespace(
            type_as_number=30,
            text=lbl_text,
            id="wnd[1]/usr/lbl" + lbl_text.replace(" ", ""),
            name=lbl_text,
            children=[],
        )
        elems.append(elem)

    # The root popup element in the tree
    root = SimpleNamespace(
        type_as_number=70,  # GuiModalWindow
        text=popup_text,
        id="wnd[1]",
        name="wnd1",
        children=elems,
    )
    popup.dump_tree.return_value = [root]

    # Patch find_by_id to also return popup for wnd[1]
    original_find = session.find_by_id

    def find_with_popup(element_id, raise_error=True):
        if element_id == "wnd[1]":
            return popup
        return original_find(element_id, raise_error=raise_error)

    session.find_by_id = find_with_popup
    return session, popup


class TestCheckPopup:
    @pytest.mark.anyio
    async def test_check_popup_returns_none_when_no_popup(self):
        """check_popup returns None when wnd[1] does not exist."""
        session = make_mock_session()
        backend = _make_backend(session)

        result = await backend.check_popup()
        assert result is None

    @pytest.mark.anyio
    async def test_check_popup_returns_popup_info(self):
        """check_popup returns PopupInfo with message and buttons."""
        session, popup = _make_session_with_popup(
            popup_text="Confirm action",
            popup_buttons=[("Yes", "wnd[1]/tbar[0]/btn[0]"), ("No", "wnd[1]/tbar[0]/btn[1]")],
            popup_labels=["Are you sure?"],
        )
        backend = _make_backend(session)

        result = await backend.check_popup()
        assert result is not None
        assert "Are you sure?" in result.message
        assert len(result.buttons) == 2
        assert result.buttons[0].label == "Yes"
        assert result.buttons[1].label == "No"


class TestDismissPopup:
    @pytest.mark.anyio
    async def test_dismiss_popup_sends_enter(self):
        """dismiss_popup sends Enter (VKey 0) when no button_label given."""
        session, popup = _make_session_with_popup(popup_text="Info")
        backend = _make_backend(session)

        result = await backend.dismiss_popup()
        assert result.success is True
        assert result.popup_closed is True
        popup.send_v_key.assert_called_once_with(0)

    @pytest.mark.anyio
    async def test_dismiss_popup_with_close_button(self):
        """dismiss_popup calls close() when use_close_button=True."""
        session, popup = _make_session_with_popup(popup_text="Info")
        backend = _make_backend(session)

        result = await backend.dismiss_popup(use_close_button=True)
        assert result.success is True
        assert result.popup_closed is True
        popup.close.assert_called_once()


class TestReadEditorSource:
    @pytest.mark.anyio
    async def test_read_editor_source_returns_none_when_no_editor(self):
        """read_editor_source returns None when no editor shell exists."""
        session = make_mock_session()
        usr = MagicMock()
        # dump_tree returns no GuiShell elements
        usr.dump_tree.return_value = [
            SimpleNamespace(
                type_as_number=30,
                text="Some Label",
                id="wnd[0]/usr/lbl1",
                name="lbl1",
                children=[],
            )
        ]

        original_find = session.find_by_id

        def find_with_usr(element_id, raise_error=True):
            if element_id == "wnd[0]/usr":
                return usr
            return original_find(element_id, raise_error=raise_error)

        session.find_by_id = find_with_usr
        backend = _make_backend(session)

        result = await backend.read_editor_source()
        assert result is None


class TestCheckAndActivate:
    @pytest.mark.anyio
    async def test_check_and_activate_sends_vkeys(self):
        """check_and_activate sends VKey 26 (check) and 27 (activate)."""
        session = make_mock_session()
        wnd = session.find_by_id("wnd[0]")
        sbar = session.find_by_id("wnd[0]/sbar")
        sbar.text = "Object activated"
        sbar.message_type = "S"

        backend = _make_backend(session)

        result = await backend.check_and_activate()
        assert result.success is True
        assert result.activated is True
        # VKey 26 (check) and 27 (activate) should both be called
        calls = wnd.send_v_key.call_args_list
        assert len(calls) == 2
        assert calls[0].args[0] == 26
        assert calls[1].args[0] == 27


class TestDesktopBackendReadTable:
    """GH-553: read_table must handle column_order as Python list (sapsucker)."""

    @pytest.mark.anyio
    async def test_read_table_column_order_as_list(self):
        """column_order returns a Python list from sapsucker, not a COM collection."""
        from sapsucker.components.grid import GuiGridView

        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        # Create a mock that passes isinstance(grid, GuiGridView)
        mock_grid = MagicMock(spec=GuiGridView)
        mock_grid.row_count = 2
        mock_grid.column_order = ["COL_A", "COL_B"]  # Python list, not COM collection
        mock_grid.get_cell_value = MagicMock(side_effect=lambda r, c: f"val_{r}_{c}")

        # Mock dump_tree to return a grid element
        mock_elem = MagicMock()
        mock_elem.type_as_number = 122
        mock_elem.id = "wnd[0]/shellcont/shell"
        mock_elem.children = []

        wnd = session.find_by_id("wnd[0]")
        wnd.dump_tree = MagicMock(return_value=[mock_elem])

        # Route find_by_id to return the mock grid for the grid ID
        original_find = session.find_by_id

        def patched_find(element_id, raise_error=True):
            if element_id == "wnd[0]/shellcont/shell":
                return mock_grid
            return original_find(element_id, raise_error)

        session.find_by_id = patched_find

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.read_table(start_row=1, max_rows=2)

        assert result.success is True
        assert result.headers == ["COL_A", "COL_B"]
        assert len(result.rows) == 2

    @pytest.mark.anyio
    async def test_read_table_column_order_as_com_collection(self):
        """column_order as COM collection (with .Count attribute) still works."""
        from sapsucker.components.grid import GuiGridView

        from sapguimcp.backend.desktop import DesktopBackend

        session = make_mock_session()
        backend = DesktopBackend.__new__(DesktopBackend)
        backend._session = session

        # Mock COM collection for column_order
        com_collection = MagicMock()
        com_collection.Count = 2
        com_collection.side_effect = lambda i: ["COL_X", "COL_Y"][i]

        mock_grid = MagicMock(spec=GuiGridView)
        mock_grid.row_count = 1
        mock_grid.column_order = com_collection
        mock_grid.get_cell_value = MagicMock(return_value="v")

        mock_elem = MagicMock()
        mock_elem.type_as_number = 122
        mock_elem.id = "wnd[0]/shellcont/shell"
        mock_elem.children = []

        wnd = session.find_by_id("wnd[0]")
        wnd.dump_tree = MagicMock(return_value=[mock_elem])

        original_find = session.find_by_id

        def patched_find(element_id, raise_error=True):
            if element_id == "wnd[0]/shellcont/shell":
                return mock_grid
            return original_find(element_id, raise_error)

        session.find_by_id = patched_find

        async def mock_run(fn):
            return fn()

        backend.com = MagicMock()
        backend.com.run = mock_run

        result = await backend.read_table(start_row=1, max_rows=1)

        assert result.success is True
        assert result.headers == ["COL_X", "COL_Y"]
        assert len(result.rows) == 1
