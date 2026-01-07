# BAPI Catalog Update Guide

This document explains how to update the IS-U / S/4 Utilities BAPI Catalog.

## Overview

The catalog is stored in `src/sapwebguimcp/data/bapi_catalog.json` and provides:
- **Namespaces**: SAP namespace documentation (/IDXGC/, /APE/, etc.)
- **Tables**: Key IS-U tables and their relationships
- **Categories**: Functional areas (billing, devices, etc.)
- **BAPIs/Function Modules**: Verified and unverified entries
- **Classes**: ABAP classes (when extracted)

## How to Update

### Method 1: Manual Addition

1. Open `src/sapwebguimcp/data/bapi_catalog.json`
2. Add new entries to the appropriate section:
   - `bapis` - for verified BAPIs with full signatures
   - `function_modules` - for non-BAPI function modules
   - `classes` - for ABAP classes
   - `unverified_objects` - for objects from documentation (not yet verified in system)
3. Update `metadata.last_updated` with today's date
4. Increment `metadata.version` (e.g., 1.1.0 -> 1.2.0)

### Method 2: SAP System Extraction

Use these SAP transactions to find objects:

| Transaction | Purpose | Search Pattern Example |
|-------------|---------|------------------------|
| **SE37** | Function Modules | `BAPI_ISU*`, `/IDXGC/*` |
| **SE24** | Classes | `CL_ISU_*`, `CL_FKK_*` |
| **SE16N** | Table TFDIR for FMs | Filter on FUNCNAME |
| **SE16N** | Table SEOCLASS for classes | Filter on CLSNAME |

#### Steps in SE37:
1. Enter pattern (e.g., `BAPI_ISU*`)
2. Press F4 to search
3. Note all matching function module names
4. For each FM, view Import/Export/Tables tabs for signature

#### Steps in SE24:
1. Enter pattern (e.g., `CL_ISU_*`)
2. Press F4 to search
3. Note all matching class names
4. View Methods tab for public methods

### Method 3: Using Claude Code with MCP

Ask Claude Code to:
```
Search in SAP for all function modules matching BAPI_ISU*
and extract their signatures
```

The MCP server will navigate SAP and extract the information.

## Search Patterns

The catalog includes recommended search patterns in `search_patterns`:

### Function Modules
```
BAPI_ISU*, BAPI_DEVICE*, BAPI_MTRREAD*, BAPI_CTRAC*, BAPI_BUPA*,
BAPI_EQUI*, BAPI_FLOC*, ISU_*, FKK*, FKKBAPI*,
/IDXGC/*, /IDXGL/*, /APE/*, /APEU/*, /UCOM/*, /US4G/*
```

### Classes
```
CL_ISU_*, CL_FKK_*, CL_BUPA_*, CL_IDXGC_*,
/IDXGC/CL_*, /IDXGL/CL_*, /APE/CL_*
```

### Interfaces
```
IF_ISU_*, IF_FKK_*, IF_BUPA_*
```

## JSON Structure

### Adding a verified BAPI:
```json
{
  "name": "BAPI_ISU_NEW_FUNCTION",
  "category": "installation",
  "description": "What this BAPI does",
  "function_group": "ISU_SOMETHING",
  "verified_in_system": true,
  "import_parameters": [
    {"name": "PARAM1", "type": "TYPE1", "optional": false, "description": "..."}
  ],
  "export_parameters": [],
  "tables_parameters": [],
  "usage_notes": "Use BAPI_TRANSACTION_COMMIT after call"
}
```

### Adding an unverified object:
```json
{
  "name": "BAPI_ISU_MAYBE_EXISTS",
  "type": "function_module",
  "category": "billing",
  "description": "From documentation - not verified",
  "source": "documentation"
}
```

### Adding a class:
```json
{
  "name": "CL_ISU_SOMETHING",
  "category": "device",
  "description": "Class for device management",
  "verified_in_system": true,
  "key_methods": ["CREATE", "UPDATE", "DELETE", "GET_LIST"],
  "interfaces": ["IF_ISU_DEVICE"]
}
```

## Accessing the Catalog via MCP

The catalog is exposed as MCP resources:

| Resource URI | Description |
|--------------|-------------|
| `bapi://catalog` | Full catalog |
| `bapi://catalog/categories` | List of categories |
| `bapi://catalog/category/{id}` | BAPIs in a category |
| `bapi://catalog/bapi/{name}` | Single BAPI details |
| `bapi://catalog/search/{pattern}` | Search by name/description |
| `bapi://catalog/metadata` | Version and statistics |

## Best Practices

1. **Verify before adding**: If possible, verify objects exist in your SAP system
2. **Document sources**: Use `source` field for unverified objects
3. **Keep signatures minimal**: Only document parameters you've verified
4. **Update incrementally**: Add a few objects at a time, test, commit
5. **Use categories**: Assign objects to appropriate functional categories

---

## Funktionierende Sub-Agent Workflows

Die folgenden Workflows wurden getestet und funktionieren mit dem SAP WebGUI MCP Server.

### Workflow 1: Tabellennamen aus Namespace extrahieren (SE16 + DD02V)

