"""Data models for the table catalog - SHARED.

===========================================================================
These models are used by BOTH runtime (MCP tools) and development (scraper).
They define the data structure for tables.json.
===========================================================================
"""

from pydantic import BaseModel, ConfigDict, Field


class TableField(BaseModel):
    """Single field within a table."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Field name (e.g., 'MATNR')")
    description: str = Field(description="Field description (e.g., 'Materialnummer')")
    data_type: str = Field(description="ABAP data type (e.g., 'CHAR', 'NUMC', 'CURR')")
    length: int = Field(description="Field length")
    decimals: int | None = Field(default=None, description="Decimal places (numeric types only)")
    is_key: bool = Field(default=False, description="Part of primary key")


class TableInfo(BaseModel):
    """Metadata for a single SAP table."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Table name (e.g., 'MARA')")
    description: str = Field(description="Table description (e.g., 'Allgemeine Materialdaten')")
    delivery_class: str = Field(description="Delivery class (A=application, C=customizing, etc.)")
    fields: list[TableField] = Field(default_factory=list, description="All fields in table")


class TableCatalog(BaseModel):
    """Container for the full table catalog with metadata."""

    model_config = ConfigDict(extra="forbid")

    tables: dict[str, TableInfo] = Field(default_factory=dict, description="Tables keyed by name")
    version: str = Field(default="", description="Catalog version (e.g., '2026-01-12')")
    source_system: str = Field(default="", description="SAP system ID where data was collected")

    def get_table(self, name: str) -> TableInfo | None:
        """Look up a table by name (case-insensitive)."""
        return self.tables.get(name.upper())  # pylint: disable=no-member
