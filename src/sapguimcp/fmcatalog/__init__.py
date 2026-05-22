"""Function module catalog for SAP FM discovery and search.

RUNTIME USE - Used when the MCP server is running:
- loader: load_catalog(), get_catalog()
- search: search_function_modules(), FMSearchResult
"""

from sapguimcp.fmcatalog.loader import get_catalog, load_catalog, reload_catalog
from sapguimcp.fmcatalog.search import FMSearchResult, search_function_modules

__all__ = [
    "load_catalog",
    "reload_catalog",
    "get_catalog",
    "search_function_modules",
    "FMSearchResult",
]
