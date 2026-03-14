"""Table components — GuiTableControl, GuiTableRow, GuiTableColumn."""

from __future__ import annotations

from sapwebguimcp.sapgui.components.base import GuiComponent, GuiVContainer


class GuiTableControl(GuiVContainer):
    """Wraps the COM GuiTableControl interface (TypeAsNumber 80).

    A classic dynpro table control (not ALV grid).
    """

    @property
    def row_count(self) -> int:
        return self._com.RowCount

    @property
    def visible_row_count(self) -> int:
        return self._com.VisibleRowCount

    @property
    def current_row(self) -> int:
        return self._com.CurrentRow

    @current_row.setter
    def current_row(self, value: int) -> None:
        self._com.CurrentRow = value

    @property
    def current_col(self) -> int:
        return self._com.CurrentCol

    @current_col.setter
    def current_col(self, value: int) -> None:
        self._com.CurrentCol = value

    @property
    def columns(self):
        """Return the COM columns collection."""
        return self._com.Columns

    @property
    def rows(self):
        """Return the COM rows collection."""
        return self._com.Rows

    def get_cell(self, row: int, col: int):
        """Return the COM object for the cell at (row, col)."""
        return self._com.GetCell(row, col)


class GuiTableRow(GuiComponent):
    """Wraps a single row of a GuiTableControl."""

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def selectable(self) -> bool:
        return bool(self._com.Selectable)


class GuiTableColumn(GuiComponent):
    """Wraps a single column of a GuiTableControl."""

    @property
    def title(self) -> str:
        return self._com.Title

    @property
    def selected(self) -> bool:
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0
