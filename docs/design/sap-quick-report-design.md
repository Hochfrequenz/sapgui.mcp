# Design: `sap_quick_report` — Robustes Composite-Tool (v2)

**Datum:** 2026-03-19 (v2, überarbeitet nach Review PR #438)
**Repo:** https://github.com/Hochfrequenz/sapgui.mcp
**PR-Kontext:** https://github.com/Hochfrequenz/sapgui.mcp/pull/426 (Maßnahme 3)
**Typ:** Feature-Design (Machbarkeitsstudie → Implementierungsvorlage)
**Backend-Scope:** WebGUI-only (Phase 1). Runtime-Guard: Tool gibt sofort Fehler bei Desktop-Backend zurück. Desktop-Support (COM-Tree-basierter Classifier) ist Phase 2.

---

## Änderungen gegenüber v1

Basierend auf hf-kleins Review (#438) und kritischer Machbarkeitsanalyse:

| Was | v1 | v2 | Warum |
|---|---|---|---|
| Hint-System | Zwei-Schicht-Merge, `save_hint` Tool, stateful | **Entfernt.** Agent lernt, Tool führt aus | MCP-Server bleibt stateless; Qualitätskontrolle durch Entwickler statt automatisch |
| Popup-Handling | Hint-basiert mit Retry-Logik | **`post_f8_keys` Parameter** — Agent gibt Instruktionen mit | Einfacher, backend-agnostisch, kein Hint-Loader nötig |
| Lernfähigkeit | Agent → `save_hint()` → Datei auf Disk | **Agent → Markdown-Log** → Entwickler reviewed → Tool-Verbesserung via PR | Mensch-in-the-Loop statt unkontrolliertes Lernen |
| `readOnlyHint` | `True` | **`False`** | Transaktionen können Daten ändern/löschen |
| `read_all` | Phase 1 | **Phase 2** | Pagination ist komplex (~100 Zeilen in SE16); `max_rows` reicht |
| Desktop-Backend | "Phase 2" ohne Guard | **Runtime-Guard** mit klarem Fehler | Kein stilles Degradieren |
| Testfälle | Nur Kategorien | **Konkrete TX + Input + Expected** | hf-kleins Kernforderung |
| `dom_roles` in Result | Ja (für Hint-Suggestions) | **Entfernt** | Funktioniert nicht auf Desktop; kein Hint-System mehr |

---

## Kontext & Motivation

Der häufigste SAP-Workflow — Transaktion öffnen, Selektionsbild füllen, F8 drücken, Ergebnis lesen — braucht 4-6 einzelne Tool-Calls mit ~3.000-5.000 Tokens Orchestrierungs-Overhead. `sap_quick_report` bündelt das in 1 Call.

**Designprinzip (hf-klein):** Lieber ein weniger mächtiges Tool das robust ist als eine universelle eierlegende Wollmilchsau.

---

## Design-Entscheidungen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Scope | Robust & fokussiert | TX → Fill → F8 → Read. Nicht mehr, nicht weniger |
| Error-Handling | Steckenbleiben & melden | Agent behält Screen-Kontext, kann mit Einzeltools weiterarbeiten |
| Screen-Typen (Phase 1) | Table, Empty, Error, Unknown | 80%+ Abdeckung; Einzelsatz/Baum in Phase 2 |
| Selektionsbild | Fields + Checkboxes + Radios | Voller `ensure_screen_state`-Support via `bilingual_target`-Pattern |
| Sprachhandling | Labels wie übergeben | Agent ist verantwortlich für korrekte Sprache |
| Architektur | Pipeline mit Screen-Classifier | Testbar, erweiterbar, Classifier wiederverwendbar |
| Lernfähigkeit | Agent lernt → loggt in Markdown → Entwickler reviewed | Stateless Tool, Qualitätskontrolle durch Mensch |
| Backend | WebGUI-only + Runtime-Guard | Desktop (COM) braucht eigenen Classifier (Phase 2) |
| Popup-Handling | `post_f8_keys` Parameter | Agent gibt gelerntes Wissen als Instruktion mit, Tool bleibt stateless |

---

## Tool-Signatur

```python
@mcp.tool(
    description=(
        "Execute a transaction, fill the selection screen (fields, checkboxes, "
        "radio buttons), press Execute (F8), and return the result — all in one call.\n\n"
        "Replaces the pattern: sap_transaction → ensure_screen_state → sap_press_key(F8) "
        "→ sap_read_table.\n\n"
        "Works with any SAP report/list transaction that has a selection screen "
        "(SM37, VA05, ME2M, MB51, FBL1N, Z-transactions, etc.).\n\n"
        "After execution, you remain on the result screen. If the result is "
        "'unknown', use individual tools to investigate further.\n\n"
        "If you already know a transaction shows a popup after F8 (e.g., a variant "
        "selection dialog), pass post_f8_keys=['Enter'] to dismiss it automatically.\n\n"
        "LEARNING: When you encounter screen_type='unknown' and resolve it manually, "
        "append your learning to 'tcode-learnings.md' in the working directory so a "
        "developer can improve the tool. Include: tcode, what appeared after F8, "
        "how you resolved it, and what post_f8_keys to use next time.\n\n"
        "Do NOT use for:\n"
        "- SE16 (use sap_se16_query instead)\n"
        "- SM37 (use sap_sm37_lookup instead — has job log support)\n"
        "- Transactions without selection screens (e.g., BP, VA01)\n"
        "- SE11/SE24/SE37 (use dedicated lookup tools)\n\n"
        "WebGUI-only. Returns an error on desktop backend."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
)
async def sap_quick_report(
    tcode: str,
    fields: dict[str, str] | None = None,
    checkboxes: dict[str, bool] | None = None,
    radios: dict[str, bool] | None = None,
    max_rows: int = 30,
    post_f8_keys: list[str] | None = None,
    output_file: str | None = None,
    session: str | None = None,
    agent_id: str | None = None,
) -> QuickReportResult:
```

**Parameter:**

| Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `tcode` | `str` | required | Transaktionscode (z.B. "VA05", "ME2M") |
| `fields` | `dict[str, str] \| None` | `None` | Textfelder auf dem Selektionsbild, Key = Label-Text |
| `checkboxes` | `dict[str, bool] \| None` | `None` | Checkboxen, Key = Label-Text, Value = gewünscht an/aus |
| `radios` | `dict[str, bool] \| None` | `None` | Radio-Buttons, Key = Label-Text, Value = `True` um zu selektieren |
| `max_rows` | `int` | `30` | Max. Zeilen bei Tabellenergebnis. `Field(ge=1)`. |
| `post_f8_keys` | `list[str] \| None` | `None` | Tasten die nach F8 gedrückt werden sollen (z.B. `["Enter"]` bei bekanntem Popup). Jede Taste wird gedrückt, danach `wait_for_ready()`. Max. 3 Tasten. Keys werden nicht validiert — `press_key()` Error-Handling greift. **Abbruch:** Nach jeder Taste prüft der Classifier ob der Screen schon klassifizierbar ist (TABLE/EMPTY/ERROR). Falls ja, werden restliche Keys übersprungen. |
| `output_file` | `str \| None` | `None` | Pfad für JSON-Export der vollständigen Ergebnisse |
| `session` | `str \| None` | `None` | Session-ID bei Multi-Session |
| `agent_id` | `str \| None` | `None` | Agent-ID bei Multi-Agent |

**Anmerkung zu `fields`:** Der Key ist Label-Text wie er auf dem Selektionsbild steht. `ensure_screen_state` füllt den ersten Match für ein Label. Bei ambiguen Labels (z.B. "Postleitzahl" 2x in TX BP) wird das falsche Feld gefüllt — es gibt aktuell **keine automatische Erkennung** dafür. Für Transaktionen mit bekannten Duplikat-Labels sind die Einzeltools besser geeignet, da der LLM dort per Feedback-Loop den richtigen CSS-Selektor lernen kann. Die Tool-Description listet solche TXen unter "Do NOT use for".

---

## Rückgabe-Modell

```python
class ScreenClassification(StrEnum):
    """Was nach F8 auf dem Bildschirm erschienen ist."""
    TABLE = "table"       # ALV-Grid oder Tabelle erkannt
    EMPTY = "empty"       # Keine Daten gefunden (Status-Bar Info/Warning)
    ERROR = "error"       # Fehler (Status-Bar Typ "E" oder Error-Screen)
    UNKNOWN = "unknown"   # Nicht klassifizierbar — Agent muss mit Einzeltools weiter

class QuickReportResult(ToolResult):
    """Ergebnis von sap_quick_report."""
    tcode: str
    screen_type: ScreenClassification
    page_title: str = ""

    # Status-Bar (Flat-Fields, konsistent mit KeyboardResult-Pattern im Repo)
    status_bar_type: StatusBarType | None = None
    status_bar_message: str | None = None

    # Bei screen_type="table"
    table: TableData | None = None

    # Bei screen_type="error" oder "unknown"
    screen_text: ScreenText | None = None

    # Warnungen (z.B. "Checkbox 'Geplant' not found on screen")
    warnings: list[str] = []
```

**Anmerkung:** `status_bar_type` + `status_bar_message` als Flat-Fields, konsistent mit dem bestehenden `KeyboardResult`-Pattern im Repo.

**`success` vs `screen_type` Semantik:**

| Situation | `success` | `screen_type` | Warum |
|---|---|---|---|
| Desktop-Backend | `False` | — | Infrastruktur-Fehler, Tool konnte nicht starten |
| TX nicht gefunden | `False` | — | Infrastruktur-Fehler |
| Grid gefunden, Tabelle gelesen | `True` | `TABLE` | Erfolg |
| "Keine Daten gefunden" | `True` | `EMPTY` | SAP hat korrekt geantwortet, nur leer |
| Status-Bar Typ "E" nach F8 | `True` | `ERROR` | SAP hat geantwortet, Pipeline lief durch |
| Screen nicht klassifizierbar | `True` | `UNKNOWN` | Pipeline lief durch, Agent muss weitermachen |

**Regel:** `success=False` nur bei Infrastruktur-Fehlern wo die Pipeline nicht komplett durchlief. `success=True` + `screen_type=ERROR/UNKNOWN` wenn SAP geantwortet hat aber das Ergebnis kein Table war.

---

## Pipeline-Architektur

### Ablauf

```
1. Runtime-Guard: _is_desktop_backend()     → bei Desktop: return ERROR sofort
2. backend.enter_transaction(tcode)         → TransactionResult (bei Fehler: return ERROR)
3. ensure_screen_state(...)                 → ScreenStateDiff (Warnings sammeln, weitermachen)
4. backend.press_key("F8")                 → KeyboardResult
5. backend.wait_for_ready()                → explizit warten bis SAP fertig
6. post_f8_keys ausführen (falls gegeben)  → je Taste: press_key + wait_for_ready + classify.
                                              Falls klassifizierbar → restliche Keys überspringen. Max. 3 Tasten.
7. classify_result_screen()                → ScreenClassification
8. parse_by_classification()               → TableData | ScreenText | None
9. build_result()                          → QuickReportResult
```

### Error-Handling pro Schritt

Das Tool bleibt bei Fehlern **auf dem aktuellen Screen stehen** (kein `/n` Reset, kein F3 Back). Der Agent behält den Kontext und kann mit Einzeltools weitermachen.

| Schritt | Fehler | Verhalten |
|---|---|---|
| Runtime-Guard | Desktop-Backend | Return `ERROR`: "sap_quick_report requires WebGUI backend" |
| `enter_transaction` | TX nicht gefunden | Return `ERROR` + status_bar |
| `ensure_screen_state` | Feld/Checkbox nicht gefunden | Warning anhängen, **weitermachen** mit F8 |
| `ensure_screen_state` | Ambigue Labels | Kein automatischer Schutz — füllt ersten Match. Bekannte Duplikat-TXen in Tool-Description ausschließen |
| `press_key("F8")` | SAP-Fehler | Return `ERROR` + status_bar |
| `post_f8_keys` | Taste schlägt fehl | Warning anhängen, **weitermachen** mit Klassifizierung |
| `classify_result_screen` | Kein Grid, kein Error | `UNKNOWN` + screen_text |
| `read_table` | Parse-Fehler oder leeres Grid | `TABLE` mit leerer TableData + warning |

### Screen-Classifier

```python
async def classify_result_screen(
    backend: SapUiBackend,
) -> tuple[ScreenClassification, StatusBarInfo]:
    """
    Analysiert den aktuellen Screen nach F8.

    Prüfreihenfolge:
    1. Status-Bar lesen (immer, als Basis-Info)
    2. Status-Bar Typ "E"? → ERROR
    3. Status-Bar enthält "keine Daten"/"no data"/"keine Werte"/"no entries"? → EMPTY
    4. DOM hat [role='grid']? → TABLE
    5. Sonst → UNKNOWN
    """
```

**Phase 2 Erweiterungen** (nicht in diesem Design):
- `SINGLE_RECORD` — Einzelsatz-Anzeige erkennen (kein Grid, aber strukturierte Felder)
- `TREE` — Baumstruktur erkennen (`[role='tree']` im DOM)
- Desktop-Backend-Support mit COM-Tree-basiertem Classifier

### Dateistruktur

```
src/sapguimcp/
  tools/
    quick_report_tools.py          ← Tool-Funktion + Pipeline + classify_result_screen()
  models/
    quick_report_models.py         ← QuickReportResult, ScreenClassification
```

Flachere Struktur als v1: kein `_hint_loader.py`, kein `tcode_hints.json`, keine Hint-Modelle.

**Registrierung:** `register_quick_report_tools(mcp)` Wrapper-Funktion, konsistent mit `register_sm37_tools(mcp)` und `register_se16_tools(mcp)`.

---

## Lernfähigkeit: Agent → Markdown-Log → Entwickler

### Prinzip

Das Tool ist stateless. Die Lernfähigkeit liegt beim Agent und beim Entwickler:

1. **Tool** gibt bei `UNKNOWN` strukturierte Info zurück (`screen_text`, `status_bar_message`)
2. **Agent** löst das Problem manuell mit Einzeltools
3. **Agent** loggt sein Learning in eine Markdown-Datei
4. **Entwickler** liest den Log und entscheidet:
   - Häufiges Pattern → ins Tool einbauen (z.B. als Default-`post_f8_keys` in der Tool-Description)
   - Nicht automatisierbar → in die Tool-Description als "Do NOT use for" aufnehmen
   - Edge Case → neuer Screen-Typ für Phase 2

### Format der Markdown-Log-Datei

Die Tool-Description instruiert den Agent, Learnings in `tcode-learnings.md` im Working Directory zu loggen:

```markdown
# TCode Learnings

Gesammelte Erkenntnisse aus `sap_quick_report` Aufrufen mit `screen_type: "unknown"`.
Entwickler: Prüfe diese Einträge und übernimm relevante Patterns ins Tool.

---

## FBL1N — Kreditorenposten
- **Datum:** 2026-03-19
- **Screen nach F8:** Popup "Variantenauswahl" mit Buttons [Übernehmen, Abbrechen]
- **Lösung:** Enter drücken, danach TABLE mit Kreditorenposten
- **Für nächsten Call:** `post_f8_keys=["Enter"]`
- **Empfehlung für Tool:** Häufiges Pattern, könnte als Beispiel in die Tool-Description

## ZCUSTOM01 — Kundenreport Werk
- **Datum:** 2026-03-20
- **Screen nach F8:** Dialogfenster "Druckvorschau"
- **Lösung:** F3 (Back), dann Layout-Variante wählen, dann erneut F8
- **Für nächsten Call:** Nicht mit sap_quick_report lösbar, Einzeltools nötig
- **Empfehlung für Tool:** In "Do NOT use for" aufnehmen
```

### Warum Markdown statt JSON/Hint-Dateien

| Aspekt | JSON Hint-System (v1) | Markdown Log (v2) |
|---|---|---|
| Neuer Code im Tool | ~200 Zeilen | 0 Zeilen |
| MCP-Server | Stateful (Disk-I/O) | Stateless |
| Wer entscheidet was ins Tool kommt | Automatisch (fragil) | Entwickler (bewusst) |
| Qualitätskontrolle | Keine | Review durch Mensch |
| Desktop-kompatibel | Nein (DOM-Roles in Hints) | Ja (nur Text) |
| Für den Agent nutzbar | Indirekt (Tool liest Hints) | Direkt (Agent liest eigenen Log) |

### Lernfähiger Ablauf (End-to-End Beispiel)

```
Erstes Mal — unbekannte Transaktion:
──────────────────────────────────────
1. Agent ruft auf: sap_quick_report("FBL1N", fields={"Kreditor": "*"})
2. Pipeline: transaction → fill → F8 → wait_for_ready → classify
3. Classifier: kein Grid, kein Error, kein "keine Daten" → UNKNOWN
4. Tool gibt zurück:
   {
     screen_type: "unknown",
     screen_text: {title: "Variantenauswahl", ...},
     status_bar_message: ""
   }
5. Agent sieht: Popup. Nutzt sap_press_key("Enter") um es zu schließen.
6. Agent liest Ergebnis mit sap_read_table().
7. Agent loggt Learning in tcode-learnings.md

Zweites Mal — Agent hat gelernt:
──────────────────────────────────────
1. Agent ruft auf: sap_quick_report("FBL1N", fields={"Kreditor": "*"},
                                     post_f8_keys=["Enter"])
2. Pipeline: transaction → fill → F8 → wait_for_ready → Enter → wait_for_ready
3. Classifier: Grid gefunden → TABLE
4. Tool gibt zurück: {screen_type: "table", table: TableData(...)}
5. Ein Call statt sechs.

Später — Entwickler reviewed Log:
──────────────────────────────────────
1. Entwickler liest tcode-learnings.md
2. Sieht: FBL1N braucht immer Enter nach F8
3. Entscheidet: Tool-Description um Beispiel erweitern
4. PR mit aktualisierter Description → alle Agents lernen es
```

---

## Logging bei Unknown Screens

```python
logger.warning(
    "Unclassified screen after F8",
    extra={
        "tcode": tcode,
        "page_title": page_title,
        "status_bar_type": status_bar.type,
        "status_bar_message": status_bar.message,
        "has_grid": has_grid,
    },
)
```

---

## Testbarkeit

### Unit-Tests (offline, Mock-Backend)

| Test Case | TX | Input | Mock-Setup | Erwartetes Ergebnis |
|---|---|---|---|---|
| Happy path: Tabelle | VA05 | `fields={"Auftraggeber": "*"}` | `enter_transaction` OK, Snapshot hat `[role='grid']`, `read_table` liefert 3 Rows | `screen_type=TABLE`, 3 Rows |
| Keine Daten | ME2M | `fields={"Werk": "9999"}` | Status-Bar: type="I", message="Keine Daten gefunden" | `screen_type=EMPTY`, kein Table |
| Error: TX nicht gefunden | ZZZZZ | keine | `enter_transaction` → `success=False`, error="TX not found" | `screen_type=ERROR`, error message |
| Error: Desktop-Backend | VA05 | beliebig | `_is_desktop_backend()` → `True` | `success=False`, error="requires WebGUI backend" |
| Feld nicht gefunden | VA05 | `fields={"FakeField": "x"}` | Feld nicht im Snapshot | `warnings` enthält "FakeField not found", F8 trotzdem gedrückt |
| Ambigue Labels (kein Schutz) | — | `fields={"Postleitzahl": "12345"}` | Snapshot hat "Postleitzahl" 2x | `ensure_screen_state` füllt ersten Match — kein Fehler, potenziell falsches Feld. Bekannte TXen via Tool-Description ausschließen |
| Unknown Screen | ZCUSTOM01 | keine | Kein `[role='grid']`, Status-Bar type != "E", kein "keine Daten" | `screen_type=UNKNOWN`, screen_text gesetzt |
| Status-Bar Typ E | ME2M | `fields={"Werk": "XXXX"}` | Status-Bar: type="E", message="Werk XXXX existiert nicht" | `screen_type=ERROR`, status_bar_message gesetzt |
| post_f8_keys ausgeführt | FBL1N | `post_f8_keys=["Enter"]` | Nach F8: Popup-Screen, nach Enter: Grid | `screen_type=TABLE`, press_key("Enter") aufgerufen |
| post_f8_keys max 3 | — | `post_f8_keys=["Enter","Enter","Enter","Enter"]` | — | Nur 3 Tasten ausgeführt, Warning für 4. |
| post_f8_keys leere Liste | VA05 | `post_f8_keys=[]` | Grid nach F8 | Identisch zu `None` — TABLE |
| post_f8_keys löst Popup nicht | FBL1N | `post_f8_keys=["Escape"]` | Popup bleibt nach Escape | `screen_type=UNKNOWN`, Popup-Screen in screen_text |
| post_f8_keys Early-Exit | — | `post_f8_keys=["Enter","F5"]` | Nach Enter: Grid erkannt | TABLE, nur Enter ausgeführt, F5 übersprungen |
| max_rows Validation | VA05 | `max_rows=0` | — | Validierungsfehler (`Field(ge=1)`) |
| Pipeline-Reihenfolge | VA05 | `fields={"X": "Y"}` | Mock-Backend | Assert: enter_transaction → ensure_screen_state → press_key("F8") → wait_for_ready → classify |
| output_file Export | VA05 | `output_file="/tmp/out.json"` | Table-Result | Temp-Datei existiert, JSON valide |

### Integrationstests (Live-SAP)

| Test Case | TX | Input | Erwartetes Ergebnis |
|---|---|---|---|
| VA05 Auftragsübersicht | VA05 | `fields={"Auftraggeber": "*"}` | `screen_type=TABLE`, `table.headers` nicht leer |
| ME2M Bestellungen | ME2M | `fields={"Werk": "<valid_plant>"}` | `screen_type=TABLE` oder `EMPTY` |
| Ungültige Transaktion | ZZZZNOTREAL | keine | `screen_type=ERROR` |
| FBL1N ohne post_f8_keys | FBL1N | `fields={"Kreditor": "*"}` | `screen_type=UNKNOWN` (Varianten-Popup blockiert) — beweist das Limit |
| FBL1N mit post_f8_keys | FBL1N | `fields={"Kreditor": "*"}, post_f8_keys=["Enter"]` | `screen_type=TABLE` — beweist dass post_f8_keys funktioniert |
| MB51 Materialbelege | MB51 | `fields={"Material": "<valid_mat>"}` | `screen_type=TABLE` oder `EMPTY` |
| Result-Model Roundtrip | VA05 | beliebig | `QuickReportResult.model_dump_json()` → `QuickReportResult.model_validate_json()` |

**Geschätzte Offline-Abdeckung: ~90%** (höher als v1, da kein Hint-System zu mocken)

---

## Implementierungsreihenfolge

| Schritt | Was | Abhängigkeiten | Aufwand |
|---|---|---|---|
| 1 | `ScreenClassification` + `QuickReportResult` in `models/quick_report_models.py` | Keine | Klein |
| 2 | `classify_result_screen()` in `tools/quick_report_tools.py` | Schritt 1 | Klein |
| 3 | `sap_quick_report` Pipeline inkl. Runtime-Guard + `post_f8_keys` | Schritte 1-2 | Mittel |
| 4 | Tool-Registrierung in `server.py` | Schritt 3 | Klein |
| 5 | Tests (Unit + Integration-Stubs) | Schritte 1-4 | Mittel |

Schritte 1 und 2 können parallel bearbeitet werden.

**Gesamtaufwand Phase 1:** ~150-200 Zeilen Produktionscode, ~300 Zeilen Tests

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| Screen-Classifier erkennt Grid nicht (DOM-Varianten) | Mittel | Fallback auf `UNKNOWN` + screen_text; Agent kann mit Einzeltools weiter |
| `ensure_screen_state` schlägt bei unbekannten Selektionsbildern fehl | Mittel | Warnings statt Abbruch; F8 wird trotzdem gedrückt. Bei ambiguen Labels: klarer Fehler |
| Agent loggt nicht in tcode-learnings.md | Mittel | Instruktion ist in Tool-Description; kein harter Zwang, aber Best Practice |
| `post_f8_keys` reicht nicht für komplexe Popups | Niedrig | Max 3 Tasten deckt 99% der Fälle; komplexere → Einzeltools |
| Desktop-Backend nicht unterstützt | Phase 1 akzeptiert | Runtime-Guard mit klarem Fehler; Desktop-Support in Phase 2 |

---

## Abgrenzung zu bestehenden Tools

| Tool | Scope | Unterschied zu `sap_quick_report` |
|---|---|---|
| `sap_se16_query` | Nur SE16N | Transaktionsspezifisch, eigene Filter-Logik, eigene Pagination |
| `sap_sm37_lookup` | Nur SM37 | Transaktionsspezifisch, kennt SM37-Felder + Job-Log |
| `sap_transaction` + Einzeltools | Alles | Flexibel aber 4-6 Calls; `sap_quick_report` bündelt den häufigsten Flow |
| `sap_quick_report` | Generisch | Für jede Transaktion mit Selektionsbild → F8 → Ergebnis |

`sap_quick_report` ersetzt NICHT die dedizierten Tools — es ergänzt sie für Transaktionen ohne eigenes Tool.

---

## Phase 2 (separat)

Nicht in diesem Design, aber als Ausblick:
- Desktop-Backend-Support mit COM-Tree-basiertem Classifier
- `SINGLE_RECORD` + `TREE` Screen-Typen
- `read_all` Pagination
- Shipped `post_f8_keys` Defaults in einer Konfigurationsdatei (wenn tcode-learnings.md genug Patterns zeigt)
