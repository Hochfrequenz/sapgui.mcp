#!/usr/bin/env python3
"""Parse SE11 snapshot to extract field metadata."""
import re
import json
import sys

def parse_se11_snapshot(snapshot: str, table_name: str) -> dict:
    """
    Parse SE11 browser_snapshot output to extract table metadata.

    Returns:
        dict with table description and list of fields
    """
    result = {
        "name": table_name,
        "beschreibung": "",
        "felder": []
    }

    # Extract table description from: textbox "Kurzbeschreibung": DESCRIPTION
    desc_match = re.search(r'textbox "Kurzbeschreibung": ([^\n]+)', snapshot)
    if desc_match:
        result["beschreibung"] = desc_match.group(1).strip()

    # Pattern for field rows:
    # row "Zum Auswählen einer Zeile drücken Sie die Leertaste. FIELDNAME   DATAELEMENT TYPE LENGTH DEC COORD DESCRIPTION":
    # Note: Some descriptions have colons, so we need a more careful pattern

    # First, find all row definitions that match field pattern
    # The pattern in the snapshot is:
    # row "Zum Auswählen...Leertaste. FIELD DATAEL TYPE LEN DEC COORD DESC":

    field_pattern = r'row ["\']Zum Auswählen.*?Leertaste\. (\S+)\s+(\S+)\s+(\w+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([^"\']+)["\']:'

    # Also need to check for key fields (checkbox checked)
    # After a field row, look for: checkbox "" [checked]

    # Split by rows and process
    lines = snapshot.split('\n')
    current_field = None
    fields_found = []

    for line in lines:
        # Check for field row
        match = re.search(field_pattern, line)
        if match:
            field = {
                "feldname": match.group(1),
                "datenelement": match.group(2),
                "datentyp": match.group(3),
                "laenge": int(match.group(4)),
                "dezimalstellen": int(match.group(5)),
                "kurztext": match.group(7).strip(),
                "schluesselfeld": False  # Will be updated if checkbox is checked
            }
            fields_found.append(field)
            current_field = field
        elif current_field and '[checked]' in line and 'checkbox' in line:
            # This is a key field
            current_field["schluesselfeld"] = True

    result["felder"] = fields_found
    result["anzahl_felder"] = len(fields_found)

    return result


def test():
    # Test with sample snapshot
    sample = '''
    - textbox "Kurzbeschreibung": OBSOLET
    - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. MANDT   MANDT CLNT 3 0 0 Mandant":
          - gridcell "..."
          - checkbox "" [checked] [disabled]
    - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. DB_KEY   /BOBF/CONF_KEY RAW 16 0 0 NodeID":
          - gridcell "..."
          - checkbox "" [checked] [disabled]
    - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. PARENT_KEY /BOBF/CONF_KEY RAW 16 0 0 NodeID":
          - gridcell "..."
          - checkbox [disabled]
    '''
    result = parse_se11_snapshot(sample, "/US4G/TEST")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test()
    else:
        # Read snapshot from stdin
        snapshot = sys.stdin.read()
        result = parse_se11_snapshot(snapshot, sys.argv[1] if len(sys.argv) > 1 else "UNKNOWN")
        print(json.dumps(result, indent=2, ensure_ascii=False))
