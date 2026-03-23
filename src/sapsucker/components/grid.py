"""GuiGridView — ALV grid control wrapper."""

# pylint: disable=too-many-public-methods

from __future__ import annotations

from sapsucker.components.shell import GuiShell

__all__ = ["GuiGridView"]


class GuiGridView(GuiShell):
    """Wraps the COM GuiGridView shell (SubType 'GridView').

    The ALV grid is the most commonly used data display in SAP.
    """

    @property
    def row_count(self) -> int:
        """Total number of rows."""
        return int(self._com.RowCount)

    @property
    def column_count(self) -> int:
        """Total number of columns."""
        return int(self._com.ColumnCount)

    @property
    def current_cell_row(self) -> int:
        """Row index of the current cell."""
        return int(self._com.CurrentCellRow)

    @current_cell_row.setter
    def current_cell_row(self, value: int) -> None:
        self._com.CurrentCellRow = value

    @property
    def current_cell_column(self) -> str:
        """Column name of the current cell."""
        return str(self._com.CurrentCellColumn)

    @current_cell_column.setter
    def current_cell_column(self, value: str) -> None:
        self._com.CurrentCellColumn = value

    @property
    def selected_rows(self) -> str:
        """Comma-separated string of selected row indexes."""
        return str(self._com.SelectedRows)

    @selected_rows.setter
    def selected_rows(self, value: str) -> None:
        self._com.SelectedRows = value

    @property
    def first_visible_row(self) -> int:
        """Index of the first visible row."""
        return int(self._com.FirstVisibleRow)

    @first_visible_row.setter
    def first_visible_row(self, value: int) -> None:
        self._com.FirstVisibleRow = value

    @property
    def column_order(self) -> list[str]:
        """Return the column order as a list of column names."""
        col = self._com.ColumnOrder
        return [str(col(i)) for i in range(col.Count)]

    @property
    def toolbar_button_count(self) -> int:
        """Number of toolbar buttons."""
        return int(self._com.ToolbarButtonCount)

    # --- Cell access ---

    def get_cell_value(self, row: int, column: str) -> str:
        """Read the value of a cell."""
        return str(self._com.GetCellValue(row, column))

    def set_cell_value(self, row: int, column: str, value: str) -> None:
        """Write a value to a cell (calls ModifyCell on COM)."""
        self._com.ModifyCell(row, column, value)

    def get_cell_changeable(self, row: int, column: str) -> bool:
        """Check if a cell is editable."""
        return bool(self._com.GetCellChangeable(row, column))

    def get_cell_type(self, row: int, column: str) -> str:
        """Return the type of a cell."""
        return str(self._com.GetCellType(row, column))

    # --- Click actions ---

    def click(self, row: int, column: str) -> None:
        """Single-click a cell."""
        self._com.Click(row, column)

    def double_click(self, row: int, column: str) -> None:
        """Double-click a cell."""
        self._com.DoubleClick(row, column)

    def click_current_cell(self) -> None:
        """Click the current cell."""
        self._com.ClickCurrentCell()

    def double_click_current_cell(self) -> None:
        """Double-click the current cell."""
        self._com.DoubleClickCurrentCell()

    # --- Selection ---

    def select_all(self) -> None:
        """Select all rows."""
        self._com.SelectAll()

    def clear_selection(self) -> None:
        """Clear the current selection."""
        self._com.ClearSelection()

    def select_column(self, column: str) -> None:
        """Select an entire column."""
        self._com.SelectColumn(column)

    def deselect_column(self, column: str) -> None:
        """Deselect an entire column."""
        self._com.DeselectColumn(column)

    # --- Navigation & buttons ---

    def current_cell_moved(self) -> None:
        """Notify the grid that the current cell has been moved."""
        self._com.CurrentCellMoved()

    def press_button(self, button_id: str) -> None:
        """Press a button embedded in the grid."""
        self._com.PressButton(button_id)

    def press_toolbar_button(self, button_id: str) -> None:
        """Press a toolbar button by ID."""
        self._com.PressToolbarButton(button_id)

    def press_enter(self) -> None:
        """Press Enter on the grid."""
        self._com.PressEnter()

    def press_toolbar_context_button(self, button_id: str) -> None:
        """Press a toolbar context button (opens dropdown)."""
        self._com.PressToolbarContextButton(button_id)

    def context_menu(self) -> None:
        """Open the context menu on the current cell."""
        self._com.ContextMenu()

    # --- Row manipulation ---

    def delete_rows(self, rows: str) -> None:
        """Delete rows by row string (e.g. '0,1,2')."""
        self._com.DeleteRows(rows)

    def duplicate_rows(self, rows: str) -> None:
        """Duplicate rows by row string."""
        self._com.DuplicateRows(rows)

    def insert_rows(self, rows: str) -> None:
        """Insert rows by row string."""
        self._com.InsertRows(rows)

    # --- Toolbar button info ---

    def get_toolbar_button_id(self, pos: int) -> str:
        """Return the toolbar button ID at the given position."""
        return str(self._com.GetToolbarButtonId(pos))

    def get_toolbar_button_text(self, pos: int) -> str:
        """Return the toolbar button text at the given position."""
        return str(self._com.GetToolbarButtonText(pos))

    def get_toolbar_button_type(self, pos: int) -> int:
        """Return the toolbar button type at the given position."""
        return int(self._com.GetToolbarButtonType(pos))

    def get_toolbar_button_enabled(self, pos: int) -> bool:
        """Whether the toolbar button at the given position is enabled."""
        return bool(self._com.GetToolbarButtonEnabled(pos))

    def get_toolbar_button_tooltip(self, pos: int) -> str:
        """Return the toolbar button tooltip at the given position."""
        return str(self._com.GetToolbarButtonTooltip(pos))

    # --- Cell info methods ---

    def get_cell_color(self, row: int, column: str) -> int:
        """Return the color index of a cell."""
        return int(self._com.GetCellColor(row, column))

    def get_cell_icon(self, row: int, column: str) -> str:
        """Return the icon string (e.g. '@01@') displayed in a cell."""
        return str(self._com.GetCellIcon(row, column))

    def get_cell_state(self, row: int, column: str) -> str:
        """Return the state of a cell ('Normal', 'Error', 'Warning', 'Info')."""
        return str(self._com.GetCellState(row, column))

    def modify_cell(self, row: int, column: str, value: str) -> None:
        """Modify a cell value. SAP spec alias for set_cell_value."""
        self._com.ModifyCell(row, column, value)

    def is_cell_hotspot(self, row: int, column: str) -> bool:
        """Return whether a cell is a clickable hotspot."""
        return bool(self._com.IsCellHotspot(row, column))

    def get_cell_tooltip(self, row: int, column: str) -> str:
        """Return the tooltip text for a cell."""
        return str(self._com.GetCellTooltip(row, column))

    # --- Column info methods ---

    def get_displayed_column_title(self, column: str) -> str:
        """Return the currently displayed title for a column."""
        return str(self._com.GetDisplayedColumnTitle(column))

    def get_column_tooltip(self, column: str) -> str:
        """Return the tooltip text for a column header."""
        return str(self._com.GetColumnTooltip(column))

    def get_column_data_type(self, column: str) -> str:
        """Return the ABAP data type of a column (e.g. 'CHAR', 'NUMC')."""
        return str(self._com.GetColumnDataType(column))
