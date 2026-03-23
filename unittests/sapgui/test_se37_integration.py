"""Integration tests for GuiTableControl and GuiTab against SE37.

Opens SE37 in display mode for BAPI_USER_GET_DETAIL, exercises
table control and tab methods. All tests are read-only.
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

# Known SE37 element IDs for BAPI_USER_GET_DETAIL display mode
_TAB_STRIP_ID = "wnd[0]/usr/tabsFUNC_TAB_STRIP"
_TAB_IMPORT_ID = f"{_TAB_STRIP_ID}/tabpIMPORT"
_TAB_EXPORT_ID = f"{_TAB_STRIP_ID}/tabpEXPORT"
_TAB_TABLES_ID = f"{_TAB_STRIP_ID}/tabpTABLES"
_TAB_EXCEPT_ID = f"{_TAB_STRIP_ID}/tabpEXCEPT"


def _open_se37_display(session):
    """Navigate to SE37, display BAPI_USER_GET_DETAIL."""
    okcode = session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/nSE37"
    session.find_by_id("wnd[0]").send_v_key(0)
    time.sleep(1)

    try:
        fm_field = session.find_by_id("wnd[0]/usr/ctxtRS38L-NAME")
        fm_field.text = "BAPI_USER_GET_DETAIL"
    except Exception:
        pytest.skip("Could not find SE37 function module field")

    # Press F7 (Display)
    session.find_by_id("wnd[0]").send_v_key(7)
    time.sleep(1)


def _find_table_in_tab(session, tab_id):
    """Select a tab and find the table control inside it via raw COM traversal.

    SE37 tables live inside a subscreen of each tab.  ``dump_tree`` does not
    reliably traverse into SE37 subscreens, so we walk ``Children`` on the
    raw COM object and wrap the result directly.

    Important: after ``tab.select()`` the original COM reference can become
    stale, so we re-fetch the tab via ``find_by_id`` before walking.
    """
    from sapsucker._factory import wrap_com_object

    tab = session.find_by_id(tab_id)
    tab.select()
    time.sleep(0.5)

    # Re-fetch to get a fresh COM reference after selection
    tab = session.find_by_id(tab_id)

    def _walk(com_obj, depth=0, max_depth=6):
        """Depth-first search for a GuiTableControl (type 80)."""
        try:
            if com_obj.TypeAsNumber == 80:
                return com_obj
        except Exception:
            return None
        if depth >= max_depth:
            return None
        try:
            children = com_obj.Children
            if children:
                for i in range(children.Count):
                    result = _walk(children.Item(i), depth + 1, max_depth)
                    if result is not None:
                        return result
        except Exception:
            pass
        return None

    raw_table = _walk(tab._com)
    if raw_table is None:
        return None
    return wrap_com_object(raw_table)


@pytest.fixture
def se37_session(sap_desktop_session):
    """Provide a session at SE37 displaying BAPI_USER_GET_DETAIL."""
    _open_se37_display(sap_desktop_session)
    yield sap_desktop_session
    okcode = sap_desktop_session.find_by_id("wnd[0]/tbar[0]/okcd")
    okcode.text = "/n"
    sap_desktop_session.find_by_id("wnd[0]").send_v_key(0)


class TestGuiTab:
    def test_find_tab_strip(self, se37_session):
        """SE37 has a tab strip (FUNC_TAB_STRIP) for parameter pages."""
        from sapsucker.components.tab import GuiTabStrip

        tabstrip = se37_session.find_by_id(_TAB_STRIP_ID)
        assert isinstance(tabstrip, GuiTabStrip)

    def test_tab_select_import(self, se37_session):
        """Select the Import tab and verify no error."""
        from sapsucker.components.tab import GuiTab

        tab = se37_session.find_by_id(_TAB_IMPORT_ID)
        assert isinstance(tab, GuiTab)
        tab.select()

    def test_tab_select_export(self, se37_session):
        """Select the Export tab and verify no error."""
        from sapsucker.components.tab import GuiTab

        tab = se37_session.find_by_id(_TAB_EXPORT_ID)
        assert isinstance(tab, GuiTab)
        tab.select()

    def test_tab_select_tables(self, se37_session):
        """Select the Tables tab and verify no error."""
        from sapsucker.components.tab import GuiTab

        tab = se37_session.find_by_id(_TAB_TABLES_ID)
        assert isinstance(tab, GuiTab)
        tab.select()

    def test_tab_select_multiple(self, se37_session):
        """Cycle through several tabs to verify switching works."""
        from sapsucker.components.tab import GuiTab

        for tab_id in [_TAB_IMPORT_ID, _TAB_EXPORT_ID, _TAB_TABLES_ID, _TAB_EXCEPT_ID]:
            tab = se37_session.find_by_id(tab_id)
            assert isinstance(tab, GuiTab)
            tab.select()
            time.sleep(0.3)


class TestGuiTableControl:
    def test_table_properties(self, se37_session):
        """Find the Import parameters table and read its properties."""
        from sapsucker.components.table import GuiTableControl

        table = _find_table_in_tab(se37_session, _TAB_IMPORT_ID)
        if table is None:
            pytest.skip("No table control found in Import tab")
        assert isinstance(table, GuiTableControl)
        assert table.row_count >= 0
        assert table.visible_row_count > 0
        assert isinstance(table.current_row, int)

    def test_table_columns(self, se37_session):
        """Verify columns collection is accessible and non-empty."""
        table = _find_table_in_tab(se37_session, _TAB_IMPORT_ID)
        if table is None:
            pytest.skip("No table control found in Import tab")
        cols = table.columns
        assert cols is not None
        assert cols.Count > 0

    def test_table_rows(self, se37_session):
        """Verify rows collection is accessible."""
        table = _find_table_in_tab(se37_session, _TAB_IMPORT_ID)
        if table is None:
            pytest.skip("No table control found in Import tab")
        rows = table.rows
        assert rows is not None

    def test_table_get_cell(self, se37_session):
        """Verify get_cell returns a COM object for row 0, col 0."""
        table = _find_table_in_tab(se37_session, _TAB_IMPORT_ID)
        if table is None:
            pytest.skip("No table control found in Import tab")
        if table.row_count == 0 or table.columns.Count == 0:
            pytest.skip("Import table has no data")
        cell = table.get_cell(0, 0)
        assert cell is not None

    def test_table_in_export_tab(self, se37_session):
        """The Export tab also contains a table control."""
        from sapsucker.components.table import GuiTableControl

        table = _find_table_in_tab(se37_session, _TAB_EXPORT_ID)
        if table is None:
            pytest.skip("No table control found in Export tab")
        assert isinstance(table, GuiTableControl)
        assert table.row_count >= 0

    def test_get_absolute_row(self, se37_session):
        """get_absolute_row returns a GuiTableRow for visible rows."""
        from sapsucker.components.table import GuiTableRow

        table = _find_table_in_tab(se37_session, _TAB_IMPORT_ID)
        if table is None:
            pytest.skip("No table control found in Import tab")
        if table.row_count == 0:
            pytest.skip("Import table has no data")
        row = table.get_absolute_row(0)
        assert isinstance(row, GuiTableRow)


# ---------------------------------------------------------------------------
# GuiScrollbar integration tests via table's vertical scrollbar
# ---------------------------------------------------------------------------


class TestGuiScrollbar:
    def test_scrollbar_properties(self, se37_session):
        """Verify scrollbar properties on a table's vertical scrollbar."""
        from sapsucker.components.container import GuiScrollbar

        table = _find_table_in_tab(se37_session, _TAB_IMPORT_ID)
        if table is None:
            pytest.skip("No table control found in Import tab")

        # Access the raw COM vertical scrollbar and wrap it
        try:
            raw_sb = table.com.VerticalScrollbar
            sb = GuiScrollbar(raw_sb)
        except Exception:
            pytest.skip("No vertical scrollbar on this table")

        assert isinstance(sb.minimum, int)
        assert isinstance(sb.maximum, int)
        assert isinstance(sb.position, int)
        assert isinstance(sb.page_size, int)
        assert sb.minimum >= 0
        assert sb.maximum >= sb.minimum
        assert sb.page_size > 0
