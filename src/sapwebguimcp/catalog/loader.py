"""Transaction catalog loader.

Handles loading the transaction catalog from the static JSON file
bundled with the package.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from sapwebguimcp.catalog.models import TransactionCatalog

logger = logging.getLogger(__name__)

# Path to the bundled catalog file
CATALOG_PATH = Path(__file__).parent.parent / "data" / "transactions.json"


@lru_cache(maxsize=1)
def load_catalog(catalog_path: Path | None = None) -> TransactionCatalog:
    """Load the transaction catalog from JSON file.

    Results are cached, so subsequent calls return the same instance.
    Use reload_catalog() to force a refresh.

    Args:
        catalog_path: Optional custom path to catalog file.
                     Defaults to bundled transactions.json.

    Returns:
        TransactionCatalog instance (may be empty if file doesn't exist)
    """
    path = catalog_path or CATALOG_PATH

    if not path.exists():
        logger.warning("Transaction catalog not found at %s", path)
        return TransactionCatalog()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        catalog = TransactionCatalog.model_validate(data)
        logger.info(
            "Loaded transaction catalog: %d transactions (%d enriched)",
            len(catalog.transactions),
            catalog.enriched_count,
        )
        return catalog
    except Exception as e:
        logger.exception("Failed to load transaction catalog from %s", path)
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
    """Get the current transaction catalog.

    Convenience function that loads the default catalog.
    Returns empty catalog if file doesn't exist.

    Returns:
        TransactionCatalog instance
    """
    try:
        return load_catalog()
    except RuntimeError:
        return TransactionCatalog()


def catalog_exists() -> bool:
    """Check if the transaction catalog file exists."""
    return CATALOG_PATH.exists()


def get_catalog_stats() -> dict[str, int | str | None]:
    """Get statistics about the current catalog.

    Returns:
        Dict with catalog statistics
    """
    if not catalog_exists():
        return {
            "exists": False,
            "path": str(CATALOG_PATH),
            "total_transactions": 0,
            "enriched_count": 0,
        }

    catalog = get_catalog()
    return {
        "exists": True,
        "path": str(CATALOG_PATH),
        "total_transactions": len(catalog.transactions),
        "enriched_count": catalog.enriched_count,
        "last_updated": catalog.last_updated.isoformat() if catalog.last_updated else None,
        "source_system": catalog.source_system,
        "language": catalog.language,
    }
