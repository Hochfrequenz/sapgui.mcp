"""Transaction catalog loader - RUNTIME USE.

===========================================================================
This module is for RUNTIME use by MCP tools (search_transactions, etc.).
It reads the bundled transactions.json file - no SAP session required.

For DEVELOPMENT (building/updating the catalog), see scraper.py.
===========================================================================

Handles loading the transaction catalog from the static JSON file
bundled with the package.

Design Notes:
- This module is the PRIMARY loader for the catalog at runtime
- scraper.py has its own load_catalog_for_scraping() for the scraping workflow,
  which does NOT use caching (scraper modifies catalog in-place)
- We use lru_cache for singleton-like behavior in MCP tools
- The catalog is bundled with the package - it's always available at runtime

Error Handling Strategy:
- load_catalog(): Raises RuntimeError on parse errors (fail-fast for debugging)
- get_catalog(): Returns empty catalog on errors (graceful degradation for tools)
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from sapguimcp.catalog.models import TransactionCatalog

logger = logging.getLogger(__name__)

# Path to the bundled catalog file
CATALOG_PATH = Path(__file__).parent.parent / "data" / "transactions.json"


@lru_cache(maxsize=1)
def load_catalog(catalog_path: Path | None = None) -> TransactionCatalog:
    """Load the transaction catalog from JSON file (cached singleton).

    Results are cached by (catalog_path,) tuple, so:
    - load_catalog() and load_catalog(None) return same cached instance
    - load_catalog(Path("other.json")) caches separately

    Use reload_catalog() to clear cache and force a refresh.

    Args:
        catalog_path: Optional custom path to catalog file.
                     Defaults to bundled transactions.json.

    Returns:
        TransactionCatalog instance

    Raises:
        RuntimeError: If file exists but cannot be parsed (fail-fast)

    Note:
        Returns empty catalog (no error) if file doesn't exist,
        because catalog may not be populated yet during development.
    """
    path = catalog_path or CATALOG_PATH

    if not path.exists():
        logger.warning("Catalog not found", extra={"path": str(path)})
        return TransactionCatalog()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        catalog = TransactionCatalog.model_validate(data)
        logger.info(
            "Loaded catalog",
            extra={"transactions": len(catalog.transactions), "enriched": catalog.enriched_count},
        )
        return catalog
    except Exception as e:
        logger.exception("Loading catalog", extra={"path": str(path)})
        raise RuntimeError(f"Failed to load transaction catalog: {e}") from e


def reload_catalog(catalog_path: Path | None = None) -> TransactionCatalog:
    """Force reload the transaction catalog from disk.

    Clears the cache and loads fresh data.

    Args:
        catalog_path: Optional custom path to catalog file.

    Returns:
        Fresh TransactionCatalog instance
    """
    load_catalog.cache_clear()
    return load_catalog(catalog_path)


def get_catalog() -> TransactionCatalog:
    """Get the current transaction catalog (never raises).

    This is the recommended function for MCP tools because:
    1. It never raises exceptions (graceful degradation)
    2. MCP tools should return structured errors, not crash
    3. An empty catalog is valid during development

    For debugging/testing, use load_catalog() directly to see errors.

    Returns:
        TransactionCatalog instance (empty if file missing or corrupt)
    """
    try:
        return load_catalog()
    except RuntimeError:
        # Don't propagate parse errors - return empty catalog
        return TransactionCatalog()
