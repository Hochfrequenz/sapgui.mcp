# Design: sapwebgui.mcp — Token-Effizienz & Robuste Datenextraktion

**Datum:** 2026-03-18
**Repo:** https://github.com/Hochfrequenz/sapwebgui.mcp
**Typ:** Konzeptionelles Design-Dokument
**Scope:** Optimierung bestehender Tools + gezielte Erweiterungen

## Kontext

Der MCP-Server von Hochfrequenz ermöglicht SAP-Automatisierung via Claude Desktop/Claude Code. Die Codebasis ist bereits ausgereift: strukturierte Pydantic-Rückgaben, dedizierte Tools für SE11/SE16/SE24/SE37/SE93, Prompts/Rezepte, Multi-Session-Support.

Dieses Design adressiert zwei zusammenhängende Schwächen:

1. **Token-Verbrauch**: Der Agent braucht zu viele Tool-Calls und bekommt zu viel Payload pro Call
2. **Scroll-Robustheit**: Das WebGUI-Backend liest nur sichtbare DOM-Zeilen (~7-13 bei ALV-Grids)

## Designprinzip

Bestehende Tools zuerst optimieren, bevor Neues gebaut wird. Die drei Maßnahmen sind unabhängig voneinander implementierbar.

---

## Maßnahme 1: Tool-Descriptions, Knowledge & Defaults optimieren

### 1.1 Tool-Descriptions verschärfen

Die LLM-facing Descriptions der Tools bekommen Guidance zur Sparsamkeit.

**`sap_read_table`** — aktueller Anfang der Description (gekürzt, Original enthält zusätzlich Session-Parameter-Doku):
```
"Read rows from an ALV grid or table on the current screen. [...]"
```
Ergänzen:
```
"Use max_rows=10 for a quick preview. Only request full data when the user
explicitly needs all rows. Omit include_cells unless you need to click
cells afterward."
```

**`sap_get_screen_text`** — aktueller Anfang der Description (gekürzt):
```
"Get all readable text from the current SAP screen. [...]"
```
Ergänzen:
```
"Avoid calling this after sap_transaction — the TransactionResult already
contains page_title. Only call when you need field labels or button texts
for an unknown screen."
```

**`sap_get_form_fields`** — aktuell:
```
"Discover fillable form fields on the current SAP screen."
```
Ergänzen:
```
"Skip this if you already know the field labels from a prompt/recipe or
prior experience. Use sap_fill_form directly with label-based keys."
```

**`sap_discover_buttons`** — die aktuelle Description enthält bereits "Prefer keyboard shortcuts when available - they're faster." Die Empfehlung hier ist, dies prominenter zu machen und das konkrete Tool zu nennen:
```
Ergänzung: "Use sap_get_shortcuts to discover available shortcuts before
resorting to button clicks."
```

**`sap_get_capabilities`** — Description ergänzen:
```
"Call once per session, not per task. Cache the result mentally."
```

### 1.2 `sap_knowledge.md` erweitern

Neue Sektion einfügen nach "## MCP-Tools are Faster than manual evaluation".

> **Hinweis:** Die bestehende Sektion "### ALV Grid Pagination (Feature Request)" unter "## Common Patterns" sollte aktualisiert werden, sobald Maßnahme 2 implementiert ist — sie beschreibt das gleiche Pattern als Feature Request, das dann umgesetzt wäre.

```markdown
## Working Efficiently — Minimize Tool Calls

### The 3-Call Rule
For simple data lookups, aim for 3 or fewer tool calls:
1. `sap_se16_query` (or dedicated tool) — get the data
2. Done. No need for sap_get_screen_text, sap_read_table,
   or sap_discover_fields if a dedicated tool exists.

### Avoid Redundant Exploration
- Do NOT call `sap_get_screen_text` after `sap_transaction`
  just to "see what's on screen" — the transaction result
  already tells you the page title and success status.
- Do NOT call `sap_discover_fields` before `sap_fill_form`
  if you already know the field labels from a recipe or
  the user's request. `sap_fill_form` matches by label text.
- Do NOT call `sap_discover_buttons` before `sap_keyboard`
  — SAP shortcuts are standardized (F8=Execute, Ctrl+S=Save,
  F3=Back). Check `sap_get_shortcuts` only for non-standard screens.

### Prefer Dedicated Tools
These tools combine multiple steps internally:
- `sap_se16_query` = transaction + filter + execute + read
  (replaces 4-6 manual tool calls)
- `sap_se11_lookup` = structured metadata without navigation
- `sap_se24_lookup` / `sap_se37_lookup` = class/FM info in one call

### When to Use Generic vs. Dedicated Tools
- **SE16 data?** → `sap_se16_query` (NOT sap_transaction + sap_fill_form + ...)
- **Table structure?** → `sap_se11_lookup` (NOT sap_transaction("SE11") + ...)
- **Unknown transaction?** → Then use `sap_transaction` + generic tools
```

