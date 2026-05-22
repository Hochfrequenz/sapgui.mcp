"""Table catalog loader - RUNTIME USE.

===========================================================================
This module is for RUNTIME use by MCP tools (search_tables, etc.).
It reads the bundled tables.json file - no SAP session required.

For DEVELOPMENT (building/updating the catalog), see scraper.py.
===========================================================================
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from sapguimcp.tables.models import TableCatalog

logger = logging.getLogger(__name__)

# Path to the bundled catalog file
CATALOG_PATH = Path(__file__).parent.parent / "data" / "tables.json"


@lru_cache(maxsize=1)
def load_catalog(catalog_path: Path | None = None) -> TableCatalog:
    """Load the table catalog from JSON file (cached singleton).

    Args:
        catalog_path: Optional custom path to catalog file.
                     Defaults to bundled tables.json.

    Returns:
        TableCatalog instance

    Raises:
        RuntimeError: If file exists but cannot be parsed
    """
    path = catalog_path or CATALOG_PATH

    if not path.exists():
        logger.warning("Catalog not found", extra={"path": str(path)})
        return TableCatalog()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        catalog = TableCatalog.model_validate(data)
        logger.info("Loaded catalog", extra={"tables": len(catalog.tables)})
        return catalog
    except Exception as e:
        logger.exception("Loading catalog", extra={"path": str(path)})
        raise RuntimeError(f"Failed to load table catalog: {e}") from e


def reload_catalog(catalog_path: Path | None = None) -> TableCatalog:
    """Force reload the table catalog from disk."""
    load_catalog.cache_clear()
    return load_catalog(catalog_path)


def get_catalog() -> TableCatalog:
    """Get the current table catalog (never raises).

    This is the recommended function for MCP tools because:
    1. It never raises exceptions (graceful degradation)
    2. MCP tools should return structured errors, not crash
    """
    try:
        return load_catalog()
    except RuntimeError:
        return TableCatalog()
