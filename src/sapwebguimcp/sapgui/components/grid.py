"""GuiGridView — ALV grid control wrapper."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.shell import GuiShell


class GuiGridView(GuiShell):
    """Wraps the COM GuiGridView shell (SubType 'GridView').

    The ALV grid is the most commonly used data display in SAP.
    """

    @property
    def row_count(self) -> int:
        return self._com.RowCount

    @property
    def column_count(self) -> int:
        return self._com.ColumnCount

    @property
    def current_cell_row(self) -> int:
        return self._com.CurrentCellRow

    @current_cell_row.setter
    def current_cell_row(self, value: int) -> None:
        self._com.CurrentCellRow = value

    @property
    def current_cell_column(self) -> str:
        return self._com.CurrentCellColumn

    @current_cell_column.setter
    def current_cell_column(self, value: str) -> None:
        self._com.CurrentCellColumn = value

    @property
    def selected_rows(self) -> str:
        return self._com.SelectedRows

    @selected_rows.setter
    def selected_rows(self, value: str) -> None:
        self._com.SelectedRows = value

    @property
    def first_visible_row(self) -> int:
        return self._com.FirstVisibleRow

    @first_visible_row.setter
    def first_visible_row(self, value: int) -> None:
        self._com.FirstVisibleRow = value

    @property
    def column_order(self):
        """Return the column order collection."""
        return self._com.ColumnOrder

    @property
    def toolbar_button_count(self) -> int:
        return self._com.ToolbarButtonCount

    # --- Cell access ---

    def get_cell_value(self, row: int, column: str) -> str:
        """Read the value of a cell."""
        return self._com.GetCellValue(row, column)

    def set_cell_value(self, row: int, column: str, value: str) -> None:
        """Write a value to a cell (calls ModifyCell on COM)."""
        self._com.ModifyCell(row, column, value)

    def get_cell_changeable(self, row: int, column: str) -> bool:
        """Check if a cell is editable."""
        return bool(self._com.GetCellChangeable(row, column))

    def get_cell_type(self, row: int, column: str) -> str:
        """Return the type of a cell."""
        return self._com.GetCellType(row, column)

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
        return self._com.GetToolbarButtonId(pos)

    def get_toolbar_button_text(self, pos: int) -> str:
        return self._com.GetToolbarButtonText(pos)

    def get_toolbar_button_type(self, pos: int) -> int:
        return self._com.GetToolbarButtonType(pos)

    def get_toolbar_button_enabled(self, pos: int) -> bool:
        return bool(self._com.GetToolbarButtonEnabled(pos))

    def get_toolbar_button_tooltip(self, pos: int) -> str:
        return self._com.GetToolbarButtonTooltip(pos)
