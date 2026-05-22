"""Transaction catalog module for SAP transaction discovery and search.

This module has two distinct purposes:

RUNTIME (Business Logic) - Used when the MCP server is running:
-----------------------------------------------------------------
- models: TransactionInfo, TransactionCatalog, detect_area
- loader: load_catalog(), get_catalog(), reload_catalog()
- search: search_transactions(), SearchResult

These are used by the `search_transactions` MCP tool to help Claude find
relevant SAP transactions. They read from the bundled transactions.json file.

DEVELOPMENT (Catalog Building) - Used to populate the catalog:
--------------------------------------------------------------
- scraper: scrape_tstc(), enrich_with_se93(), scrape_catalog(), save_catalog()

These are NOT exposed as MCP tools. They require an active SAP session and
are used by developers/maintainers to build or update the transaction catalog.

Typical development workflow:
1. scrape_tstc() - Query TSTC table for all transaction codes
2. enrich_with_se93() - Add descriptions from SE93 (incremental, resumable)
3. save_catalog() - Save to transactions.json

The resulting transactions.json is bundled with the package for runtime use.
"""

# =============================================================================
# RUNTIME EXPORTS - For MCP server business logic
# =============================================================================

from sapguimcp.catalog.loader import (
    get_catalog,
    load_catalog,
    reload_catalog,
)
from sapguimcp.catalog.models import TransactionCatalog, TransactionInfo, detect_area
from sapguimcp.catalog.scraper import (
    enrich_with_se93,
    load_catalog_for_scraping,
    load_tstc_data,
    save_catalog,
    scrape_catalog,
    scrape_tstc,
)
from sapguimcp.catalog.search import SearchResult, search_transactions

# =============================================================================
# DEVELOPMENT EXPORTS - For catalog building (not MCP tools)
# =============================================================================


__all__ = [
    # -------------------------------------------------------------------------
    # RUNTIME - Used by MCP tools during normal operation
    # -------------------------------------------------------------------------
    # Models
    "TransactionInfo",
    "TransactionCatalog",
    "detect_area",
    # Loader (reads bundled transactions.json)
    "load_catalog",
    "reload_catalog",
    "get_catalog",
    # Search (powers the search_transactions MCP tool)
    "search_transactions",
    "SearchResult",
    # -------------------------------------------------------------------------
    # DEVELOPMENT - Used to build/update the catalog (requires SAP session)
    # -------------------------------------------------------------------------
    "scrape_tstc",  # Query TSTC table for transaction codes
    "scrape_catalog",  # Full scrape: TSTC + SE93 enrichment
    "enrich_with_se93",  # Add descriptions from SE93 (incremental)
    "save_catalog",  # Save catalog to JSON file
    "load_tstc_data",  # Load raw TSTC data from JSON
    "load_catalog_for_scraping",  # Load catalog without caching (for scraper)
]