### 1.3 Parameter-Defaults anpassen

| Parameter | Aktuell | Neu | Begründung |
|---|---|---|---|
| `sap_read_table.max_rows` | 100 | 30 | Weniger Tokens per Default; Agent kann bei Bedarf erhöhen |
| Cell-Metadata in `TableData` | Immer inkludiert | Nur wenn `include_cells=True` (default `False`) | Größter Payload-Treiber pro Zeile — wird nur zum Klicken gebraucht |

**Code-Änderung für `include_cells`:**

Datei: `src/sapwebguimcp/tools/sap_tools.py`, Funktion `sap_read_table`

```python
async def sap_read_table(
    start_row: int = 1,
    end_row: int | None = None,
    max_rows: int = 30,            # geändert von 100
    include_cells: bool = False,   # NEU
    session: str | None = None,
    agent_id: str | None = None,
) -> TableData:
```

**Betroffene Schichten:** Der neue Parameter `include_cells` muss durch alle Schichten propagiert werden:

1. `src/sapwebguimcp/tools/sap_tools.py` — Tool-Funktion (neuer Parameter)
2. `src/sapwebguimcp/backend/protocol.py` — `SapUiReader.read_table` Signatur erweitern
3. `src/sapwebguimcp/backend/webgui/backend.py` — WebGUI-Implementierung
4. `src/sapwebguimcp/backend/desktop/` — Desktop-Implementierung (durchreichen)

Post-Processing im Tool-Layer (nach Backend-Call, vor Rückgabe):

```python
if not include_cells:
    for row in result.rows:
        row.cells = None
```

Alternativ kann das Stripping im Tool-Layer statt im Backend erfolgen — das vermeidet Änderungen am Protocol und beiden Backend-Implementierungen. Der Tool-Layer ist die dünnere Änderung.

### 1.4 Testbarkeit

| Änderung | Offline-testbar | Wie |
|---|---|---|
| Description-Texte | Ja | Textänderung, CI prüft Formatting + Spelling |
| `sap_knowledge.md` | Ja | `codespell`, Prettier |
| `max_rows` Default | Ja | Unit-Test auf Funktions-Defaults |
| `include_cells` | Ja | Mock-Backend: `read_table(include_cells=False)` → assert `cells is None` |

---

## Maßnahme 2: WebGUI Scroll-Extraktion (ALV Pagination)

### Problem

`sap_read_table` im WebGUI-Backend liest nur im DOM sichtbare Zeilen (~7-13 bei ALV-Grids). Das Desktop-Backend hat kein Scroll-Problem, da COM-basierter Zugriff direkt auf beliebige Zeilen zugreifen kann (nicht DOM-limitiert). `sap_se16_query` hat eine eigene PageDown-Pagination (Funktion `_collect_rows_with_pagination` in `se16_tools.py`). Aber das generische `sap_read_table` hat im WebGUI kein Scrolling.

### Lösung

Die PageDown-Pagination aus `se16_tools.py` in eine gemeinsame Hilfsfunktion extrahieren.

### Neue Datei: `src/sapwebguimcp/backend/webgui/alv_pagination.py`

> **Hinweis zur Platzierung:** Die bestehenden Dateien in `parsers/` sind transaktionsspezifisch (se16_parser.py, sm37_parser.py etc.). Ein generischer Pagination-Helper passt besser direkt neben `backend.py`.

```python
async def alv_collect_all_rows(
    page,
    extract_js: str,
    max_rows: int = 500,
) -> list[TableRow]:
    """
    Collect all rows from an ALV grid by paginating with PageDown.

    Algorithm (already validated in se16_tools.py):
    1. Focus grid: page.locator("[role='grid']").first.click()
    2. Read visible rows via extract_table_data.js
    3. Press PageDown
    4. Wait ~1s for lazy loading
    5. Read next page
    6. Deduplicate via first column key (proven pattern from se16_tools.py, see #136)
    7. Detect end: first-row key unchanged after PageDown → stop
    8. Stuck counter: 3 consecutive empty pages → stop
    9. Return all collected rows, capped at max_rows
    """
```

### Integration in `sap_read_table`

