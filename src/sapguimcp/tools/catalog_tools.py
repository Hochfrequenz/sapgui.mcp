"""
Transaction catalog search tool for SAP.

This module provides an MCP tool to search for SAP transactions by keyword,
description, or module area. It helps Claude find relevant transactions
for user tasks.

DESIGN DECISIONS:

1. WHY `success: bool` IN RESPONSES?
   MCP tools can return structured data OR raise exceptions. We chose
   structured responses with `success=True` always because:
   - Consistent response shape makes client parsing easier
   - "No results" is not an error, it's valid empty data

2. WHY NOT RAISE EXCEPTIONS?
   MCP clients handle exceptions differently. Returning structured
   CatalogSearchResponse ensures Claude always gets usable data with
   hints about what went wrong (no matches, etc.)

3. WHY `readOnlyHint=True`?
   This tool only reads the bundled JSON catalog - it never modifies
   it or makes SAP calls. This hint lets clients skip confirmation dialogs.

4. WHY NO `catalog_exists` CHECK?
   The catalog is bundled with the package and always available at runtime.
   There's no scenario where it wouldn't exist in production.
"""

import logging

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapguimcp.catalog.loader import get_catalog
from sapguimcp.catalog.search import search_transactions as do_search

logger = logging.getLogger(__name__)

__all__ = ["register_catalog_tools"]


# =============================================================================
# Result Models
# =============================================================================


class TransactionSearchResult(BaseModel):
    """A single transaction from search results."""

    tcode: str = Field(description="Transaction code (e.g., 'VA01')")
    description: str = Field(description="Transaction description")
    area: str | None = Field(default=None, description="SAP module area (e.g., 'SD-Sales')")
    program: str = Field(default="", description="Program name")
    transaction_type: str = Field(default="unknown", description="Type: 'dialog' or 'report'")
    score: float = Field(description="Relevance score (0-100)")
    match_type: str = Field(description="How the match was found")


class CatalogSearchResponse(BaseModel):
    """Response from transaction search.

    NOTE: `success` is always True because this tool never "fails" in the
    traditional sense. Empty results are valid data, not errors.
    """

    success: bool = Field(default=True)
    query: str = Field(description="The search query used")
    total_results: int = Field(description="Number of results found (0 is valid)")
    results: list[TransactionSearchResult] = Field(description="Matching transactions")
    hint: str | None = Field(default=None, description="Guidance when no results")


# =============================================================================
# MCP Tool Registration
# =============================================================================


def register_catalog_tools(mcp: FastMCP) -> None:
    """Register transaction catalog tools with the MCP server."""

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description=(
            "Search for SAP transactions by description or transaction code. "
            "Use this when the user asks things like:\n"
            "- 'How do I create a sales order?'\n"
            "- 'What transaction displays customer master?'\n"
            "- 'Show me material management transactions'\n"
            "- 'What is VA01?'\n\n"
            "Returns matching transactions with relevance scores."
        ),
    )
    async def search_transactions(
        query: str,
        area: str | None = None,
        limit: int = 10,
    ) -> CatalogSearchResponse:
        """
        Search for SAP transactions by keyword or code.

        Args:
            query: Search query - can be a transaction code (e.g., 'VA01'),
                   partial code (e.g., 'VA'), or description keywords
                   (e.g., 'create sales order', 'customer master')
            area: Optional filter by SAP module area. Common values:
                  - 'SD' = Sales & Distribution
                  - 'MM' = Materials Management
                  - 'FI' = Financial Accounting
                  - 'CO' = Controlling
                  - 'PP' = Production Planning
                  - 'HR' = Human Resources
                  - 'BC' = Basis/Technical
            limit: Maximum results to return (default 10, max 50)

        Returns:
            CatalogSearchResponse with matching transactions
        """
        # Validate limit
        limit = min(max(1, limit), 50)

        # Load catalog and search
        catalog = get_catalog()

        # Perform search
        search_results = do_search(catalog, query, area=area, limit=limit)

        # Convert to response format
        results = [
            TransactionSearchResult(
                tcode=r.transaction.tcode,
                description=r.transaction.description,
                area=r.transaction.area,
                program=r.transaction.program,
                transaction_type=r.transaction.transaction_type,
                score=r.score,
                match_type=r.match_type,
            )
            for r in search_results
        ]

        hint = None
        if not results:
            hint = f"No transactions found for '{query}'. Try broader keywords or check spelling."

        return CatalogSearchResponse(
            success=True,
            query=query,
            total_results=len(results),
            results=results,
            hint=hint,
        )
