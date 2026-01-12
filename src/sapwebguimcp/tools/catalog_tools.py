"""
Transaction catalog search tool for SAP.

This module provides MCP tools to search for SAP transactions by keyword,
description, or module area. It helps Claude find relevant transactions
for user tasks.

DESIGN DECISIONS:

1. WHY `success: bool` IN RESPONSES?
   MCP tools can return structured data OR raise exceptions. We chose
   structured responses with `success=True` always because:
   - Consistent response shape makes client parsing easier
   - "No results" is not an error, it's valid empty data
   - `catalog_available=False` indicates missing catalog (not a crash)

2. WHY NOT RAISE EXCEPTIONS?
   MCP clients handle exceptions differently. Returning structured
   CatalogSearchResponse ensures Claude always gets usable data with
   hints about what went wrong (empty catalog, no matches, etc.)

3. WHY `readOnlyHint=True`?
   These tools only read the bundled JSON catalog - they never modify
   it or make SAP calls. This hint lets clients skip confirmation dialogs.
"""

import logging

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from sapwebguimcp.catalog.loader import catalog_exists, get_catalog, get_catalog_stats
from sapwebguimcp.catalog.search import search_transactions as do_search

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
    traditional sense. Empty results, missing catalog, etc. are all valid
    states represented by other fields. Check `catalog_available` and
    `total_results` to understand the actual outcome.
    """

    # Always True - see class docstring for why
    success: bool = Field(default=True)
    query: str = Field(description="The search query used")
    total_results: int = Field(description="Number of results found (0 is valid)")
    results: list[TransactionSearchResult] = Field(description="Matching transactions")
    catalog_available: bool = Field(description="False if catalog file missing/empty")
    hint: str | None = Field(default=None, description="Guidance when no results")


class CatalogStatusResponse(BaseModel):
    """Response from catalog status check."""

    success: bool = Field(default=True)
    exists: bool = Field(description="Whether catalog file exists")
    total_transactions: int = Field(description="Total transactions in catalog")
    enriched_count: int = Field(description="Transactions with SE93 metadata")
    last_updated: str | None = Field(default=None, description="When catalog was last updated")
    source_system: str | None = Field(default=None, description="SAP system ID")


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

        # Check if catalog exists
        if not catalog_exists():
            return CatalogSearchResponse(
                success=True,
                query=query,
                total_results=0,
                results=[],
                catalog_available=False,
                hint=(
                    "Transaction catalog not found. Run the catalog scraper first: "
                    "scrape_catalog() or scrape_tstc() + enrich_with_se93()"
                ),
            )

        # Load catalog and search
        catalog = get_catalog()

        if not catalog.transactions:
            return CatalogSearchResponse(
                success=True,
                query=query,
                total_results=0,
                results=[],
                catalog_available=True,
                hint="Catalog is empty. Run the scraper to populate it.",
            )

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
            catalog_available=True,
            hint=hint,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            openWorldHint=False,
        ),
        description="Get status of the transaction catalog (total transactions, last updated, etc.)",
    )
    async def get_transaction_catalog_status() -> CatalogStatusResponse:
        """
        Get information about the transaction catalog.

        Returns statistics about the loaded catalog including:
        - Whether it exists
        - Total transaction count
        - How many are enriched with descriptions
        - When it was last updated
        """
        stats = get_catalog_stats()

        total = stats.get("total_transactions", 0)
        enriched = stats.get("enriched_count", 0)

        return CatalogStatusResponse(
            success=True,
            exists=bool(stats.get("exists")),
            total_transactions=int(total) if isinstance(total, (int, str)) else 0,
            enriched_count=int(enriched) if isinstance(enriched, (int, str)) else 0,
            last_updated=str(stats["last_updated"]) if stats.get("last_updated") else None,
            source_system=str(stats["source_system"]) if stats.get("source_system") else None,
        )
