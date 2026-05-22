"""Class catalog loader - RUNTIME USE.

Loads the bundled classes.json file for search.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from sapguimcp.classcatalog.models import ClassCatalog, ClassEntry

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent / "data" / "classes.json"


@lru_cache(maxsize=1)
def load_catalog(catalog_path: Path | None = None) -> ClassCatalog:
    """Load the class catalog from JSON file (cached singleton).

    Note: Uses maxsize=1 cache. The catalog_path parameter exists for testing,
    but production code should use get_catalog() which always uses the default path.
    Calling with different paths will evict the previous cached result.
    """
    path = catalog_path or CATALOG_PATH

    if not path.exists():
        logger.warning("Catalog not found", extra={"path": str(path)})
        return ClassCatalog()

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        # Convert to dict indexed by uppercase name
        classes = {}
        for cls_data in data.get("classes", []):
            entry = ClassEntry.from_dict(cls_data)
            classes[entry.name.upper()] = entry

        catalog = ClassCatalog(
            classes=classes,
            source_system=data.get("source_system"),
            language=data.get("language"),
            total_count=len(classes),
        )
        logger.info("Loaded catalog", extra={"classes": len(classes)})
        return catalog
    except Exception as e:
        logger.exception("Loading catalog", extra={"path": str(path)})
        raise RuntimeError(f"Failed to load class catalog: {e}") from e


def reload_catalog(catalog_path: Path | None = None) -> ClassCatalog:
    """Force reload the class catalog from disk."""
    load_catalog.cache_clear()
    return load_catalog(catalog_path)


def get_catalog() -> ClassCatalog:
    """Get the current class catalog (never raises)."""
    try:
        return load_catalog()
    except RuntimeError:
        return ClassCatalog()