```python
async def sap_read_table(
    start_row: int = 1,
    end_row: int | None = None,
    max_rows: int = 30,
    include_cells: bool = False,
    read_all: bool = False,         # NEU
    session: str | None = None,
    agent_id: str | None = None,
) -> TableData:
```

Wenn `read_all=True`: nutze `alv_collect_all_rows()` statt nur sichtbare Rows. `max_rows` bleibt als Sicherheitsnetz aktiv.

### Tool-Description-Ergänzung

```
"Use read_all=True to paginate through the entire ALV grid (~7 rows/sec).
Only use this when the user needs ALL data. For a quick check, the default
(visible rows only) is sufficient."
```

### Fallback-Verhalten

- Kein `[role='grid']` im DOM → Fallback auf sichtbare Rows (wie bisher)
- `read_all=True` beim Desktop-Backend → wird transparent durchgereicht; das Desktop-Backend greift via COM direkt auf beliebige Zeilen zu und braucht kein Scrolling
- Stuck-Detection verhindert Endlosschleifen

### Testbarkeit

| Aspekt | Offline-testbar | Wie |
|---|---|---|
| Deduplizierungslogik | Ja | Unit-Test mit Mock-Seitendaten: 2 Pages mit Overlap → korrekte Deduplizierung |
| Stuck-Detection | Ja | Unit-Test: 3x gleiche erste Zeile → Abbruch |
| End-Detection | Ja | Unit-Test: first-row key unverändert nach PageDown → Abbruch |
| `max_rows`-Cap | Ja | Unit-Test: 500 Rows gesammelt, max_rows=100 → 100 zurück |
| PageDown + DOM-Reload | Nein | Integration-Test gegen echtes SAP WebGUI |
| `read_all=True` Routing | Ja | Mock-Backend: assert `alv_collect_all_rows` wird aufgerufen |

Offline-Abdeckung: ~60%. Die PageDown-Mechanik selbst ist bereits in Produktion validiert (SE16).

---

## Maßnahme 3: Composite-Tool `sap_quick_report`

### Problem

Der häufigste Flow — Transaktion öffnen, Filter setzen, ausführen, Tabelle lesen — braucht 4-6 einzelne Tool-Calls:

```
1. sap_transaction("SM37")
2. sap_get_form_fields()              ← oft unnötig
3. sap_fill_form({"Benutzer": "*"})
4. sap_keyboard("F8")
5. sap_read_table(max_rows=30)
6. sap_read_status_bar()              ← oft unnötig
```

Jeder Call kostet Tokens für Request, Response und LLM-Reasoning. Bei 6 Calls: ~3.000-5.000 Tokens Orchestrierungs-Overhead.

### Lösung

Neues Tool `sap_quick_report` in `src/sapwebguimcp/tools/quick_report_tools.py`:

```python
@mcp.tool(
    description=(
        "Execute a transaction, fill selection screen fields, press Execute (F8), "
        "and return the resulting table data — all in one call.\n\n"
        "This replaces the common pattern of: sap_transaction → sap_fill_form → "
        "sap_keyboard(F8) → sap_read_table.\n\n"
        "Use this for standard SAP report/list transactions with a selection screen "
        "(SM37, VA05, ME2M, MB51, FBL1N, etc.).\n\n"
        "Do NOT use for:\n"
        "- SE16 (use sap_se16_query instead)\n"
        "- Transactions without selection screens (e.g., BP, VA01)\n"
        "- Complex multi-step workflows"
    )
)
async def sap_quick_report(
    tcode: str,
    fields: dict[str, str] | None = None,
    max_rows: int = 30,
    read_all: bool = False,
    session: str | None = None,
    agent_id: str | None = None,
) -> QuickReportResult:
```

### Rückgabe-Modell

```python
class QuickReportResult(ToolResult):
    """Result from sap_quick_report tool."""

    tcode: str = Field(description="Transaction code executed")
    page_title: str = Field(default="", description="Screen title after execution")
    status_bar_type: StatusBarType = Field(default="none",
        description="Status bar type after F8: S/E/W/I/none")
    status_bar_message: str = Field(default="",
        description="Status bar text after F8")
    table: TableData | None = Field(default=None,
        description="Table data if a table was found after execution")
    error_screen: str | None = Field(default=None,
        description="Screen text if no table was found (e.g., error or unexpected screen)")
```

### Interner Ablauf

Das Composite-Tool ruft **Backend-Methoden direkt** auf (nicht die MCP-Tool-Funktionen), analog zum bestehenden Pattern in `se16_tools.py`. Das vermeidet doppeltes MCP-Logging und ist effizienter.

