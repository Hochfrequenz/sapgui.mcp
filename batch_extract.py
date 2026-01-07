#!/usr/bin/env python3
"""Helper script to parse SE11 snapshot and update metadata JSON."""
import re
import json
import sys


def parse_se11_snapshot(snapshot: str) -> dict | None:
    """Parse SE11 browser_snapshot and return table metadata."""
    # Check if table doesn't exist
    if "existiert nicht" in snapshot or "does not exist" in snapshot.lower():
        return None

    result = {
        "beschreibung": "",
        "anzahl_felder": 0,
        "felder": []
    }

    # Extract description
    desc_match = re.search(r'textbox "Kurzbeschreibung": ([^\n]+)', snapshot)
    if desc_match:
        result["beschreibung"] = desc_match.group(1).strip()

    # Extract field count from pagination
    count_match = re.search(r'button /\s*\n\s*- button "(\d+)"', snapshot)
    if count_match:
        result["anzahl_felder"] = int(count_match.group(1))

    # Parse field rows
    field_pattern = r'row ["\']Zum Auswählen[^"\']*Leertaste\. (\S+)\s+(\S+)\s+(\w+)\s+(\d+)\s+(\d+)\s+\d+\s+([^"\']+)["\']:'

    # Split by rows to check key fields
    rows = re.split(r'(?=row ["\']Zum Auswählen)', snapshot)

    for row_text in rows:
        match = re.search(field_pattern, row_text)
        if match:
            is_key = '[checked]' in row_text.split('checkbox', 1)[1] if 'checkbox' in row_text else False

            field = {
                "feldname": match.group(1),
                "datenelement": match.group(2),
                "datentyp": match.group(3),
                "laenge": int(match.group(4)),
                "dezimalstellen": int(match.group(5)),
                "kurztext": match.group(6).strip(),
                "schluesselfeld": is_key
            }
            result["felder"].append(field)

    if not result["anzahl_felder"]:
        result["anzahl_felder"] = len(result["felder"])

    return result


def update_metadata_file(metadata_path: str, table_name: str, table_data: dict):
    """Add table data to metadata JSON file."""
    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    metadata["tabellen"][table_name] = table_data
    metadata["fortschritt"]["extrahiert"] = len(metadata["tabellen"])

    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python batch_extract.py METADATA_PATH TABLE_NAME < snapshot.txt")
        sys.exit(1)

    metadata_path = sys.argv[1]
    table_name = sys.argv[2]
    snapshot = sys.stdin.read()

    result = parse_se11_snapshot(snapshot)
    if result is None:
        print(json.dumps({"status": "not_found", "table": table_name}))
    else:
        update_metadata_file(metadata_path, table_name, result)
        print(json.dumps({
            "status": "ok",
            "table": table_name,
            "fields_found": len(result["felder"]),
            "total_fields": result["anzahl_felder"]
        }))
