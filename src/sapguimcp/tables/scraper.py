"""Table catalog scraper - DEVELOPMENT USE ONLY.

===========================================================================
WARNING: This module is for DEVELOPMENT/MAINTENANCE of the catalog.
It is NOT exposed as an MCP tool. It requires an active SAP session.

For RUNTIME use (MCP tools), see:
- loader.py: Load the bundled catalog
- search.py: Search the catalog
===========================================================================

Usage (from Claude Code with SAP session active):
    from sapguimcp.tables.scraper import scrape_table_catalog
    result = await scrape_table_catalog(
        prefixes=["MARA", "VBAK", "EKKO"],
        batch_size=10,
        output_file="data/tables.json"
    )
"""

# pylint: disable=import-outside-toplevel,too-many-locals

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sapguimcp.tables.models import TableCatalog, TableField, TableInfo

logger = logging.getLogger(__name__)


def load_catalog_for_scraping(catalog_file: str | Path) -> TableCatalog:
    """Load catalog from JSON file WITHOUT caching (for scraper use only)."""
    catalog_path = Path(catalog_file)
    if not catalog_path.exists():
        return TableCatalog()

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    return TableCatalog.model_validate(data)


def save_catalog(catalog: TableCatalog, catalog_file: str | Path) -> None:
    """Save catalog to JSON file."""
    catalog_path = Path(catalog_file)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    with open(catalog_path, "w", encoding="utf-8") as f:
        f.write(catalog.model_dump_json(indent=2))


async def get_table_list_from_dd02l(
    prefixes: list[str],
    max_hits: int = 500,
) -> list[str]:
    """Query DD02L for table names matching prefixes.

    Uses the existing sap_se16_query internal function.

    Args:
        prefixes: Table name prefixes to search (e.g., ["MARA", "VBAK"])
        max_hits: Maximum tables per prefix

    Returns:
        List of table names
    """
    from sapguimcp.backend.manager import get_backend
    from sapguimcp.tools.se16_tools import _execute_se16_query

    backend = await get_backend()
    all_tables: set[str] = set()

    for prefix in prefixes:
        logger.info("Querying DD02L", extra={"prefix": f"{prefix}*"})
        result = await _execute_se16_query(
            backend,
            table="DD02L",
            filters={"TABNAME": f"{prefix}*"},
            max_hits=max_hits,
        )

        if result.success and hasattr(result, "rows"):
            for row in result.rows:
                tabname = row.data.get("TABNAME") or row.data.get("Tabellenname", "")
                if tabname:
                    all_tables.add(str(tabname).strip().upper())

    return sorted(all_tables)


async def _lookup_table_se11(table_name: str) -> TableInfo | str:
    """Look up a single table in SE11 and return TableInfo or error string."""
    from sapguimcp.backend.manager import get_backend
    from sapguimcp.models.se11_models import SE11Entry
    from sapguimcp.tools.se11_tools import _lookup_object_on_initial_screen

    backend = await get_backend()

    # Navigate to SE11 with clean state
    await backend.enter_transaction("/n")
    await backend.wait_for_ready()
    tx_result = await backend.enter_transaction("SE11")
    if not tx_result.success:
        return f"Failed to navigate to SE11: {tx_result.error}"
    await backend.wait_for_ready()

    result = await _lookup_object_on_initial_screen(backend, table_name, "table")

    if isinstance(result, SE11Entry):
        fields = [
            TableField(
                name=f.name,
                description=f.description or "",
                data_type=f.datatype or "CHAR",  # SE11Field uses 'datatype' not 'data_type'
                length=f.length or 0,
                decimals=f.decimals if f.decimals else None,
                is_key=f.is_key or False,
            )
            for f in result.fields
        ]
        return TableInfo(
            name=table_name,
            description=result.description or "",
            delivery_class="",  # SE11Entry doesn't have delivery_class, leave empty
            fields=fields,
        )

    # SE11Error
    return result.error or "Unknown error"


async def scrape_table_catalog(
    prefixes: list[str] | None = None,
    batch_size: int = 10,
    output_file: str | Path = Path("tables.json"),
    max_tables: int | None = None,
) -> dict[str, Any]:
    """Scrape table metadata from SAP.

    Uses the existing SE11 internal functions.

    1. Query DD02L for table names matching prefixes
    2. Enrich each table via SE11 lookup in batches
    3. Save after each batch (resume-friendly)

    Args:
        prefixes: Table name prefixes (defaults to common tables)
        batch_size: Tables to process before saving
        output_file: Path to save catalog JSON
        max_tables: Maximum tables to scrape (for testing)

    Returns:
        Dict with scraping statistics
    """
    # Default prefixes targeting ~1500-2500 tables
    if prefixes is None:
        prefixes = [
            "MARA",
            "MARC",
            "MARD",
            "MAKT",  # Material master
            "VBAK",
            "VBAP",
            "VBEP",  # Sales
            "EKKO",
            "EKPO",  # Purchasing
            "BKPF",
            "BSEG",  # Accounting
            "KNA1",
            "KNB1",  # Customers
            "LFA1",
            "LFB1",  # Vendors
            "T0",  # Config tables (T001, T002, etc.)
            "EUIT",  # UI tables
        ]

    output_path = Path(output_file)

    # Load existing catalog for resume
    catalog = load_catalog_for_scraping(output_path)
    existing_tables = set(catalog.tables.keys())

    # Get table list from DD02L
    logger.info("Fetching table list from DD02L")
    table_names = await get_table_list_from_dd02l(prefixes)
    logger.info("Found tables matching prefixes", extra={"count": len(table_names)})

    # Filter out already scraped
    to_scrape = [t for t in table_names if t not in existing_tables]
    if max_tables:
        to_scrape = to_scrape[:max_tables]

    logger.info("Tables to scrape", extra={"to_scrape": len(to_scrape), "existing": len(existing_tables)})

    stats = {"processed": 0, "success": 0, "failed": 0}
    errors: list[dict[str, str]] = []

    # Process in batches
    for batch_start in range(0, len(to_scrape), batch_size):
        batch = to_scrape[batch_start : batch_start + batch_size]

        for table_name in batch:
            stats["processed"] += 1
            logger.info(
                "SE11 lookup", extra={"processed": stats["processed"], "total": len(to_scrape), "table": table_name}
            )

            try:
                result = await _lookup_table_se11(table_name)

                if isinstance(result, TableInfo):
                    catalog.tables[table_name] = result
                    stats["success"] += 1
                else:
                    stats["failed"] += 1
                    errors.append({"table": table_name, "error": result})

            except Exception as e:  # pylint: disable=broad-exception-caught
                stats["failed"] += 1
                errors.append({"table": table_name, "error": str(e)})
                logger.exception("SE11 lookup failed", extra={"table": table_name})

        # Save after each batch
        catalog.version = datetime.now(UTC).strftime("%Y-%m-%d")
        save_catalog(catalog, output_path)
        logger.info("Saved catalog", extra={"total_tables": len(catalog.tables), "new": stats["success"]})

    return {
        "success": True,
        "processed": stats["processed"],
        "success_count": stats["success"],
        "failed": stats["failed"],
        "errors": errors[:10],
        "total_in_catalog": len(catalog.tables),
        "output_file": str(output_path),
    }
