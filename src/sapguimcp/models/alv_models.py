"""Pydantic models for SAP ALV grid support (ALV = ABAP List Viewer)."""

from pydantic import Field

from sapguimcp.models.base import ToolResult


class TableCellClickResult(ToolResult):
    """Result from sap_click_table_cell tool."""

    row: int = Field(ge=1, description="Row that was clicked (1-indexed)")
    column: int | str = Field(description="Column that was clicked (index or header)")
    selector_used: str = Field(description="CSS selector that was used for the click")
    page_title: str = Field(default="", description="Page title after click")
    was_hotspot: bool = Field(default=False, description="Whether cell was a navigation hotspot")
