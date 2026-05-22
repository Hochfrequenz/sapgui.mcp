"""Transaction catalog scraper - DEVELOPMENT USE ONLY.

===========================================================================
WARNING: This module is for DEVELOPMENT/MAINTENANCE of the catalog.
It is NOT exposed as an MCP tool. It requires an active SAP session.

For RUNTIME use (MCP tools), see:
- loader.py: Load the bundled catalog
- search.py: Search the catalog
===========================================================================

This module provides functions to scrape transaction codes from SAP
and build a transaction catalog. It uses:

1. SE16 (sap_se16_query) to query the TSTC table for all transaction codes
2. SE93 (sap_se93_lookup) to enrich each transaction with description and metadata

DESIGN DECISIONS:

1. WHY DUPLICATE load_catalog()?
   This module has its own load_catalog() that does NOT use caching,
   unlike loader.load_catalog(). This is intentional because:
   - Scraper modifies catalog in-place during SE93 enrichment
   - Cached catalog would not reflect incremental saves
   - Scraper needs fresh reads after each batch save

2. WHY dict[str, Any] RETURN TYPES?
   Scraper functions return dicts instead of Pydantic models because:
   - They're called from Claude Code, not MCP tools
   - JSON-like dicts are easier to inspect in Claude's output
   - Adding Pydantic models here would require importing from tools layer
   Consider refactoring if this becomes an MCP tool in the future.

3. WHY BROAD EXCEPTION CATCHING?
   SE93 enrichment catches all exceptions (line ~310) because:
   - SE93 can fail for many reasons (tcode deleted, no auth, timeout)
   - We want to continue processing other tcodes, not abort
   - Errors are logged and returned in the result dict

Usage (from Claude Code with SAP session active):
    1. First, scrape TSTC to get all transaction codes:
       result = await scrape_tstc(output_file="data/tstc_raw.json")

    2. Then, enrich with SE93 data (can be done incrementally):
       result = await enrich_with_se93(
           catalog_file="data/transactions.json",
           tstc_file="data/tstc_raw.json",
           batch_size=50,
           prefix_filter=["VA", "ME", "MM"]
       )
"""

# pylint: disable=import-outside-toplevel,too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,too-many-branches,too-many-statements

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from fastmcp import Context

from sapguimcp.catalog.models import TransactionCatalog, TransactionInfo
from sapguimcp.models.se16_models import SE16Result
from sapguimcp.models.se93_models import SE93Entry

logger = logging.getLogger(__name__)


