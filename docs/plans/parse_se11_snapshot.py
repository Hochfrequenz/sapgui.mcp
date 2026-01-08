"""
Parse SE11 browser_snapshot output and save to extraction checkpoint.

Usage:
    python parse_se11_snapshot.py '<snapshot_text>' '<table_name>'

Or pipe the snapshot:
    echo '<snapshot>' | python parse_se11_snapshot.py - '<table_name>'
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

CHECKPOINT_FILE = Path(__file__).parent / "extraction_checkpoint.jsonl"
PROGRESS_FILE = Path(__file__).parent / "extraction_progress.json"


def parse_se11_snapshot(snapshot: str, table_name: str) -> dict:
    """Parse SE11 browser snapshot and extract table metadata."""

    result = {
        "tabname": table_name,
        "description": None,
        "extracted_at": datetime.now().isoformat(),
        "fields": []
    }

    # Extract table description (Kurzbeschreibung)
    # Pattern: textbox "Kurzbeschreibung": <description>
    desc_match = re.search(r'textbox "Kurzbeschreibung": ([^\n]+)', snapshot)
    if desc_match:
        result["description"] = desc_match.group(1).strip()

    # Extract fields from grid rows
    # Pattern: row "... FIELDNAME ... DATENELEMENT DATATYPE LENGTH DECIMALS ... DESCRIPTION":
    # Each row contains: selection, field, key checkbox, init checkbox, datenelement, datatype, length, decimals, coord, description

    # Find all data rows (not header, not empty "Leer" rows)
    row_pattern = re.compile(
        r'row "Zum Auswählen einer Zeile.*?'
        r'(\S+)\s+'           # Field name
        r'(?:\s*)'            # Optional space
        r'(\S+)\s+'           # Data element (rollname)
        r'([A-Z0-9]+)\s+'     # Data type
        r'(\d+)\s+'           # Length
        r'(\d+)\s+'           # Decimals
        r'\d+\s+'             # Coord (always 0)
        r'([^"]+)"',          # Description (until closing quote)
        re.DOTALL
    )

    # Alternative: parse from gridcell patterns
    # gridcell "FIELDNAME": ... gridcell "DATATYPE": ... gridcell "Description":

    position = 0

    # Find rows by looking for the pattern in accessibility tree
    lines = snapshot.split('\n')
    current_row = {}

    for line in lines:
        line = line.strip()

        # Check for row with field data pattern
        # Example: row "Zum Auswählen einer Zeile drücken Sie die Leertaste. CLIENT   MANDT CLNT 3 0 0 Mandant":
        row_match = re.match(
            r'- row "Zum Auswählen.*?\. (\S+)\s+.*?(\S+)\s+([A-Z0-9]+)\s+(\d+)\s+(\d+)\s+\d+\s+(.+?)":',
            line
        )
        if row_match:
            position += 1
            fieldname = row_match.group(1)
            rollname = row_match.group(2)
            datatype = row_match.group(3)
            length = int(row_match.group(4))
            decimals = int(row_match.group(5))
            description = row_match.group(6).strip()

            # Check if key field (look for [checked] in the row's checkbox)
            keyflag = ""
            # Key fields have [checked] checkbox after the field name

            result["fields"].append({
                "fieldname": fieldname,
                "position": position,
                "keyflag": keyflag,  # Will be enhanced below
                "datatype": datatype,
                "length": length,
                "decimals": decimals,
                "rollname": rollname,
                "description": description
            })

    # If regex didn't work well, try a more robust approach
    if not result["fields"]:
        # Look for gridcell patterns
        # Each field appears as: gridcell "FIELDNAME": followed by checkboxes, then gridcell "ROLLNAME": etc.

        # Split by row markers
        row_blocks = re.split(r'- row "Zum Auswählen', snapshot)

        for block in row_blocks[1:]:  # Skip first (before any row)
            if 'Leer' in block[:100]:  # Empty row
                continue

            position += 1
            field_data = {}

            # Extract field name
            field_match = re.search(r'gridcell "([A-Z0-9_]+)":\s*\n\s*- textbox', block)
            if field_match:
                field_data["fieldname"] = field_match.group(1)

            # Check for key flag (checkbox [checked])
            # The key checkbox comes after the field name
            key_check = re.search(r'gridcell "":\s*\n\s*- checkbox "" \[checked\]', block)
            field_data["keyflag"] = "X" if key_check else ""

            # Extract rollname/datenelement
            rollname_match = re.search(r'gridcell "([A-Z0-9_/]+)":\s*\n\s*- textbox\s*\n.*?gridcell "([A-Z0-9]+)":', block)
            if rollname_match:
                field_data["rollname"] = rollname_match.group(1)
                field_data["datatype"] = rollname_match.group(2)

            # Extract length, decimals
            nums = re.findall(r'gridcell "(\d+)":', block)
            if len(nums) >= 2:
                field_data["length"] = int(nums[0])
                field_data["decimals"] = int(nums[1])

            # Extract description (last non-empty gridcell with textbox)
            desc_matches = re.findall(r'gridcell "([^"]+)":\s*\n\s*- textbox\s*$', block, re.MULTILINE)
            if desc_matches:
                field_data["description"] = desc_matches[-1]

            if "fieldname" in field_data:
                field_data["position"] = position
                field_data.setdefault("keyflag", "")
                field_data.setdefault("datatype", "")
                field_data.setdefault("length", 0)
                field_data.setdefault("decimals", 0)
                field_data.setdefault("rollname", "")
                field_data.setdefault("description", "")
                result["fields"].append(field_data)

    # Final fallback: parse from the raw row text
    if not result["fields"]:
        # Pattern for the row summary text
        # "Zum Auswählen einer Zeile drücken Sie die Leertaste. CLIENT   MANDT CLNT 3 0 0 Mandant"
        row_texts = re.findall(
            r'row "Zum Auswählen einer Zeile drücken Sie die Leertaste\. '
            r'(\S+)\s+'        # fieldname
            r'(?:(\S+)\s+)?'   # optional rollname
            r'([A-Z]+)\s+'     # datatype
            r'(\d+)\s+'        # length
            r'(\d+)\s+'        # decimals
            r'\d+\s+'          # coord
            r'(.+?)"',         # description
            snapshot
        )

        for i, match in enumerate(row_texts):
            fieldname, rollname, datatype, length, decimals, description = match
            result["fields"].append({
                "fieldname": fieldname,
                "position": i + 1,
                "keyflag": "",  # Need to check separately
                "datatype": datatype,
                "length": int(length),
                "decimals": int(decimals),
                "rollname": rollname or "",
                "description": description.strip()
            })

    # Determine key fields by checking for [checked] checkboxes
    # Look for pattern: gridcell "FIELDNAME": ... checkbox "" [checked]
    for field in result["fields"]:
        fname = field["fieldname"]
        # Check if this field has a checked key checkbox
        key_pattern = rf'gridcell "{fname}".*?checkbox "" \[checked\] \[disabled\]'
        if re.search(key_pattern, snapshot, re.DOTALL):
            field["keyflag"] = "X"

    return result


def save_checkpoint(record: dict) -> None:
    """Append record to checkpoint file."""
    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def update_progress(table_name: str, success: bool) -> None:
    """Update progress tracker."""
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        progress = {"tables": {"completed": [], "failed": []}, "transactions": {"completed": [], "failed": []}}

    if success:
        if table_name not in progress["tables"]["completed"]:
            progress["tables"]["completed"].append(table_name)
    else:
        if table_name not in progress["tables"]["failed"]:
            progress["tables"]["failed"].append(table_name)

    progress["last_updated"] = datetime.now().isoformat()

    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


def main():
    if len(sys.argv) < 3:
        print("Usage: python parse_se11_snapshot.py '<snapshot>' '<table_name>'")
        print("   or: python parse_se11_snapshot.py - '<table_name>' (read from stdin)")
        sys.exit(1)

    snapshot_arg = sys.argv[1]
    table_name = sys.argv[2]

    if snapshot_arg == "-":
        snapshot = sys.stdin.read()
    else:
        snapshot = snapshot_arg

    try:
        record = parse_se11_snapshot(snapshot, table_name)

        if not record["fields"]:
            print(f"ERROR: No fields parsed for {table_name}")
            update_progress(table_name, False)
            sys.exit(1)

        save_checkpoint(record)
        update_progress(table_name, True)

        print(f"OK: {table_name}")
        print(f"  Description: {record['description']}")
        print(f"  Fields: {len(record['fields'])}")
        for f in record["fields"][:3]:
            print(f"    - {f['fieldname']}: {f['description']}")
        if len(record["fields"]) > 3:
            print(f"    ... and {len(record['fields']) - 3} more")

    except Exception as e:
        print(f"ERROR: {e}")
        update_progress(table_name, False)
        sys.exit(1)


if __name__ == "__main__":
    main()
