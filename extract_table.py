#!/usr/bin/env python3
"""Extract table metadata from SE11 snapshot and save to us4g_metadata.json."""
import re
import json
import sys


def parse_snapshot(snapshot: str) -> dict:
    """Parse SE11 browser_snapshot and return table metadata."""
    # Check if table doesn't exist
    if "existiert nicht" in snapshot or "does not exist" in snapshot.lower():
        return None

    result = {
        "beschreibung": "",
        "anzahl_felder": 0,
        "felder": []
    }

    # Extract description - handle quoted descriptions
    desc_match = re.search(r'textbox "Kurzbeschreibung": "?([^"\n]+)"?', snapshot)
    if desc_match:
        result["beschreibung"] = desc_match.group(1).strip().strip('"')

    # Extract field count from pagination button pattern: button "1" / button "27"
    count_match = re.search(r'button "\d+"\s*\n\s*- button /\s*\n\s*- button "(\d+)"', snapshot)
    if count_match:
        result["anzahl_felder"] = int(count_match.group(1))

    # Parse field rows - use flexible pattern for Umlauts
    # Pattern: row "Zum Auswählen...Leertaste. FIELDNAME DATAELEMENT TYPE LENGTH DEC COORD DESCRIPTION":
    field_pattern = r'row "Zum Ausw.hlen einer Zeile dr.cken Sie die Leertaste\. (\S+)\s+(\S+)\s+(\w+)\s+(\d+)\s+(\d+)\s+\d+\s+([^"]+)":'

    # Split by rows and process each
    rows = re.split(r'(?=- row "Zum Ausw)', snapshot)

    for row_text in rows:
        match = re.search(field_pattern, row_text)
        if match:
            field_name = match.group(1)
            # Skip .INCLUDE entries
            if field_name == '.INCLUDE':
                continue

            # Check if key field (checkbox [checked])
            is_key = 'checkbox "" [checked]' in row_text

            field = {
                "feldname": field_name,
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


def add_table(table_name: str, table_data: dict, metadata_path: str = 'us4g_metadata.json'):
    """Add table to metadata file."""
    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    metadata['tabellen'][table_name] = table_data
    metadata['fortschritt']['extrahiert'] = len(metadata['tabellen'])

    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    return len(metadata['tabellen'])


def extract_and_save(table_name: str, snapshot: str):
    """Extract table from snapshot and save to metadata."""
    result = parse_snapshot(snapshot)
    if result is None:
        print(f"NOT_FOUND: {table_name}")
        return None

    total = add_table(table_name, result)
    print(f"OK: {table_name} ({len(result['felder'])} fields) - Total: {total}/613")
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_table.py TABLE_NAME [snapshot_file]")
        sys.exit(1)

    table_name = sys.argv[1]

    if len(sys.argv) >= 3:
        with open(sys.argv[2], 'r', encoding='utf-8') as f:
            snapshot = f.read()
    else:
        snapshot = sys.stdin.read()

    extract_and_save(table_name, snapshot)
