#!/usr/bin/env python3
"""
Convert DD03L ALV export to us4g_metadata.json format.
Reads the sap_read_table output and creates table->fields structure.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

def convert_dd03l_to_metadata(input_file: str, output_file: str):
    """Convert DD03L table export to metadata JSON."""

    # Read input file
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data.get('success'):
        print(f"Error: Input file indicates failure: {data.get('error')}")
        return

    rows = data.get('rows', [])
    print(f"Processing {len(rows)} field rows...")

    # Group fields by table
    tables = defaultdict(list)

    for row in rows:
        row_data = row.get('data', {})

        # Extract field values (handle messy header names)
        tabname = None
        fieldname = None
        position = 0
        keyflag = ''
        datatype = ''
        leng = 0
        decimals = 0

        for key, value in row_data.items():
            key_lower = key.lower()
            if 'tabellenname' in key_lower or 'tabelle' in key_lower:
                tabname = value
            elif 'feldname' in key_lower or 'feld' in key_lower:
                fieldname = value
            elif 'position' in key_lower or 'tabpos' in key_lower:
                try:
                    position = int(value) if value else 0
                except:
                    position = 0
            elif 'schlüssel' in key_lower or 'key' in key_lower:
                keyflag = value
            elif 'datentyp' in key_lower or 'datatype' in key_lower:
                datatype = value
            elif 'stellen' in key_lower or 'länge' in key_lower or 'leng' in key_lower:
                try:
                    leng = int(value) if value else 0
                except:
                    leng = 0
            elif 'dezimal' in key_lower or 'decimal' in key_lower:
                try:
                    decimals = int(value) if value else 0
                except:
                    decimals = 0

        if tabname and fieldname:
            tables[tabname].append({
                'feldname': fieldname,
                'position': position,
                'schluesselfeld': keyflag == 'X',
                'datentyp': datatype,
                'laenge': leng,
                'dezimalstellen': decimals
            })

    # Sort fields by position within each table
    for tabname in tables:
        tables[tabname].sort(key=lambda x: x['position'])
        # Remove position from output
        for field in tables[tabname]:
            del field['position']

    # Build output structure
    output = {
        'extraktionsdatum': '2026-01-07',
        'quelle': 'SAP DD03L via ABAP Report',
        'beschreibung': 'S/4 Utilities /US4G/ Tabellen-Feldmetadaten',
        'fortschritt': {
            'extrahiert': len(tables),
            'gesamt': len(tables)
        },
        'tabellen': {}
    }

    for tabname in sorted(tables.keys()):
        output['tabellen'][tabname] = {
            'beschreibung': '',  # Not available from DD03L
            'anzahl_felder': len(tables[tabname]),
            'felder': tables[tabname]
        }

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Converted {len(tables)} tables to {output_file}")

if __name__ == '__main__':
    input_file = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\KleinKonstantin\.claude\projects\C--github-sapwebgui-mcp\da657a31-d602-4e14-aec8-cdc26b52a8e6\tool-results\mcp-sap-webgui-sap_read_table-1767816171143.txt'
    output_file = sys.argv[2] if len(sys.argv) > 2 else r'C:\github\sapwebgui.mcp\us4g_metadata_new.json'

    convert_dd03l_to_metadata(input_file, output_file)