async def scrape_tstc(
    output_file: str | Path | None = None,
    max_hits: int = 10000,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Query TSTC table to get all transaction codes.

    This is Step 1.1 of the scraping process. It queries the TSTC table
    using SE16N and saves the raw results.

    Args:
        output_file: Path to save raw TSTC data (JSON)
        max_hits: Maximum rows to retrieve (default 10000)
        ctx: MCP context for progress reporting (optional)

    Returns:
        Dict with keys:
        - success: bool
        - total_transactions: int
        - output_file: str (if provided)
        - transactions: list of dicts with TCODE, PGMNA, DESSION
    """
    # Import here to avoid circular imports
    from sapguimcp.backend.manager import get_backend
    from sapguimcp.tools.se16_tools import _execute_se16_query

    backend = await get_backend()

    # Query TSTC table
    result = await _execute_se16_query(
        backend,
        table="TSTC",
        filters=None,
        max_hits=max_hits,
        ctx=ctx,
    )

    if not result.success:
        return {
            "success": False,
            "error": result.error or "Failed to query TSTC table",
        }

    # Check if it's SE16Result (inline) or SE16FileSummary
    if not isinstance(result, SE16Result):
        return {
            "success": False,
            "error": "Expected inline SE16Result, got file summary",
        }

    # Extract transaction data (handle both technical and German column names)
    transactions = []
    for row in result.rows:
        # Handle both TCODE (technical) and Transaktionscode (German display name)
        tcode = row.data.get("TCODE") or row.data.get("Transaktionscode", "")
        if tcode:  # Skip empty transaction codes
            program = row.data.get("PGMNA") or row.data.get("Programm", "")
            screen = row.data.get("DESSION") or row.data.get("Dynpro")
            transactions.append(
                {
                    "TCODE": str(tcode).strip(),
                    "PGMNA": str(program).strip() if program else "",
                    "DESSION": screen,
                }
            )

    output = {
        "success": True,
        "total_transactions": len(transactions),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "transactions": transactions,
    }

    # Save to file if requested
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        output["output_file"] = str(output_path)

    return output


def load_tstc_data(tstc_file: str | Path) -> list[dict[str, Any]]:
    """Load raw TSTC data from a JSON file.

    Args:
        tstc_file: Path to the TSTC JSON file

    Returns:
        List of transaction dicts with TCODE, PGMNA, DESSION keys
    """
    with open(tstc_file, encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    transactions: list[dict[str, Any]] = data.get("transactions", [])
    return transactions


def load_catalog_for_scraping(catalog_file: str | Path) -> TransactionCatalog:
    """Load catalog from JSON file WITHOUT caching (for scraper use only).

    IMPORTANT: This is different from loader.load_catalog() which uses
    lru_cache. We need uncached reads here because:
    - Scraper modifies and saves catalog after each batch
    - We need to read fresh data, not stale cached version

    Args:
        catalog_file: Path to the catalog JSON file

    Returns:
        TransactionCatalog (empty if file doesn't exist)
    """
    catalog_path = Path(catalog_file)
    if not catalog_path.exists():
        return TransactionCatalog()

    with open(catalog_path, encoding="utf-8") as f:
        data = json.load(f)

    return TransactionCatalog.model_validate(data)


def save_catalog(catalog: TransactionCatalog, catalog_file: str | Path) -> None:
    """Save catalog to JSON file.

    Args:
        catalog: The catalog to save
        catalog_file: Path to save to
    """
    catalog_path = Path(catalog_file)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)

    with open(catalog_path, "w", encoding="utf-8") as f:
        f.write(catalog.model_dump_json(indent=2))


def apply_se93_enrichment(txn: TransactionInfo, se93_entry: SE93Entry) -> TransactionInfo:
    """Apply SE93 data to a TransactionInfo.

    Args:
        txn: The transaction to enrich
        se93_entry: SE93 data to apply

    Returns:
        Updated TransactionInfo
    """
    return txn.model_copy(
        update={
            "description": se93_entry.description,
            "program": se93_entry.program,
            "screen_number": se93_entry.screen_number,
            "transaction_type": se93_entry.transaction_type,
            "package": se93_entry.package,
            "authorization_object": se93_entry.authorization_object,
            "gui_html": se93_entry.gui_html,
            "gui_java": se93_entry.gui_java,
            "gui_windows": se93_entry.gui_windows,
            "enriched": True,
            "retrieved_at": se93_entry.retrieved_at,
        }
    )


async def enrich_with_se93(
    catalog_file: str | Path,
    tstc_file: str | Path | None = None,
    tstc_data: list[dict[str, Any]] | None = None,
    batch_size: int = 50,
    prefix_filter: list[str] | None = None,
    skip_enriched: bool = True,
    max_transactions: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Enrich transactions with SE93 metadata.

    This is Step 1.2 of the scraping process. For each transaction,
    it calls SE93 to get the full description and metadata.

    Progress is saved after each batch, so the process can be resumed
    if interrupted.

    Args:
        catalog_file: Path to save/load catalog JSON
        tstc_file: Path to TSTC raw data (if not providing tstc_data)
        tstc_data: Raw TSTC data (alternative to tstc_file)
        batch_size: How many transactions to process before saving
        prefix_filter: Only process transactions starting with these prefixes
        skip_enriched: Skip transactions already enriched
        max_transactions: Stop after processing this many transactions
        progress_callback: Optional callback(processed, total, current_tcode)

    Returns:
        Dict with enrichment statistics
    """
    # Import here to avoid circular imports
    from sapguimcp.backend.manager import get_backend
    from sapguimcp.tools.se93_tools import _lookup_tcode_on_initial_screen

    # Load TSTC data
    if tstc_data is None:
        if tstc_file is None:
            return {"success": False, "error": "Must provide either tstc_file or tstc_data"}
        tstc_data = load_tstc_data(tstc_file)

    # Load existing catalog (uncached - we modify and save after each batch)
    catalog = load_catalog_for_scraping(catalog_file)

    # Build index of existing transactions
    existing_tcodes = {t.tcode.upper(): i for i, t in enumerate(catalog.transactions)}

    # Add any new transactions from TSTC
    new_count = 0
    for tstc_row in tstc_data:
        tcode = str(tstc_row.get("TCODE", "")).strip().upper()
        if tcode and tcode not in existing_tcodes:
            txn = TransactionInfo.from_tstc_row(tstc_row)
            catalog.transactions.append(txn)
            existing_tcodes[tcode] = len(catalog.transactions) - 1
            new_count += 1

    catalog.tstc_count = len(catalog.transactions)

    # Filter transactions to process
    to_process = []
    for i, txn in enumerate(catalog.transactions):
        # Skip already enriched if requested
        if skip_enriched and txn.enriched:
            continue

        # Apply prefix filter
        if prefix_filter:
            matches_prefix = any(txn.tcode.upper().startswith(p.upper()) for p in prefix_filter)
            if not matches_prefix:
                continue

        to_process.append((i, txn))

    # Limit if requested
    if max_transactions and len(to_process) > max_transactions:
        to_process = to_process[:max_transactions]

    total = len(to_process)
    processed = 0
    enriched = 0
    failed = 0
    errors: list[dict[str, str]] = []

    # Get backend
    backend = await get_backend()

    # Process in batches
    for batch_start in range(0, total, batch_size):
        batch = to_process[batch_start : batch_start + batch_size]

        for idx, txn in batch:
            processed += 1

            if progress_callback:
                progress_callback(processed, total, txn.tcode)

            logger.info("SE93 enrichment", extra={"processed": processed, "total": total, "tcode": txn.tcode})

            # Navigate to Easy Access first, then SE93 — prevents state bleeding
            await backend.enter_transaction("/n")
            await backend.wait_for_ready()
            tx_result = await backend.enter_transaction("SE93")
            if not tx_result.success:
                failed += 1
                errors.append({"tcode": txn.tcode, "error": f"Failed to navigate to SE93: {tx_result.error}"})
                continue
            await backend.wait_for_ready()

            # Call SE93 lookup
            try:
                result = await _lookup_tcode_on_initial_screen(backend, txn.tcode)

                if isinstance(result, SE93Entry):
                    # Apply enrichment
                    updated = apply_se93_enrichment(txn, result)
                    catalog.transactions[idx] = updated
                    enriched += 1
                else:
                    # SE93Error
                    failed += 1
                    errors.append(
                        {
                            "tcode": txn.tcode,
                            "error": result.error,
                        }
                    )

            except Exception as e:  # pylint: disable=broad-exception-caught
                failed += 1
                errors.append(
                    {
                        "tcode": txn.tcode,
                        "error": str(e),
                    }
                )
                logger.exception("SE93 enrichment failed", extra={"tcode": txn.tcode})

        # Save after each batch
        catalog.enriched_count = sum(1 for t in catalog.transactions if t.enriched)
        catalog.last_updated = datetime.now(UTC)
        save_catalog(catalog, catalog_file)
        logger.info("Saved catalog", extra={"enriched": enriched, "failed": failed})

    return {
        "success": True,
        "new_from_tstc": new_count,
        "processed": processed,
        "enriched": enriched,
        "failed": failed,
        "errors": errors[:10],  # First 10 errors only
        "catalog_file": str(catalog_file),
        "total_in_catalog": len(catalog.transactions),
        "total_enriched": catalog.enriched_count,
    }


async def scrape_catalog(
    catalog_file: str | Path,
    max_tstc_hits: int = 10000,
    se93_batch_size: int = 50,
    prefix_filter: list[str] | None = None,
    max_se93_transactions: int | None = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Full scraping pipeline: TSTC query + SE93 enrichment.

    This combines Steps 1.1 and 1.2 into a single operation.
    For large catalogs, consider running scrape_tstc and enrich_with_se93
    separately to allow resuming.

    Args:
        catalog_file: Path to save catalog
        max_tstc_hits: Max transactions from TSTC
        se93_batch_size: Batch size for SE93 calls
        prefix_filter: Only enrich transactions with these prefixes
        max_se93_transactions: Max transactions to enrich with SE93
        ctx: MCP context for progress reporting (optional)

    Returns:
        Dict with full statistics
    """
    # Step 1: Query TSTC
    tstc_result = await scrape_tstc(max_hits=max_tstc_hits, ctx=ctx)

    if not tstc_result.get("success"):
        return tstc_result

    tstc_data = tstc_result.get("transactions", [])
    if not isinstance(tstc_data, list):
        tstc_data = []

    # Step 2: Enrich with SE93
    enrich_result = await enrich_with_se93(
        catalog_file=catalog_file,
        tstc_data=tstc_data,
        batch_size=se93_batch_size,
        prefix_filter=prefix_filter,
        max_transactions=max_se93_transactions,
    )

    return {
        "success": True,
        "tstc_total": tstc_result.get("total_transactions", 0),
        **enrich_result,
    }
