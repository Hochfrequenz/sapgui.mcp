#!/usr/bin/env python3
"""Parse SE11 snapshot to extract field metadata."""
import re
import json
import sys


def parse_se11_snapshot(snapshot: str, table_name: str) -> dict:
    """
    Parse SE11 browser_snapshot output to extract table metadata.

    Returns dict with table info and fields.
    """
    result = {
        "beschreibung": "",
        "anzahl_felder": 0,
        "felder": []
    }

    # Check if table doesn't exist
    if "existiert nicht" in snapshot or "does not exist" in snapshot.lower():
        return None

    # Extract table description
    desc_match = re.search(r'textbox "Kurzbeschreibung": ([^\n]+)', snapshot)
    if desc_match:
        result["beschreibung"] = desc_match.group(1).strip()

    # Extract total field count from button pattern: button "1" / button "82"
    count_match = re.search(r'button "\d+"\s*\n\s*- button /\s*\n\s*- button "(\d+)"', snapshot)
    if count_match:
        result["anzahl_felder"] = int(count_match.group(1))

    # Pattern for field rows - handles both single and double quote variants
    # row "Zum Auswählen...Leertaste. FIELD DATAEL TYPE LEN DEC COORD DESC":
    field_pattern = r'row ["\']Zum Auswählen[^"\']*Leertaste\. (\S+)\s+(\S+)\s+(\w+)\s+(\d+)\s+(\d+)\s+\d+\s+([^"\']+)["\']:'

    # Find all field matches
    matches = re.finditer(field_pattern, snapshot)
    fields_data = []

    for match in matches:
        field = {
            "feldname": match.group(1),
            "datenelement": match.group(2),
            "datentyp": match.group(3),
            "laenge": int(match.group(4)),
            "dezimalstellen": int(match.group(5)),
            "kurztext": match.group(6).strip(),
            "schluesselfeld": False
        }
        fields_data.append(field)

    # Now check which fields are key fields by looking at checkbox patterns
    # The pattern is: field row, then gridcells with checkboxes
    # Key fields have [checked] on their checkboxes

    # Split snapshot by row patterns
    rows = re.split(r'(?=row ["\']Zum Auswählen)', snapshot)

    for i, row_text in enumerate(rows):
        if i == 0:
            continue  # Skip header

        # Extract field name from this row
        name_match = re.search(r'Leertaste\. (\S+)', row_text)
        if name_match:
            field_name = name_match.group(1)

            # Check if there's a [checked] checkbox in this row's gridcells
            # Key field checkbox pattern: gridcell "": checkbox "" [checked]
            if '[checked]' in row_text:
                # Find the corresponding field in our list
                for field in fields_data:
                    if field["feldname"] == field_name:
                        field["schluesselfeld"] = True
                        break

    result["felder"] = fields_data
    if not result["anzahl_felder"]:
        result["anzahl_felder"] = len(fields_data)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parse_snapshot.py TABLENAME < snapshot.txt")
        sys.exit(1)

    table_name = sys.argv[1]
    snapshot = sys.stdin.read()

    result = parse_se11_snapshot(snapshot, table_name)
    if result is None:
        print(json.dumps({"error": "Table does not exist"}))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
