# SE11 Extraction Workflow for Sub-Agent

## Overview
Extract table field metadata from SAP SE11 using MCP tools and snapshot parsing.

## Files
- `se11_extractor.js` - Parser for browser_snapshot output
- `us4g_transp_tables.json` - List of all 613 /US4G/* tables
- `us4g_metadata.json` - Output file with extracted metadata

## Workflow per Table

### Step 1: Fill table name and display
```
browser_fill(selector="input[lsdata*='RSRD1-TBMA_VAL']", value="TABLE_NAME")
sap_keyboard(key="F7")
```

### Step 2: Read data via snapshot
```
browser_snapshot()
```

### Step 3: Parse snapshot (use se11_extractor.js logic)
The snapshot contains:
- `textbox "Transp.Tabelle": TABLE_NAME`
- `textbox "Kurzbeschreibung": DESCRIPTION`
- `button "X" / button "/" / button "TOTAL"` - field count
- `row "Zum Auswählen... FELDNAME DATENELEMENT DATENTYP LÄNGE DEZ KOORD KURZTEXT":` - field data
- `checkbox "" [checked]` after gridcell = key field

### Step 4: Go back for next table
```
sap_keyboard(key="F3")
```

## Parsing Logic (JavaScript)

```javascript
function parseSE11Snapshot(snapshotText) {
    const result = {tableName: '', description: '', fieldCount: 0, fields: []};

    // Table name
    const tableMatch = snapshotText.match(/textbox "Transp\.Tabelle":\s*([^\n]+)/);
    if (tableMatch) result.tableName = tableMatch[1].trim();

    // Description
    const descMatch = snapshotText.match(/textbox "Kurzbeschreibung":\s*([^\n]+)/);
    if (descMatch) result.description = descMatch[1].trim();

    // Field count
    const countMatch = snapshotText.match(/button "(\d+)"\s*\n\s*- button \/\s*\n\s*- button "(\d+)"/);
    if (countMatch) result.fieldCount = parseInt(countMatch[2]);

    // Parse field rows
    const rowPattern = /row "Zum Auswählen einer Zeile drücken Sie die Leertaste\.\s+([^"]+)":/g;
    let match;
    while ((match = rowPattern.exec(snapshotText)) !== null) {
        const parts = match[1].trim().split(/\s+/);
        if (parts.length >= 6 && !parts[0].includes('Feld')) {
            const rowStart = match.index;
            const rowContent = snapshotText.substring(rowStart, rowStart + 1000);
            const isKey = /gridcell "":\s*\n\s*- checkbox "" \[checked\]/.test(rowContent);

            result.fields.push({
                feldname: parts[0],
                datenelement: parts[1],
                datentyp: parts[2],
                laenge: parseInt(parts[3]) || 0,
                dezimalstellen: parseInt(parts[4]) || 0,
                kurztext: parts.slice(6).join(' '),
                schluesselfeld: isKey
            });
        }
    }
    return result;
}
```

## Batch Processing

1. Read `us4g_transp_tables.json` and `us4g_metadata.json`
2. Find tables not yet in metadata
3. For each missing table:
   - browser_fill + sap_keyboard F7
   - browser_snapshot + parse
   - sap_keyboard F3
4. Every 50 tables:
   - Update `us4g_metadata.json`
   - `git add us4g_metadata.json && git commit -m "WIP: /US4G/ (X/613)"`

## Error Handling

- If table doesn't exist: SAP shows error in status bar, skip and continue
- If parsing fails: Log error, skip table, continue
- Never stop until all tables processed

## Output Format (us4g_metadata.json)

```json
{
  "extraktionsdatum": "2026-01-07",
  "quelle": "SAP SE11 - ABAP Dictionary",
  "beschreibung": "S/4 Utilities /US4G/ Tabellen-Feldmetadaten",
  "fortschritt": {"extrahiert": 613, "gesamt": 613},
  "tabellen": {
    "/US4G/BILL_CYC": {
      "beschreibung": "Abrechnungszyklus",
      "anzahl_felder": 3,
      "felder": [
        {"feldname": "MANDT", "datenelement": "MANDT", "datentyp": "CLNT", "laenge": 3, "dezimalstellen": 0, "kurztext": "Mandant", "schluesselfeld": true},
        ...
      ]
    }
  }
}
```
