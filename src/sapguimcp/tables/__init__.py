"""Table catalog module for SAP table discovery and search.

This module has two distinct purposes:

RUNTIME (Business Logic) - Used when the MCP server is running:
-----------------------------------------------------------------
- models: TableField, TableInfo, TableCatalog
- loader: load_catalog(), get_catalog(), reload_catalog()
- search: search_tables(), TableSearchResult

These are used by the `search_tables` MCP tool to help Claude find
relevant SAP tables. They read from the bundled tables.json file.

DEVELOPMENT (Catalog Building) - Used to populate the catalog:
--------------------------------------------------------------
- scraper: scrape_table_catalog()

These are NOT exposed as MCP tools. They require an active SAP session and
are used by developers/maintainers to build or update the table catalog.
"""

# Runtime exports only - scraper is development-only
from sapguimcp.tables.loader import get_catalog, load_catalog, reload_catalog
from sapguimcp.tables.models import TableCatalog, TableField, TableInfo
from sapguimcp.tables.search import TableSearchResult, search_tables

__all__ = [
    # Models
    "TableField",
    "TableInfo",
    "TableCatalog",
    # Loader
    "get_catalog",
    "load_catalog",
    "reload_catalog",
    # Search
    "search_tables",
    "TableSearchResult",
]
