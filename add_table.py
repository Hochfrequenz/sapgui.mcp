#!/usr/bin/env python3
"""Add a single table to us4g_metadata.json."""
import json
import sys
import re


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

    # Extract description
    desc_match = re.search(r'textbox "Kurzbeschreibung": ([^\n]+)', snapshot)
    if desc_match:
        result["beschreibung"] = desc_match.group(1).strip()

    # Extract field count from pagination button
    count_match = re.search(r'button "(\d+)"\s*$', snapshot, re.MULTILINE)
    # Try to find pattern: button "1" / button "27"
    count_match2 = re.search(r'button "\d+"\s*\n\s*- button /\s*\n\s*- button "(\d+)"', snapshot)
    if count_match2:
        result["anzahl_felder"] = int(count_match2.group(1))

    # Parse field rows
    # Pattern: row "Zum Auswählen...Leertaste. FIELDNAME DATAELEMENT TYPE LENGTH DEC COORD DESCRIPTION":
    field_pattern = r'row "Zum Auswählen einer Zeile drücken Sie die Leertaste\. (\S+)\s+(\S+)\s+(\w+)\s+(\d+)\s+(\d+)\s+\d+\s+([^"]+)":'

    rows = re.split(r'(?=- row "Zum Auswählen)', snapshot)

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


def add_table(table_name: str, table_data: dict):
    """Add table to metadata file."""
    with open('us4g_metadata.json', 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    metadata['tabellen'][table_name] = table_data
    metadata['fortschritt']['extrahiert'] = len(metadata['tabellen'])

    with open('us4g_metadata.json', 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"Added {table_name} with {len(table_data['felder'])} fields")
    print(f"Total extracted: {len(metadata['tabellen'])}/613")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_table.py TABLE_NAME < snapshot.txt")
        sys.exit(1)

    table_name = sys.argv[1]
    snapshot = sys.stdin.read()

    result = parse_snapshot(snapshot)
    if result is None:
        print(json.dumps({"error": "Table does not exist", "table": table_name}))
    else:
        add_table(table_name, result)
