#!/usr/bin/env python3
"""Consolidate scraped TSTC data into a transaction catalog.

This script reads all SE16 query result files and creates the
transactions.json catalog file.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sapguimcp.catalog.models import TransactionCatalog, TransactionInfo, detect_area


def load_se16_result(file_path: Path) -> list[dict]:
    """Load rows from an SE16 query result file."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    result = data.get("result", data)
    rows = result.get("rows", [])

    # Extract data from each row
    transactions = []
    for row in rows:
        row_data = row.get("data", row)
        tcode = row_data.get("TCODE") or row_data.get("Transaktionscode", "")
        if tcode:
            # Get description - column name is "Transaktionstext" in German UI
            desc = row_data.get("Transaktionstext") or row_data.get("TTEXT", "")
            transactions.append(
                {
                    "TCODE": str(tcode).strip(),
                    "PGMNA": str(row_data.get("PGMNA") or row_data.get("Programm", "")).strip(),
                    "DESSION": row_data.get("DESSION") or row_data.get("Dynpro"),
                    "TTEXT": str(desc).strip() if desc else "",
                }
            )
    return transactions


def main():
    """Main consolidation function."""
    # Paths
    tool_results_dir = Path(
        r"C:\Users\KleinKonstantin\.claude\projects\C--github-sapgui-mcp\d667c1d3-9bc0-4d17-a90f-c1a710d03224\tool-results"
    )
    data_dir = project_root / "src" / "sapguimcp" / "data"
    output_file = data_dir / "transactions.json"

    # Ensure data directory exists
    data_dir.mkdir(parents=True, exist_ok=True)

    # Collect all transactions
    all_transactions: dict[str, dict] = {}

    # Load from SE16 result files
    for file_path in tool_results_dir.glob("mcp-sap-webgui-sap_se16_query-*.txt"):
        print(f"Loading {file_path.name}...")
        try:
            rows = load_se16_result(file_path)
            for row in rows:
                tcode = row["TCODE"].upper()
                if tcode and tcode not in all_transactions:
                    all_transactions[tcode] = row
            print(f"  -> {len(rows)} transactions")
        except Exception as e:
            print(f"  -> Error: {e}")

    print(f"\nTotal unique transactions: {len(all_transactions)}")

    # Create catalog
    transactions = []
    for tcode, row_data in sorted(all_transactions.items()):
        txn = TransactionInfo(
            tcode=tcode,
            description=row_data.get("TTEXT", ""),
            program=row_data.get("PGMNA", ""),
            screen_number=str(row_data.get("DESSION", "")).strip() or None,
            area=detect_area(tcode),
            enriched=False,  # Not enriched with SE93 yet
        )
        transactions.append(txn)

    catalog = TransactionCatalog(
        transactions=transactions,
        source_system="dev",
        language="DE",
        last_updated=datetime.now(UTC),
        tstc_count=len(transactions),
        enriched_count=0,
    )

    # Save catalog
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(catalog.model_dump_json(indent=2))

    print(f"\nCatalog saved to: {output_file}")
    print(f"Total transactions: {len(catalog.transactions)}")

    # Print area breakdown
    area_counts: dict[str, int] = {}
    for txn in catalog.transactions:
        area = txn.area or "Unknown"
        area_counts[area] = area_counts.get(area, 0) + 1

    print("\nTransactions by area:")
    for area, count in sorted(area_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {area}: {count}")


if __name__ == "__main__":
    main()
