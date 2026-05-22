"""Class catalog for SAP class discovery and search.

RUNTIME USE - Used when the MCP server is running:
- loader: load_catalog(), get_catalog()
- search: search_classes(), ClassSearchResult
"""

from sapguimcp.classcatalog.loader import get_catalog, load_catalog, reload_catalog
from sapguimcp.classcatalog.search import ClassSearchResult, search_classes

__all__ = [
    "load_catalog",
    "reload_catalog",
    "get_catalog",
    "search_classes",
    "ClassSearchResult",
]
