"""Function module catalog loader - RUNTIME USE.

Loads the bundled function_modules.json file for search.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from sapguimcp.fmcatalog.models import FMCatalog, FunctionModuleEntry

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent / "data" / "function_modules.json"


@lru_cache(maxsize=1)
def load_catalog(catalog_path: Path | None = None) -> FMCatalog:
    """Load the FM catalog from JSON file (cached singleton).

    Note: Uses maxsize=1 cache. The catalog_path parameter exists for testing,
    but production code should use get_catalog() which always uses the default path.
    Calling with different paths will evict the previous cached result.
    """
    path = catalog_path or CATALOG_PATH

    if not path.exists():
        logger.warning("Catalog not found", extra={"path": str(path)})
        return FMCatalog()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Convert to dict indexed by uppercase name
        fms = {}
        for fm_data in data.get("function_modules", []):
            entry = FunctionModuleEntry.from_dict(fm_data)
            fms[entry.name.upper()] = entry

        catalog = FMCatalog(
            function_modules=fms,
            source_system=data.get("source_system"),
            language=data.get("language"),
            total_count=len(fms),
        )
        logger.info("Loaded catalog", extra={"function_modules": len(fms)})
        return catalog
    except Exception as e:
        logger.exception("Loading catalog", extra={"path": str(path)})
        raise RuntimeError(f"Failed to load FM catalog: {e}") from e


def reload_catalog(catalog_path: Path | None = None) -> FMCatalog:
    """Force reload the FM catalog from disk."""
    load_catalog.cache_clear()
    return load_catalog(catalog_path)


def get_catalog() -> FMCatalog:
    """Get the current FM catalog (never raises)."""
    try:
        return load_catalog()
    except RuntimeError:
        return FMCatalog()
