"""Transaction catalog module for SAP transaction discovery and search."""

from sapwebguimcp.catalog.loader import (
    catalog_exists,
    get_catalog,
    get_catalog_stats,
    load_catalog,
    reload_catalog,
)
from sapwebguimcp.catalog.models import TransactionCatalog, TransactionInfo, detect_area
from sapwebguimcp.catalog.scraper import (
    enrich_with_se93,
    load_tstc_data,
    save_catalog,
    scrape_catalog,
    scrape_tstc,
)
from sapwebguimcp.catalog.search import SearchResult, search_transactions

__all__ = [
    # Models
    "TransactionInfo",
    "TransactionCatalog",
    "detect_area",
    # Loader functions
    "load_catalog",
    "reload_catalog",
    "get_catalog",
    "catalog_exists",
    "get_catalog_stats",
    # Scraper functions
    "scrape_tstc",
    "scrape_catalog",
    "enrich_with_se93",
    "save_catalog",
    "load_tstc_data",
    # Search functions
    "search_transactions",
    "SearchResult",
]
