"""Pydantic models for SAP ALV grid support (ALV = ABAP List Viewer)."""

from typing import Literal

from pydantic import Field

from sapguimcp.models.base import ToolResult


class TableCellClickResult(ToolResult):
    """Result from sap_click_table_cell tool."""

    row: int = Field(ge=1, description="Row that was clicked (1-indexed)")
    column: int | str = Field(description="Column that was clicked (index or header)")
    selector_used: str = Field(description="CSS selector that was used for the click")
    page_title: str = Field(default="", description="Page title after click")
    was_hotspot: bool = Field(default=False, description="Whether cell was a navigation hotspot")


class ModifyCellResult(ToolResult):
    """Result from sap_modify_cell tool. Every field has a default, so ``failure(...)`` needs only the error."""

    row: int = Field(default=0, description="Row that was addressed (1-indexed, as in sap_read_table)")
    column: str = Field(
        default="", description="Column the column argument resolved to, as sap_read_table's headers name it"
    )
    table_type: Literal["GuiGridView", "GuiTableControl"] | None = Field(
        default=None, description="Kind of table written: an ALV grid or a classic table control"
    )
    scrolled: bool = Field(default=False, description="True if the row had to be scrolled into view (or loaded)")
    previous_value: str = Field(default="", description="Cell value before the write")
    value: str = Field(default="", description="Cell value read back after the write (not an echo of the input)")
    written: bool = Field(
        default=False,
        description="True once the write was sent; a failure with written=True means the cell DID change",
    )
    note: str = Field(default="", description="What to do next, or a popup / status message the write caused")
