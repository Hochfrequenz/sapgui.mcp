"""Integration tests for GuiGridView against SE16N ALV grid.

Opens SE16N, queries table T000 (clients), and tests grid methods
on the result. All tests are read-only.
"""

import sys
import time

import pytest

from unittests.conftest import is_sap_integration_test_machine

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="SAP GUI COM is Windows-only"),
    pytest.mark.skipif(
        not is_sap_integration_test_machine(),
        reason="SAP integration tests only run on authorized machines",
    ),
]


def _open_se16n_t000(session):
    """Navigate to SE16N, query table T000, return the grid."""
    from sapsucker.components.grid import GuiGridView

    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/nSE16N"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)

    # Fill table name
    try:
        table_field = session.find_by_id("wnd[0]/usr/ctxtGD-TAB")
        table_field.text = "T000"
    except Exception:
        pytest.skip("Could not find SE16N table name field")

    # Press F8 (Execute)
    session.find_by_id("wnd[0]").send_v_key(8)
    time.sleep(2)

    # SE16N places its ALV grid in different locations depending on
    # the SAP release.  The dock-shell path (shellcont/shell) is the
    # most common on newer systems; the usr/cntl* paths appear on
    # older releases or when the ALV is embedded in the user area.
    for grid_id in [
        "wnd[0]/shellcont/shell",
        "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell",
        "wnd[0]/usr/cntlGRID1/shellcont/shell",
        "wnd[0]/usr/cntlRESULT_LIST/shellcont/shell",
    ]:
        try:
            elem = session.find_by_id(grid_id)
            if isinstance(elem, GuiGridView):
                return elem
        except Exception:
            continue
    pytest.skip("Could not find ALV grid in SE16N")


@pytest.fixture
def se16n_grid(sap_desktop_session):
    """Provide an ALV grid from SE16N showing T000."""
    grid = _open_se16n_t000(sap_desktop_session)
    yield grid
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/n"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)


class TestGuiGridViewProperties:
    def test_row_count(self, se16n_grid):
        assert se16n_grid.row_count > 0

    def test_column_count(self, se16n_grid):
        assert se16n_grid.column_count > 0

    def test_column_order(self, se16n_grid):
        order = se16n_grid.column_order
        assert isinstance(order, list)
        assert len(order) > 0
        assert isinstance(order[0], str)

    def test_toolbar_button_count(self, se16n_grid):
        assert se16n_grid.toolbar_button_count > 0

    def test_first_visible_row(self, se16n_grid):
        assert isinstance(se16n_grid.first_visible_row, int)
        assert se16n_grid.first_visible_row >= 0


class TestGuiGridViewCellAccess:
    def test_get_cell_value(self, se16n_grid):
        val = se16n_grid.get_cell_value(0, "MANDT")
        assert isinstance(val, str)
        assert len(val) > 0

    def test_get_cell_changeable(self, se16n_grid):
        assert se16n_grid.get_cell_changeable(0, "MANDT") is False

    def test_get_cell_type(self, se16n_grid):
        cell_type = se16n_grid.get_cell_type(0, "MANDT")
        assert isinstance(cell_type, str)


class TestGuiGridViewNewMethods:
    def test_get_cell_color(self, se16n_grid):
        color = se16n_grid.get_cell_color(0, "MANDT")
        assert isinstance(color, int)

    def test_get_cell_icon(self, se16n_grid):
        icon = se16n_grid.get_cell_icon(0, "MANDT")
        assert isinstance(icon, str)

    def test_get_cell_state(self, se16n_grid):
        state = se16n_grid.get_cell_state(0, "MANDT")
        assert state in ("Normal", "Error", "Warning", "Info", "")

    def test_is_cell_hotspot(self, se16n_grid):
        result = se16n_grid.is_cell_hotspot(0, "MANDT")
        assert isinstance(result, bool)

    def test_get_cell_tooltip(self, se16n_grid):
        tooltip = se16n_grid.get_cell_tooltip(0, "MANDT")
        assert isinstance(tooltip, str)

    def test_get_displayed_column_title(self, se16n_grid):
        title = se16n_grid.get_displayed_column_title("MANDT")
        assert isinstance(title, str)
        assert len(title) > 0

    def test_get_column_tooltip(self, se16n_grid):
        tooltip = se16n_grid.get_column_tooltip("MANDT")
        assert isinstance(tooltip, str)

    def test_get_column_data_type(self, se16n_grid):
        dtype = se16n_grid.get_column_data_type("MANDT")
        assert isinstance(dtype, str)


class TestGuiGridViewToolbar:
    def test_get_toolbar_button_id(self, se16n_grid):
        btn_id = se16n_grid.get_toolbar_button_id(0)
        assert isinstance(btn_id, str)

    def test_get_toolbar_button_enabled(self, se16n_grid):
        enabled = se16n_grid.get_toolbar_button_enabled(0)
        assert isinstance(enabled, bool)

    def test_get_toolbar_button_tooltip(self, se16n_grid):
        tooltip = se16n_grid.get_toolbar_button_tooltip(0)
        assert isinstance(tooltip, str)


class TestGuiGridViewSelection:
    def test_select_all_and_clear(self, se16n_grid):
        se16n_grid.select_all()
        # selected_rows returns a string like "0,1,2" or "0-5" (range)
        assert se16n_grid.selected_rows != ""
        se16n_grid.clear_selection()
        assert se16n_grid.selected_rows == ""
