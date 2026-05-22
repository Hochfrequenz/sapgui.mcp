"""
Table catalog search tool for SAP.

This module provides an MCP tool to search for SAP tables by keyword,
description, or field name/description.
"""

import logging

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapguimcp.tables.loader import get_catalog
from sapguimcp.tables.search import search_tables as do_search

logger = logging.getLogger(__name__)

__all__ = ["register_table_tools"]


# =============================================================================
# Result Models
# =============================================================================


class TableFieldResult(BaseModel):
    """A field in the search result."""

    name: str = Field(description="Field name")
    description: str = Field(description="Field description")
    data_type: str = Field(description="ABAP data type")
    length: int = Field(description="Field length")
    decimals: int | None = Field(default=None, description="Decimal places")
    is_key: bool = Field(default=False, description="Part of primary key")


class TableSearchResultItem(BaseModel):
    """A single table from search results."""

    name: str = Field(description="Table name (e.g., 'MARA')")
    description: str = Field(description="Table description")
    delivery_class: str = Field(description="Delivery class")
    fields: list[TableFieldResult] = Field(description="Table fields")
    score: float = Field(description="Relevance score (0-100)")
    match_reason: str = Field(description="Why this table matched")


class TableSearchResponse(BaseModel):
    """Response from table search."""

    success: bool = Field(default=True)
    query: str = Field(description="The search query used")
    total_results: int = Field(description="Number of results found")
    total_in_catalog: int = Field(description="Total tables in catalog")
    results: list[TableSearchResultItem] = Field(description="Matching tables")
    hint: str | None = Field(default=None, description="Guidance when no results")


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_table_tools(mcp: FastMCP) -> None:
    """Register table catalog tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Search for SAP tables by name, description, or field. "
            "Use this when the user asks things like:\n"
            "- 'What table stores material master data?'\n"
            "- 'Which table has the MATNR field?'\n"
            "- 'Find tables related to purchase orders'\n\n"
            "Returns matching tables with relevance scores."
        ),
    )
    async def search_tables(
        query: str,
        include_fields: bool = True,
        limit: int = 10,
    ) -> TableSearchResponse:
        """
        Search for SAP tables by keyword or field.

        Args:
            query: Search query - can be a table name (e.g., 'MARA'),
                   partial name (e.g., 'MAR'), description keywords
                   (e.g., 'material master'), or field name (e.g., 'MATNR')
            include_fields: Also search within field names and descriptions
            limit: Maximum results to return (default 10, max 50)

        Returns:
            TableSearchResponse with matching tables
        """
        limit = min(max(1, limit), 50)

        catalog = get_catalog()
        search_results = do_search(catalog, query, include_fields=include_fields, limit=limit)

        results = [
            TableSearchResultItem(
                name=r.table.name,
                description=r.table.description,
                delivery_class=r.table.delivery_class,
                fields=[
                    TableFieldResult(
                        name=f.name,
                        description=f.description,
                        data_type=f.data_type,
                        length=f.length,
                        decimals=f.decimals,
                        is_key=f.is_key,
                    )
                    for f in r.table.fields
                ],
                score=r.score,
                match_reason=r.match_reason,
            )
            for r in search_results
        ]

        hint = None
        if not results:
            hint = f"No tables found for '{query}'. Try broader keywords or check spelling."

        return TableSearchResponse(
            success=True,
            query=query,
            total_results=len(results),
            total_in_catalog=len(catalog.tables),
            results=results,
            hint=hint,
        )
