# SE11 Field Extraction Script

## Parsing browser_snapshot Output

The SE11 browser_snapshot contains all field data in this format:

```
- textbox "Transp.Tabelle": /US4G/TABLENAME
- textbox "Kurzbeschreibung": Table Description Here
- button "1"
- button /
- button "82"    <-- Total field count
- row "Zum Auswählen einer Zeile drücken Sie die Leertaste. FELDNAME DATENELEMENT DATENTYP LÄNGE DEZ KOORD KURZTEXT":
  - gridcell "FELDNAME"
  - gridcell "":
    - checkbox "" [checked] [disabled]   <-- [checked] = Schlüsselfeld
```

## Field Extraction Pattern

For each row matching:
```
row "Zum Auswählen einer Zeile drücken Sie die Leertaste. {DATA}":
```

Parse {DATA} as space-separated:
- [0] = feldname
- [1] = datenelement
- [2] = datentyp (CLNT, CHAR, NUMC, DATS, RAW, STRING, etc.)
- [3] = laenge
- [4] = dezimalstellen
- [5] = koordinatensystem (ignore)
- [6+] = kurztext (join with spaces)

## Key Field Detection

After the row, look for:
```
gridcell "":
  - checkbox "" [checked]
```

If [checked] is present in the SECOND gridcell (after feldname), it's a key field.

## .INCLUDE Handling

Rows with feldname ".INCLUDE" are include structures:
- datenelement contains the structure name (e.g., "/US4G/S_EDN_DEV_POS")
- datentyp = "STRU"

## Workflow

1. browser_fill selector="input[lsdata*='RSRD1-TBMA_VAL']" value="TABLE_NAME"
2. sap_keyboard key="F7"
3. browser_snapshot -> Parse as described above
4. sap_keyboard key="F3"
5. Repeat for next table

## JSON Output Format

```json
{
  "tableName": "/US4G/EXAMPLE",
  "beschreibung": "Description text",
  "anzahl_felder": 15,
  "felder": [
    {
      "feldname": "MANDT",
      "datenelement": "MANDT",
      "datentyp": "CLNT",
      "laenge": 3,
      "dezimalstellen": 0,
      "kurztext": "Mandant",
      "schluesselfeld": true
    }
  ]
}
```

## Scrolling for Large Tables

If fieldCount > visible rows (usually ~30), the table needs scrolling.
The "1 / 82" indicator shows total. Use Page Down or scroll to get more rows.