**Ziel:** Alle Tabellennamen eines Namespaces extrahieren (z.B. `/US4G/*`)

**Vorgehen:**
1. `sap_transaction` mit `tcode="SE16"`
2. Tabellenname `DD02V` eingeben und Enter
3. Filter setzen mit `sap_fill_form`:
   - TABNAME (von): `/US4G/*`
   - DDLANGUAGE (von): `D`
   - TABCLASS (von): `TRANSP` (nur transparente Tabellen, keine Strukturen!)
   - Max Einträge: `9999`
4. F8 zum Ausführen
5. Falls Popup "Benutzerspezifische Einstellungen": Enter drücken
6. `sap_read_table` für sichtbare Zeilen
7. **Cursor-Pagination:** Letzter sichtbarer Tabellenname → neuer VON-Wert
8. F3 zurück, neuen VON-Wert setzen, F8 erneut
9. Wiederholen bis keine neuen Tabellen

**CSS-Selektoren (SE16 mit DD02V):**
```
#M0\:46\:\:\:1\:34  →  TABNAME von
#M0\:46\:\:\:1\:59  →  TABNAME bis
#M0\:46\:\:\:2\:34  →  DDLANGUAGE von
#M0\:46\:\:\:4\:34  →  TABCLASS von
#M0\:46\:\:\:7\:34  →  Max Einträge
```

**Wichtig:**
- SAP verwendet `*` als Wildcard (kein Regex!)
- SE16 hat kein OFFSET, nur LIMIT → Cursor-basierte Pagination nötig
- TABCLASS=TRANSP filtert auf echte Datenbanktabellen
- TABCLASS=INTTAB sind nur Strukturen (zur Laufzeit)

---

### Workflow 2: Tabellen-Metadaten extrahieren (SE11)

**Ziel:** Feldstruktur einer einzelnen Tabelle extrahieren

**Vorgehen:**
1. `sap_transaction` mit `tcode="SE11"`
2. Tabellenname eingeben (z.B. `/US4G/ADDR_CHGTY`)
3. Button "Anzeigen" klicken (`#M0\:46\:\:\:12\:0`)
4. `browser_snapshot` für Grid-Daten (Feld, Key, Datenelement, Datentyp, Länge, DezStellen, Kurzbeschreibung)
5. Tabellenbeschreibung aus Feld "Kurzbeschreibung" oben
6. F3 zurück für nächste Tabelle

**Hinweis:** Dieser Ansatz ist LANGSAM (~10s pro Tabelle). Für Batch-Extraktion besser Workflow 3 verwenden.

**Include-Strukturen:** SE11 zeigt `.INCLUDE` Zeilen mit dem eingebetteten Strukturnamen. Diese können separat aufgelöst werden durch Doppelklick oder erneute SE11-Abfrage.

---

### Workflow 3: Batch-Extraktion Tabellenfelder (SE16 + DD03L) [EMPFOHLEN]

**Ziel:** Alle Felder vieler Tabellen in einem Durchlauf extrahieren

**Vorgehen:**
1. `sap_transaction` mit `tcode="SE16"`
2. Tabellenname `DD03L` eingeben und Enter
3. Filter setzen:
   - TABNAME (von): `/US4G/*` (oder gewünschter Filter)
   - AS4LOCAL (von): `A` (nur aktive Versionen)
   - Max Einträge: `9999`
4. F8 zum Ausführen
5. `sap_read_table` mit Cursor-Pagination

**Ergebnis enthält:** TABNAME, FIELDNAME, POSITION, KEYFLAG, ROLLNAME, DATATYPE, LENG, DECIMALS, etc.

**Zusätzliche Daten:**
- `DD02T` für Tabellenbeschreibungen (TABNAME, DDTEXT)
- `DD04T` für Datenelement-Texte (ROLLNAME, DDTEXT)

---

### Workflow 4: Transaktionscodes finden (SE16 + TSTCT)

**Ziel:** Transaktionscodes und deren Beschreibungen finden

**Vorgehen:**
1. `sap_transaction` mit `tcode="SE16"`
2. Tabellenname `TSTCT` eingeben
3. Filter: SPRSL = `D`, TCODE = `pattern*`
4. F8 zum Ausführen

---

### Workflow 5: Funktionsbausteine finden (SE16 + TFDIR)

**Ziel:** Funktionsbausteine eines Patterns finden

**Vorgehen:**
1. `sap_transaction` mit `tcode="SE16"`
2. Tabellenname `TFDIR` eingeben
3. Filter: FUNCNAME = `BAPI_ISU*` (oder gewünschtes Pattern)
4. F8 zum Ausführen

---

### Allgemeine Tipps für Sub-Agents

1. **Sequentiell arbeiten:** Nur ein SAP-Fenster verfügbar
2. **Inkrementell speichern:** Nach jeder Tabelle/Batch speichern
3. **Fortschritt tracken:** Bei Abbruch Wiederaufnahme ermöglichen
4. **Cursor-Pagination:** Letzter sichtbarer Wert = nächster VON-Wert
5. **Popups behandeln:** "Benutzerspezifische Einstellungen" mit Enter schließen
6. **Status prüfen:** `sap_read_status_bar` nach kritischen Aktionen
