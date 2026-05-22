"""
Pydantic models for SAP ALV grid support.

ALV (ABAP List Viewer) grids are SAP's standard table display components.
They have a specific DOM structure with clickable hotspot cells that need
special handling for browser automation.
"""

from pydantic import BaseModel, Field

from sapguimcp.models.base import ToolResult


class AlvCellInfo(BaseModel):
    """Metadata for a single ALV grid cell."""

    selector: str = Field(description="CSS selector ready for browser_click (properly escaped)")
    clickable: bool = Field(default=False, description="Whether this cell can be clicked")
    hotspot: bool = Field(default=False, description="Whether this is a navigation hotspot")


class AlvMetadata(BaseModel):
    """Grid-level metadata for an ALV table."""

    table_id: str = Field(description="SAP table element ID (e.g., 'C120')")
    selection_mode: str = Field(default="NONE", description="Selection mode: MULTI, SINGLE, or NONE")
    hotspot_columns: list[int] = Field(default_factory=list, description="Indices of columns with hotspots")
    column_map: dict[str, int] = Field(default_factory=dict, description="Column header to index mapping")


class TableCellClickResult(ToolResult):
    """Result from sap_click_table_cell tool."""

    row: int = Field(ge=1, description="Row that was clicked (1-indexed)")
    column: int | str = Field(description="Column that was clicked (index or header)")
    selector_used: str = Field(description="CSS selector that was used for the click")
    page_title: str = Field(default="", description="Page title after click")
    was_hotspot: bool = Field(default=False, description="Whether cell was a navigation hotspot")
