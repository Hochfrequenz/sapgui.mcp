"""Class catalog loader - RUNTIME USE.

Loads the bundled classes.json file for search.
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from sapwebguimcp.classcatalog.models import ClassCatalog, ClassEntry

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent.parent / "data" / "classes.json"


@lru_cache(maxsize=1)
def load_catalog(catalog_path: Path | None = None) -> ClassCatalog:
    """Load the class catalog from JSON file (cached singleton)."""
    path = catalog_path or CATALOG_PATH

    if not path.exists():
        logger.warning("Class catalog not found at %s", path)
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
        logger.info("Loaded class catalog: %d classes", len(classes))
        return catalog
    except Exception as e:
        logger.exception("Failed to load class catalog from %s", path)
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
