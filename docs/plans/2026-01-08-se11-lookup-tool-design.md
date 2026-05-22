# SE11 Lookup Tool Design

## Ziel

Ein MCP-Tool zum schnellen Auslesen von Tabellen- und Struktur-Metadaten aus SE11 (ABAP Dictionary). Ein Tool-Call pro Objekt oder Liste von Objekten - kein Orchestrieren mehrerer bestehender Tools.

## API

### Tool-Signatur

```python
from mcp.types import ToolAnnotations

@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True,
        openWorldHint=False,
    ),
    description=(
        "Look up table or structure metadata from SE11 (ABAP Dictionary). "
        "Returns field names, data types, lengths, and descriptions. "
        "Supports single name or list of names. Always queries live from SAP."
    ),
)
async def sap_se11_lookup(
    names: str | list[str],
    object_type: Literal["table", "structure"],
) -> SE11Result:
    ...
```

### Pydantic Models

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

ObjectType = Literal["table", "structure"]

class SE11Field(BaseModel):
    """A single field/column in a table or structure."""
    name: str = Field(description="Field name (e.g., 'MATNR')")
    datatype: str = Field(description="Data type (e.g., 'CHAR', 'NUMC', 'DATS')")
    length: int | None = Field(description="Length (None if not applicable)")
    decimals: int | None = Field(description="Decimal places (None if not applicable)")
    description: str = Field(description="Short text (e.g., 'Material Number')")
    is_key: bool = Field(description="Is this a key field?")

class SE11Entry(BaseModel):
    """Successful metadata lookup for a table or structure."""
    name: str = Field(description="Table/structure name")
    description: str = Field(description="Short description of table/structure")
    object_type: ObjectType = Field(description="'table' or 'structure'")
    fields: list[SE11Field] = Field(description="All fields")
    retrieved_at: datetime = Field(description="Timestamp of retrieval")

class SE11Error(BaseModel):
    """Failed metadata lookup."""
    name: str = Field(description="Requested name")
    object_type: ObjectType = Field(description="Requested type")
    error: str = Field(description="Error message (e.g., 'Table not found')")
    retrieved_at: datetime = Field(description="Timestamp of attempt")

class SE11Result(BaseModel):
    """Result of SE11 lookup - may contain both successes and failures."""
    entries: list[SE11Entry] = Field(description="Successful lookups")
    errors: list[SE11Error] = Field(description="Failed lookups")
```

## Implementierungs-Flow

```
┌─────────────────────────────────────────────────────────────┐
│  sap_se11_lookup(names=["MARA", "MARC"], object_type="table")│
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  1. sap_transaction("SE11")                                 │
└─────────────────────────────────────────────────────────────┘
                            │
         ┌──────────────────┴─── für jeden Namen ───┐
         ▼                                          │
┌─────────────────────────────────────────────────┐ │
│  2. Name ins Textfeld eingeben                  │ │
│     - Tabelle: Radio "Datenbanktabelle"         │ │
│     - Struktur: Radio "Struktur"                │ │
└─────────────────────────────────────────────────┘ │
                            │                       │
                            ▼                       │
┌─────────────────────────────────────────────────┐ │
│  3. F7 (Anzeigen)                               │ │
└─────────────────────────────────────────────────┘ │
                            │                       │
                            ▼                       │
┌─────────────────────────────────────────────────┐ │
│  4. Status Bar prüfen                           │ │
│     - Fehler? → SE11Error erstellen             │ │
│     - OK? → weiter                              │ │
└─────────────────────────────────────────────────┘ │
                            │                       │
                            ▼                       │
┌─────────────────────────────────────────────────┐ │
│  5. browser_snapshot() → YAML parsen            │ │
│     - Kurzbeschreibung extrahieren              │ │
│     - Felder-Tabelle parsen                     │ │
│     - SE11Entry erstellen mit timestamp         │ │
└─────────────────────────────────────────────────┘ │
                            │                       │
                            ▼                       │
┌─────────────────────────────────────────────────┐ │
│  6. F3 (Zurück) → nächster Name                 │ │
└─────────────────────────────────────────────────┘ │
                            │                       │
         └──────────────────┴───────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  7. SE11Result(entries=[...], errors=[...]) zurückgeben     │
└─────────────────────────────────────────────────────────────┘
```

## Dateistruktur

```
src/sapguimcp/
├── models/
│   └── se11_models.py          # SE11Field, SE11Entry, SE11Error, SE11Result
├── tools/
│   └── se11_tools.py           # sap_se11_lookup Tool
└── parsing/
    └── se11_parser.py          # YAML → Pydantic Parsing-Logik

unittests/
├── testdata/html_snapshots/
│   ├── se11_t000_fields_de.html      # Snapshot nach F7 für Tabelle
│   └── se11_bapiret2_fields_de.html  # Snapshot nach F7 für Struktur
├── test_se11_parser.py         # Unit Tests für Parser (offline)
└── test_se11_integration.py    # Integration Tests (live SAP)
```

## Integration Tests

| Test                         | Input                                                | Erwartung                       |
| ---------------------------- | ---------------------------------------------------- | ------------------------------- |
| `test_se11_single_table`     | `names="T000", type="table"`                         | 1 Entry mit Feldern MANDT, etc. |
| `test_se11_single_structure` | `names="BAPIRET2", type="structure"`                 | 1 Entry mit TYPE, MESSAGE, etc. |
| `test_se11_table_list`       | `names=["T000", "T001"], type="table"`               | 2 Entries                       |
| `test_se11_structure_list`   | `names=["BAPIRET2", "BAPI_MTYPE"], type="structure"` | 2 Entries                       |
| `test_se11_table_not_found`  | `names="DOESNOTEXIST", type="table"`                 | 1 Error                         |
| `test_se11_mixed_results`    | `names=["T000", "DOESNOTEXIST"], type="table"`       | 1 Entry, 1 Error                |

## Implementierungsschritte

1. **Explorativer Test** - YAML-Snapshot von SE11 nach F7 capturen
2. **Models** - `se11_models.py` mit Pydantic Models erstellen
3. **Parser** - `se11_parser.py` basierend auf YAML-Struktur implementieren
4. **Tool** - `se11_tools.py` mit dem MCP-Tool implementieren
5. **Unit Tests** - Parser-Tests mit Snapshots
6. **Integration Tests** - Live-Tests gegen SAP

## Offene Punkte

- YAML-Struktur des SE11-Ergebnisses muss noch analysiert werden (Schritt 1)
- Selector für Tabellen-/Struktur-Namensfeld in SE11 verifizieren
- Selector für Radio Buttons "Datenbanktabelle" vs "Struktur" finden
