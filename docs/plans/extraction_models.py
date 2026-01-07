"""
Pydantic models for SAP knowledge extraction.
Use this module to add/update extracted table and transaction metadata.

Usage:
    from extraction_models import ExtractionDB, TableRecord, FieldRecord

    db = ExtractionDB.load()
    db.add_table(TableRecord(
        tabname="/US4G/EXAMPLE",
        description="Example table",
        fields=[FieldRecord(fieldname="MANDT", position=1, ...)]
    ))
    db.save()
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# File paths
DATA_DIR = Path(__file__).parent
TABLES_FILE = DATA_DIR / "extracted_tables.json"
TRANSACTIONS_FILE = DATA_DIR / "extracted_transactions.json"
PROGRESS_FILE = DATA_DIR / "extraction_progress.json"


class FieldRecord(BaseModel):
    """A single field in an SAP table."""
    fieldname: str
    position: int = Field(ge=1)
    keyflag: Literal["X", ""] = ""
    datatype: str = ""
    length: int = Field(default=0, ge=0)
    decimals: int = Field(default=0, ge=0)
    rollname: str = ""
    domname: str = ""
    description: str = ""


class TableRecord(BaseModel):
    """Metadata for an SAP database table."""
    tabname: str
    description: str | None = None
    extracted_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    fields: list[FieldRecord] = Field(default_factory=list)

    @property
    def key_fields(self) -> list[str]:
        return [f.fieldname for f in self.fields if f.keyflag == "X"]


class TransactionRecord(BaseModel):
    """Metadata for an SAP transaction code."""
    tcode: str
    title: str | None = None
    program: str | None = None
    dynpro: str | None = None
    package: str | None = None
    ttype: str | None = None
    status: Literal["exists", "not_found", "no_auth"] = "exists"
    extracted_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ExtractionProgress(BaseModel):
    """Progress tracker for extraction."""
    tables_completed: list[str] = Field(default_factory=list)
    tables_failed: list[str] = Field(default_factory=list)
    transactions_completed: list[str] = Field(default_factory=list)
    transactions_failed: list[str] = Field(default_factory=list)
    current_batch: str | None = None
    last_updated: str | None = None


class ExtractionDB:
    """Database for managing extracted SAP metadata."""

    def __init__(self):
        self.tables: dict[str, TableRecord] = {}
        self.transactions: dict[str, TransactionRecord] = {}
        self.progress = ExtractionProgress()

    @classmethod
    def load(cls) -> ExtractionDB:
        """Load existing data from JSON files."""
        db = cls()

        # Load tables
        if TABLES_FILE.exists():
            data = json.loads(TABLES_FILE.read_text(encoding="utf-8"))
            for item in data:
                rec = TableRecord.model_validate(item)
                db.tables[rec.tabname] = rec

        # Load transactions
        if TRANSACTIONS_FILE.exists():
            data = json.loads(TRANSACTIONS_FILE.read_text(encoding="utf-8"))
            for item in data:
                rec = TransactionRecord.model_validate(item)
                db.transactions[rec.tcode] = rec

        # Load progress
        if PROGRESS_FILE.exists():
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            db.progress = ExtractionProgress.model_validate(data)

        return db

    def save(self) -> None:
        """Save all data to JSON files."""
        # Save tables
        tables_list = [t.model_dump() for t in self.tables.values()]
        TABLES_FILE.write_text(
            json.dumps(tables_list, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Save transactions
        trans_list = [t.model_dump() for t in self.transactions.values()]
        TRANSACTIONS_FILE.write_text(
            json.dumps(trans_list, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Save progress
        self.progress.last_updated = datetime.now().isoformat()
        PROGRESS_FILE.write_text(
            json.dumps(self.progress.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_table(self, record: TableRecord) -> None:
        """Add or update a table record."""
        self.tables[record.tabname] = record
        if record.tabname not in self.progress.tables_completed:
            self.progress.tables_completed.append(record.tabname)
        # Remove from failed if it was there
        if record.tabname in self.progress.tables_failed:
            self.progress.tables_failed.remove(record.tabname)

    def mark_table_failed(self, tabname: str) -> None:
        """Mark a table extraction as failed."""
        if tabname not in self.progress.tables_failed:
            self.progress.tables_failed.append(tabname)

    def add_transaction(self, record: TransactionRecord) -> None:
        """Add or update a transaction record."""
        self.transactions[record.tcode] = record
        if record.tcode not in self.progress.transactions_completed:
            self.progress.transactions_completed.append(record.tcode)
        if record.tcode in self.progress.transactions_failed:
            self.progress.transactions_failed.remove(record.tcode)

    def mark_transaction_failed(self, tcode: str) -> None:
        """Mark a transaction extraction as failed."""
        if tcode not in self.progress.transactions_failed:
            self.progress.transactions_failed.append(tcode)

    def is_table_done(self, tabname: str) -> bool:
        """Check if table already extracted."""
        return tabname in self.tables

    def is_transaction_done(self, tcode: str) -> bool:
        """Check if transaction already extracted."""
        return tcode in self.transactions

    def summary(self) -> str:
        """Get extraction summary."""
        return (
            f"Tables: {len(self.tables)} extracted, "
            f"{len(self.progress.tables_failed)} failed\n"
            f"Transactions: {len(self.transactions)} extracted, "
            f"{len(self.progress.transactions_failed)} failed"
        )


def parse_se11_snapshot(snapshot: str, table_name: str) -> dict:
    """Parse SE11 browser snapshot and extract table metadata."""
    import re

    result = {
        "tabname": table_name,
        "description": None,
        "fields": []
    }

    # Extract table description (Kurzbeschreibung)
    desc_match = re.search(r'textbox "Kurzbeschreibung": ([^\n]+)', snapshot)
    if desc_match:
        result["description"] = desc_match.group(1).strip()

    # Extract fields from grid rows
    # Format: row "Zum Auswählen einer Zeile drücken Sie die Leertaste. FIELDNAME   DATAELEMENT DATATYPE LENGTH DECIMALS COORD DESCRIPTION":
    # Pattern: FIELDNAME (spaces) DATAELEMENT DATATYPE LENGTH DECIMALS COORD DESCRIPTION
    position = 0

    # Match rows with field data - format is: FIELDNAME followed by spaces, then DATAELEMENT DATATYPE etc
    # Example: "CLIENT   MANDT CLNT 3 0 0 Mandant"
    row_pattern = re.compile(
        r'row "Zum Auswählen einer Zeile drücken Sie die Leertaste\. '
        r'(\S+)\s+'           # FIELDNAME
        r'(\S+)\s+'           # DATAELEMENT
        r'([A-Z0-9]+)\s+'     # DATATYPE
        r'(\d+)\s+'           # LENGTH
        r'(\d+)\s+'           # DECIMALS
        r'\d+\s+'             # COORD (discard)
        r'(.+?)":'            # DESCRIPTION
    )

    for match in row_pattern.finditer(snapshot):
        position += 1
        fieldname = match.group(1)
        rollname = match.group(2)
        datatype = match.group(3)
        length = int(match.group(4))
        decimals = int(match.group(5))
        description = match.group(6).strip()

        result["fields"].append({
            "fieldname": fieldname,
            "position": position,
            "keyflag": "",
            "datatype": datatype,
            "length": length,
            "decimals": decimals,
            "rollname": rollname,
            "description": description
        })

    # Determine key fields - look for checked checkbox after field gridcell
    for field in result["fields"]:
        fname = field["fieldname"]
        # Pattern: gridcell "FIELDNAME": followed by checkbox "" [checked] [disabled]
        key_pattern = rf'gridcell "{re.escape(fname)}":\s*- textbox\s*- gridcell "":\s*- checkbox "" \[checked\] \[disabled\]'
        if re.search(key_pattern, snapshot, re.DOTALL):
            field["keyflag"] = "X"

    return result


# Convenience functions for command-line use
def add_table_from_snapshot(snapshot: str, tabname: str) -> str:
    """Parse SE11 snapshot and add table to database."""
    db = ExtractionDB.load()

    try:
        parsed = parse_se11_snapshot(snapshot, tabname)

        if not parsed["fields"]:
            db.mark_table_failed(tabname)
            db.save()
            return f"ERROR: No fields parsed for {tabname}"

        fields = [FieldRecord(**f) for f in parsed["fields"]]
        record = TableRecord(
            tabname=tabname,
            description=parsed.get("description"),
            fields=fields
        )

        db.add_table(record)
        db.save()

        return (
            f"OK: {tabname}\n"
            f"  Description: {record.description}\n"
            f"  Fields: {len(record.fields)}\n"
            f"  Key fields: {record.key_fields}"
        )

    except Exception as e:
        db.mark_table_failed(tabname)
        db.save()
        return f"ERROR: {e}"


def extract_tabname_from_snapshot(snapshot: str) -> str | None:
    """Extract table name from SE11 snapshot."""
    import re
    # Pattern: textbox "Transp.Tabelle": /US4G/MI_VIEW
    match = re.search(r'textbox "Transp\.Tabelle": ([^\n]+)', snapshot)
    if match:
        return match.group(1).strip()
    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python extraction_models.py summary")
        print("  python extraction_models.py process_snapshot '<snapshot_file>'")
        print("    (table name extracted from snapshot automatically)")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "summary":
        db = ExtractionDB.load()
        print(db.summary())

    elif cmd == "process_snapshot":
        # Process a snapshot file - table name extracted from file content
        if len(sys.argv) < 3:
            print("Usage: python extraction_models.py process_snapshot '<snapshot_file>'")
            sys.exit(1)

        snapshot_file = sys.argv[2]
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            snapshot = f.read()

        # Extract table name from the snapshot itself
        tabname = extract_tabname_from_snapshot(snapshot)
        if not tabname:
            print("ERROR: Could not extract table name from snapshot")
            sys.exit(1)

        result = add_table_from_snapshot(snapshot, tabname)
        print(result)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
