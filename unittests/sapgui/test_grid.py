"""Tests for GuiGridView missing methods — issue #473."""

from unittest.mock import MagicMock

from sapwebguimcp.sapgui.components.grid import GuiGridView


def _make_grid():
    com = MagicMock()
    com.TypeAsNumber = 122
    com.SubType = "GridView"
    return GuiGridView(com)


class TestGuiGridViewCellInfo:
    def test_get_cell_color(self):
        grid = _make_grid()
        grid._com.GetCellColor.return_value = 3
        assert grid.get_cell_color(0, "COL") == 3
        grid._com.GetCellColor.assert_called_once_with(0, "COL")

    def test_get_cell_icon(self):
        grid = _make_grid()
        grid._com.GetCellIcon.return_value = "@01@"
        assert grid.get_cell_icon(0, "COL") == "@01@"

    def test_get_display_cell_value(self):
        grid = _make_grid()
        grid._com.GetDisplayCellValue.return_value = "1,234.56"
        assert grid.get_display_cell_value(0, "COL") == "1,234.56"

    def test_modify_cell(self):
        grid = _make_grid()
        grid.modify_cell(0, "COL", "new")
        grid._com.ModifyCell.assert_called_once_with(0, "COL", "new")

    def test_is_cell_hotspot(self):
        grid = _make_grid()
        grid._com.IsCellHotspot.return_value = True
        assert grid.is_cell_hotspot(0, "COL") is True

    def test_get_cell_tooltip(self):
        grid = _make_grid()
        grid._com.GetCellTooltip.return_value = "hint"
        assert grid.get_cell_tooltip(0, "COL") == "hint"


class TestGuiGridViewColumnInfo:
    def test_get_column_title_by_name(self):
        grid = _make_grid()
        grid._com.GetColumnTitleByName.return_value = "Material"
        assert grid.get_column_title_by_name("MATNR") == "Material"

    def test_get_column_tooltip(self):
        grid = _make_grid()
        grid._com.GetColumnTooltip.return_value = "tip"
        assert grid.get_column_tooltip("COL") == "tip"

    def test_get_column_data_type(self):
        grid = _make_grid()
        grid._com.GetColumnDataType.return_value = "CHAR"
        assert grid.get_column_data_type("COL") == "CHAR"
