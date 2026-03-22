"""Tests for GuiTableControl missing methods — issue #476."""

from unittest.mock import MagicMock

from sapwebguimcp.sapgui.components.table import GuiTableControl, GuiTableRow


def _make_table():
    com = MagicMock()
    com.TypeAsNumber = 80
    return GuiTableControl(com)


class TestGuiTableControlMissing:
    def test_get_absolute_row(self):
        tbl = _make_table()
        row_com = MagicMock()
        tbl._com.GetAbsoluteRow.return_value = row_com
        result = tbl.get_absolute_row(5)
        tbl._com.GetAbsoluteRow.assert_called_once_with(5)
        assert isinstance(result, GuiTableRow)

    def test_columns_returns_collection(self):
        tbl = _make_table()
        tbl._com.Columns.Count = 3
        assert tbl.columns.Count == 3

    def test_rows_returns_collection(self):
        tbl = _make_table()
        tbl._com.Rows.Count = 5
        assert tbl.rows.Count == 5