```
1. backend.enter_transaction(tcode, reset_first=True)
   → Sauberer Zustand, kein State-Bleeding
2. if fields: backend.fill_form(fields)
   → Nur wenn Filter angegeben
3. backend.press_key("F8")
   → Standard-Execute
4. backend.wait_for_ready()
   → Warten bis SAP fertig ist
5. backend.read_status_bar()
   → Bei type="E": abbrechen, error_screen mit Screen-Text befüllen
6. backend.read_table(max_rows=max_rows, read_all=read_all)
   → Tabellendaten; cells werden im Tool-Layer gestrippt
7. Alles in QuickReportResult zusammenfassen
```

`reset_first=True` ist intern fest verdrahtet — bei einem One-Shot-Tool will man immer sauberen Zustand.

`include_cells=False` ist intern fest verdrahtet — wer nach dem Report einzelne Zellen klicken will, nutzt die Einzeltools.

### Dateistruktur

```
src/sapwebguimcp/tools/
  quick_report_tools.py          ← NEU
src/sapwebguimcp/models/
  sap_results.py                 ← QuickReportResult hinzufügen
unittests/
  test_quick_report.py           ← NEU (Unit)
unittests/webgui/
  test_quick_report_integration.py  ← NEU (Integration, skips ohne SAP)
```

### Token-Einsparung

| Szenario | Heute (Einzeltools) | Mit `sap_quick_report` |
|---|---|---|
| Tool-Calls | 4-6 | 1 |
| LLM-Reasoning zwischen Calls | 4-6x "was kommt als nächstes" | 0 |
| Geschätzter Token-Overhead (Orchestrierung) | ~3.000-5.000 | ~500 |
| Fehlerquelle State-Bleeding | Möglich | Eliminiert (reset_first) |

### Testbarkeit

| Aspekt | Offline-testbar | Wie |
|---|---|---|
| `QuickReportResult` Modell | Ja | Pydantic-Validierung analog `test_models.py` |
| Orchestrierungsreihenfolge | Ja | Mock-Backend: assert Call-Reihenfolge `transaction` → `fill_form` → `keyboard` → `read_table` |
| Error-Handling (StatusBar "E") | Ja | Mock: simuliere Error-StatusBar → `table is None`, `error_screen` befüllt |
| Fehlende Tabelle nach F8 | Ja | Mock: `read_table` gibt leere `TableData` → `error_screen` mit Screen-Text |
| End-to-End SM37 | Nein | Integration-Test mit echtem SAP |

Offline-Abdeckung: ~80%.

---

## Implementierungsreihenfolge

| Schritt | Maßnahme | Abhängigkeiten | Aufwand |
|---|---|---|---|
| 1 | Maßnahme 1: Descriptions + Knowledge + Defaults | Keine | Klein (1-2h) |
| 2 | Maßnahme 2: `alv_collect_all_rows` extrahieren | Keine | Mittel (halber Tag) |
| 3 | Maßnahme 2: `read_all` Parameter integrieren | Schritt 2 | Klein (1h) |
| 4 | Maßnahme 3: `QuickReportResult` Modell | Keine | Klein (30min) |
| 5 | Maßnahme 3: `sap_quick_report` Tool | Schritt 3 + 4 | Mittel (halber Tag) |
| 6 | Tests für alles | Schritte 1-5 | Mittel (halber Tag) |

Schritte 1 und 4 können parallel bearbeitet werden. Schritt 1 ist sofort commitbar und liefert den schnellsten ROI.

## Risiken

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| PageDown funktioniert nicht bei allen ALV-Grid-Varianten | Mittel | Fallback auf sichtbare Rows; `se16_tools.py` validiert das Pattern bereits |
| `sap_quick_report` deckt Sonderfälle nicht ab (Popups, Multi-Step-Selections) | Hoch | Klarer Scope in Description: nur einfache Report-Transaktionen. Einzeltools bleiben verfügbar |
| `max_rows=30` Default ist zu niedrig für manche User | Niedrig | Agent kann auf Anfrage erhöhen; Description erklärt das |
| Bestehende Prompts/Rezepte referenzieren alte Defaults | Niedrig | Grep nach `max_rows` in Prompts, ggf. anpassen |
| `max_rows`-Default-Änderung ist Behavior Change | Niedrig | Neue Parameter (`include_cells`, `read_all`) sind additive, non-breaking. `max_rows` 100→30 ist ein Behavior Change — sollte in Release Notes dokumentiert und ggf. als Minor-Version-Bump behandelt werden |
