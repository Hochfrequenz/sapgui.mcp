"""Table components — GuiTableControl, GuiTableRow, GuiTableColumn."""

from __future__ import annotations

from typing import Any

from sapsucker.components.base import GuiComponent, GuiVContainer

__all__ = ["GuiTableColumn", "GuiTableControl", "GuiTableRow"]


class GuiTableControl(GuiVContainer):
    """Wraps the COM GuiTableControl interface (TypeAsNumber 80).

    A classic dynpro table control (not ALV grid).
    """

    @property
    def row_count(self) -> int:
        """Total number of rows in the table."""
        return int(self._com.RowCount)

    @property
    def visible_row_count(self) -> int:
        """Number of currently visible rows."""
        return int(self._com.VisibleRowCount)

    @property
    def current_row(self) -> int:
        """Index of the current row."""
        return int(self._com.CurrentRow)

    @current_row.setter
    def current_row(self, value: int) -> None:
        self._com.CurrentRow = value

    @property
    def current_col(self) -> int:
        """Index of the current column."""
        return int(self._com.CurrentCol)

    @current_col.setter
    def current_col(self, value: int) -> None:
        self._com.CurrentCol = value

    @property
    def columns(self) -> Any:
        """Return the COM columns collection."""
        return self._com.Columns

    @property
    def rows(self) -> Any:
        """Return the COM rows collection."""
        return self._com.Rows

    def get_cell(self, row: int, col: int) -> Any:
        """Return the COM object for the cell at (row, col)."""
        return self._com.GetCell(row, col)

    def get_absolute_row(self, row: int) -> "GuiTableRow":
        """Return a row by absolute index (works with scrolled tables).

        Unlike indexing via rows[i], this accounts for the scroll position
        and returns the row at the given absolute position in the data.
        Raises an exception if the row is not currently visible.
        """
        return GuiTableRow(self._com.GetAbsoluteRow(row))


class GuiTableRow(GuiComponent):
    """Wraps a single row of a GuiTableControl."""

    @property
    def selected(self) -> bool:
        """Whether the row is selected."""
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0

    @property
    def selectable(self) -> bool:
        """Whether the row can be selected."""
        return bool(self._com.Selectable)


class GuiTableColumn(GuiComponent):
    """Wraps a single column of a GuiTableControl."""

    @property
    def title(self) -> str:
        """Column header title text."""
        return str(self._com.Title)

    @property
    def selected(self) -> bool:
        """Whether the column is selected."""
        return bool(self._com.Selected)

    @selected.setter
    def selected(self, value: bool) -> None:
        self._com.Selected = 1 if value else 0
