# Design: `sap_quick_report` — Robustes Composite-Tool mit lernfähigem Screen-Classifier

**Datum:** 2026-03-18
**Repo:** https://github.com/Hochfrequenz/sapwebgui.mcp
**PR-Kontext:** https://github.com/Hochfrequenz/sapwebgui.mcp/pull/426 (Maßnahme 3)
**Typ:** Feature-Design (Machbarkeitsstudie → Implementierungsvorlage)
**Backend-Scope:** WebGUI-only (Phase 1). Desktop-Backend-Support ist nicht Teil dieses Designs, da der Screen-Classifier auf DOM-Rollen (`[role='grid']` etc.) basiert. Desktop-Backend nutzt COM-basierte Inspektion ohne DOM.

---

## Kontext & Motivation

Der häufigste SAP-Workflow — Transaktion öffnen, Selektionsbild füllen, F8 drücken, Ergebnis lesen — braucht 4-6 einzelne Tool-Calls mit ~3.000-5.000 Tokens Orchestrierungs-Overhead. Ein Composite-Tool könnte das auf 1 Call reduzieren.

**hf-kleins Bedenken (PR #426, Zeilen 259-277):**
> "Man muss sich sehr genau überlegen, wie man z.B. Error Handling macht, was wenn Schritt 3 von 5 failed? Was ist die Erwartung ans Tool? Bleiben wir auf halber Strecke stecken? Gehen wir zurück auf die Startseite? Was ist mit Transaktionalität?"

Dieses Design adressiert diese Bedenken mit einer Pipeline-Architektur, einem erweiterbaren Screen-Classifier und einem lernfähigen Hint-System.

---

## Design-Entscheidungen

| Frage | Entscheidung | Begründung |
|---|---|---|
| Scope | Robust & generisch | Alle Screen-Typen nach F8 werden behandelt, nicht nur ALV-Grids |
| Error-Handling | Steckenbleiben & melden | Agent behält Screen-Kontext, kann mit Einzeltools weiterarbeiten |
| Screen-Typen (Phase 1) | Table, Empty, Error, Unknown | 80%+ Abdeckung; Einzelsatz/Baum in Phase 2 |
| Selektionsbild | Fields + Checkboxes + Radios | Voller `ensure_screen_state`-Support via `bilingual_target`-Pattern |
| Sprachhandling | Labels wie übergeben | Agent ist verantwortlich für korrekte Sprache; generisches Tool kann nicht vorab mappen |
| Architektur | Pipeline mit Screen-Classifier | Testbar, erweiterbar, Classifier wiederverwendbar |
| Lernfähigkeit | Hybrid: Repo-Hints + User-lokale Hints | Shipped Baseline für Standard-TCodes + Agent kann kundenspezifische Hints sammeln |
| Hints ins Repo | Phase 1: README-Doku mit manuellem Export; Phase 2: CLI-Command | Kein neues CLI-Framework in Phase 1 nötig |
| Datenformat | JSON (nicht YAML) | Konsistenz mit bestehenden Data-Files (`transactions.json`, `tables.json` etc.); kein PyYAML als Runtime-Dependency |

---

## Tool-Signatur

```python
@mcp.tool(
    description=(
        "Execute a transaction, fill the selection screen (fields, checkboxes, "
        "radio buttons), press Execute (F8), and return the result — all in one call.\n\n"
        "Replaces the pattern: sap_transaction → ensure_screen_state → sap_keyboard(F8) "
        "→ sap_read_table.\n\n"
        "Works with any SAP report/list transaction that has a selection screen "
        "(SM37, VA05, ME2M, MB51, FBL1N, Z-transactions, etc.).\n\n"
        "After execution, you remain on the result screen. If the result is "
        "'unknown', use individual tools to investigate further.\n\n"
        "Do NOT use for:\n"
        "- SE16 (use sap_se16_query instead)\n"
        "- Transactions without selection screens (e.g., BP, VA01)\n"
        "- SE11/SE24/SE37 (use dedicated lookup tools)"
    ),
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
async def sap_quick_report(
    tcode: str,
    fields: dict[str, str] | None = None,
    checkboxes: dict[str, bool] | None = None,
    radios: dict[str, bool] | None = None,
    max_rows: int = 30,
    read_all: bool = False,
    output_file: str | None = None,
    session: str | None = None,
    agent_id: str | None = None,
) -> QuickReportResult:
```

**Parameter:**

| Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `tcode` | `str` | required | Transaktionscode (z.B. "SM37", "VA05") |
| `fields` | `dict[str, str] \| None` | `None` | Textfelder auf dem Selektionsbild, Key = Label-Text |
| `checkboxes` | `dict[str, bool] \| None` | `None` | Checkboxen, Key = Label-Text, Value = gewünscht an/aus |
| `radios` | `dict[str, bool] \| None` | `None` | Radio-Buttons, Key = Label-Text, Value = `True` um zu selektieren (konsistent mit `bilingual_target`) |
| `max_rows` | `int` | `30` | Max. Zeilen bei Tabellenergebnis |
| `read_all` | `bool` | `False` | Alle Zeilen via Pagination sammeln (langsam) |
| `output_file` | `str \| None` | `None` | Pfad für JSON-Export der vollständigen Ergebnisse (konsistent mit `sap_se16_query`) |
| `session` | `str \| None` | `None` | Session-ID bei Multi-Session |
| `agent_id` | `str \| None` | `None` | Agent-ID bei Multi-Agent |

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

    # Bei screen_type="unknown": Hint-Vorschlag für Lernfähigkeit
    hint_suggestion: TCodeHintSuggestion | None = None

    # Warnungen (z.B. "Checkbox 'Geplant' not found on screen")
    warnings: list[str] = []
```

**Anmerkung:** `status_bar_type` + `status_bar_message` als Flat-Fields, konsistent mit dem bestehenden `KeyboardResult`-Pattern im Repo (das ebenfalls Flat-Fields statt eingebettetem `StatusBarInfo` nutzt).

---

## Pipeline-Architektur

### Ablauf

```
1. load_hints(tcode)                    → TCodeHint | None
2. backend.enter_transaction(tcode)     → TransactionResult (bei Fehler: return ERROR)
3. ensure_screen_state(...)             → ScreenStateDiff (Warnings sammeln, weitermachen)
4. backend.press_key("F8")             → KeyboardResult
5. backend.wait_for_ready()            → explizit warten bis SAP fertig
6. check_known_popups(hint)            → Popup erkannt? → hint.popup_action + wait_for_ready()
7. classify_result_screen()            → ScreenClassification
8. parse_by_classification()           → TableData | ScreenText | None
9. build_result()                      → QuickReportResult (ggf. mit hint_suggestion)
```

### Error-Handling pro Schritt

Das Tool bleibt bei Fehlern **auf dem aktuellen Screen stehen** (kein `/n` Reset, kein F3 Back). Der Agent behält den Kontext und kann mit Einzeltools weitermachen.

| Schritt | Fehler | Verhalten |
|---|---|---|
| `enter_transaction` | TX nicht gefunden | Return `ERROR` + status_bar |
| `ensure_screen_state` | Feld/Checkbox nicht gefunden | Warning anhängen, **weitermachen** mit F8 |
| `press_key("F8")` | Unerwartetes Popup | Hint vorhanden → `popup_action` + `wait_for_ready()` ausführen; kein Hint → `UNKNOWN` + screen_text |
| `classify_result_screen` | Kein Grid, kein Error | `UNKNOWN` + screen_text + hint_suggestion |
| `read_table` | Parse-Fehler oder leeres Grid | `TABLE` mit leerer TableData + warning |

### Screen-Classifier

```python
async def classify_result_screen(
    backend: SapUiBackend,
    hint: TCodeHint | None = None,
) -> tuple[ScreenClassification, StatusBarInfo]:
    """
    Analysiert den aktuellen Screen nach F8.

    Prüfreihenfolge:
    1. Status-Bar lesen (immer, als Basis-Info)
    2. Status-Bar Typ "E"? → ERROR
    3. Status-Bar enthält "keine Daten"/"no data"/"keine Werte"/"no entries"? → EMPTY
    4. DOM hat [role='grid']? → TABLE
    5. Hint sagt was erwartet wird? → Hint-Typ, ABER nur wenn DOM-Check bestätigt
    6. Sonst → UNKNOWN
    """
```

**Wichtig:** Der Hint wird **nicht blind vertraut**. Wenn ein Hint `post_f8: table` sagt aber kein `[role='grid']` im DOM ist, gewinnt die DOM-Realität und das Ergebnis ist `UNKNOWN`.

**Phase 2 Erweiterungen** (nicht in diesem Design):
- `SINGLE_RECORD` — Einzelsatz-Anzeige erkennen (kein Grid, aber strukturierte Felder)
- `TREE` — Baumstruktur erkennen (`[role='tree']` im DOM)

### Popup-Erkennung (Detail)

Die Popup-Erkennung in Schritt 6 funktioniert wie folgt:

1. **Detection:** `backend.get_screen_text()` aufrufen. Wenn `title` oder `main_content` einen `text_pattern` aus dem Hint enthält (Substring-Match, case-insensitive) → Popup erkannt.
2. **Action:** `backend.press_key(hint.popup_action)` ausführen, dann `backend.wait_for_ready()`.
3. **Max 1 Retry:** Falls nach der Action erneut ein Popup erkannt wird (anderes Pattern), wird ein zweites Mal versucht. Danach → `UNKNOWN` mit screen_text.
4. **Kein Hint, aber Popup:** Wenn kein Hint vorhanden ist und der Screen wie ein Dialog aussieht (z.B. `title` enthält typische Popup-Wörter), wird **nicht** automatisch agiert → `UNKNOWN` + screen_text + hint_suggestion.

**`text_pattern` ist immer Substring-Match** (kein Regex). Das ist robuster und vermeidet `re.error` bei fehlerhaften User-Hints.

### Dateistruktur

```
src/sapwebguimcp/
  tools/
    quick_report_tools.py          ← Tool-Funktion + Pipeline + classify_result_screen()
    _hint_loader.py                ← load_hints(), merge Repo + User, save_hint()
  data/
    tcode_hints.json               ← Shipped Baseline (read-only)
  models/
    quick_report_models.py         ← QuickReportResult, ScreenClassification, TCodeHint, PopupHint, TCodeHintSuggestion
```

**Änderung gegenüber v1:** Flachere Struktur, konsistent mit bestehenden Conventions:
- Keine neuen Top-Level-Packages (`classifiers/`, `hints/`)
- Modelle in `models/quick_report_models.py` (analog zu `sm37_models.py`)
- Classifier inline in `quick_report_tools.py` (ist ~30 Zeilen, braucht kein eigenes Package)
- Hint-Loader als privates Modul `_hint_loader.py` in `tools/`
- CLI-Export auf Phase 2 verschoben

---

## Hint-System

### Datenmodell

```python
class PopupHint(BaseModel):
    """Bekanntes Popup das nach F8 erscheinen kann."""
    text_pattern: str          # Substring im Popup-Text (case-insensitive)
    action: str = "Enter"      # Tastendruck um Popup zu schließen

class TCodeHint(BaseModel):
    """Erwartungen an eine Transaktion nach F8."""
    tcode: str
    post_f8: ScreenClassification = ScreenClassification.TABLE
    known_popups: list[PopupHint] = []
    notes: str = ""            # Freitext für Entwickler/Agent

class TCodeHintSuggestion(BaseModel):
    """Vom Tool generierter Vorschlag für einen neuen Hint."""
    tcode: str
    observed_screen_type: str
    status_bar_type: str
    status_bar_message: str
    page_title: str
    dom_roles: list[str]       # Eindeutige ARIA-Rollen im DOM (z.B. ["dialog", "listbox"])
```

### Zwei-Schicht-Merge

```
Schicht 1 (read-only):   src/sapwebguimcp/data/tcode_hints.json    ← shipped im Package
Schicht 2 (read-write):  ~/.sapwebguimcp/tcode_hints.json           ← user-lokal
```

**Merge-Logik:**
- User-Hints überschreiben Repo-Hints per tcode-Key
- Innerhalb eines Hints: `post_f8` und `notes` werden überschrieben (User gewinnt)
- `known_popups` werden zusammengeführt (union), dedupliziert per `text_pattern`-Key. Bei gleichem `text_pattern` gewinnt die User-`action`.

### Shipped Baseline

```json
{
  "SM37": {
    "post_f8": "table",
    "known_popups": [],
    "notes": "Job-Übersicht, immer ALV-Grid"
  },
  "VA05": {
    "post_f8": "table",
    "known_popups": [],
    "notes": "Auftragsübersicht"
  },
  "ME2M": {
    "post_f8": "table",
    "known_popups": [],
    "notes": "Bestellübersicht Material"
  },
  "MB51": {
    "post_f8": "table",
    "known_popups": [],
    "notes": "Materialbelegübersicht"
  },
  "FBL1N": {
    "post_f8": "table",
    "known_popups": [
      {"text_pattern": "Variante", "action": "Enter"}
    ],
    "notes": "Kreditorenposten, fragt manchmal nach Anzeigevariante"
  },
  "FBL3N": {
    "post_f8": "table",
    "known_popups": [
      {"text_pattern": "Variante", "action": "Enter"}
    ],
    "notes": "Sachkontenposten"
  },
  "FBL5N": {
    "post_f8": "table",
    "known_popups": [
      {"text_pattern": "Variante", "action": "Enter"}
    ],
    "notes": "Debitorenposten"
  }
}
```

### Tool zum Speichern von Hints

```python
@mcp.tool(
    description=(
        "Save a TCode hint to the user-local hints file "
        "(~/.sapwebguimcp/tcode_hints.json). "
        "Use this after sap_quick_report returned screen_type='unknown' "
        "and you have identified what the screen was. "
        "The hint will be used automatically on the next call."
    ),
    annotations=ToolAnnotations(readOnlyHint=False, openWorldHint=False),
)
async def sap_save_tcode_hint(
    tcode: str,
    post_f8: str = "table",
    known_popups: list[dict[str, str]] | None = None,
    notes: str = "",
) -> SaveHintResult:
```

### Hints ins Repo bringen (Phase 1: manuell, Phase 2: CLI)

**Phase 1 — Manuell (README-Dokumentation):**

```markdown
## Contributing TCode Hints

When `sap_quick_report` encounters an unknown screen, the agent can save
a hint via `sap_save_tcode_hint`. These hints are stored locally in
`~/.sapwebguimcp/tcode_hints.json`.

To contribute your hints back to the project:

1. Open your local hints file:
   ```bash
   cat ~/.sapwebguimcp/tcode_hints.json
   ```
2. Copy the relevant entries into `src/sapwebguimcp/data/tcode_hints.json`
3. Open a PR with your additions

Alternatively, export only new hints with Python:
   ```bash
   python -c "
   import json
   from pathlib import Path
   repo = json.loads(Path('src/sapwebguimcp/data/tcode_hints.json').read_text())
   user = json.loads(Path.home().joinpath('.sapwebguimcp/tcode_hints.json').read_text())
   new = {k: v for k, v in user.items() if k not in repo}
   print(json.dumps(new, indent=2, ensure_ascii=False))
   "
   ```

Hints for standard SAP transactions (SM37, VA05, etc.) are welcome.
Customer-specific Z-transactions should remain in your local hints file.
```

**Phase 2 — CLI-Command** (separates Design):
- `sapwebguimcp hints export [--new-only]`
- CLI-Framework und Entry-Point werden im Phase-2-Design spezifiziert

---

## Lernfähiger Ablauf (End-to-End Beispiel)

```
Erstes Mal — unbekannte Transaktion:
──────────────────────────────────────
1. Agent ruft auf: sap_quick_report("ZCUSTOM01", fields={"Werk": "1000"})
2. Pipeline: transaction → fill → F8 → wait_for_ready → classify
3. Classifier: kein Grid, kein Error → UNKNOWN
4. Tool gibt zurück:
   {
     screen_type: "unknown",
     screen_text: {title: "Variantenauswahl", buttons: ["Übernehmen", "Abbrechen"]},
     hint_suggestion: {
       tcode: "ZCUSTOM01",
       observed_screen_type: "unknown",
       status_bar_type: "none",
       status_bar_message: "",
       page_title: "Variantenauswahl",
       dom_roles: ["dialog", "listbox"]
     }
   }
5. Agent sieht: Aha, ein Varianten-Popup. Nutzt sap_keyboard("Enter") um es zu schließen.
6. Agent liest Ergebnis mit sap_read_table().
7. Agent speichert: sap_save_tcode_hint("ZCUSTOM01",
     known_popups=[{"text_pattern": "Variante", "action": "Enter"}])

Zweites Mal — Hint greift:
──────────────────────────────────────
1. Agent ruft auf: sap_quick_report("ZCUSTOM01", fields={"Werk": "1000"})
2. Pipeline: transaction → fill → F8 → wait_for_ready
3. Popup erscheint → Hint sagt: "Variante" → Enter → wait_for_ready
4. Classifier: Grid gefunden → TABLE
5. Tool gibt zurück: {screen_type: "table", table: TableData(...)}
6. Ein Call statt sechs.
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
        "dom_roles": dom_roles,       # z.B. ["dialog", "listbox"]
        "has_grid": has_grid,
        "has_tree": has_tree,
    },
)
```

---

## Testbarkeit

| Aspekt | Offline-testbar | Wie |
|---|---|---|
| `QuickReportResult` Modell | Ja | Pydantic-Validierung |
| `ScreenClassification` | Ja | Enum-Tests |
| `classify_result_screen` | Ja | Mock-Backend: simuliere verschiedene DOMs + Status-Bars |
| Hint-Loader + Merge | Ja | Unit-Test: Repo-JSON + User-JSON → merged result, Popup-Deduplizierung |
| Popup-Erkennung | Ja | Mock: Popup-Text matcht Hint → action ausgeführt + wait_for_ready |
| Popup max 1 Retry | Ja | Mock: 2 Popups hintereinander → zweites wird behandelt, drittes → UNKNOWN |
| Pipeline-Reihenfolge | Ja | Mock-Backend: assert Call-Reihenfolge inkl. wait_for_ready-Calls |
| `ensure_screen_state` Integration | Ja | Bereits getestet in sm37_tools.py |
| Error-Handling pro Schritt | Ja | Mock: simuliere Fehler bei jedem Schritt → korrekte Rückgabe |
| `output_file` Export | Ja | Temp-Datei, assert JSON-Inhalt |
| End-to-End mit SAP | Nein | Integration-Test |

**Geschätzte Offline-Abdeckung: ~85%**

---

## Implementierungsreihenfolge

| Schritt | Was | Abhängigkeiten | Aufwand | Phase |
|---|---|---|---|---|
| 1 | `ScreenClassification` + `QuickReportResult` + Hint-Modelle in `models/quick_report_models.py` | Keine | Klein | 1 |
| 2 | Hint-Loader (`tools/_hint_loader.py`: JSON lesen, Zwei-Schicht-Merge) | Schritt 1 | Klein | 1 |
| 3 | `classify_result_screen()` in `tools/quick_report_tools.py` | Schritt 1 | Mittel | 1 |
| 4 | `sap_quick_report` Pipeline | Schritte 1-3 | Mittel | 1 |
| 5 | `sap_save_tcode_hint` Tool | Schritt 2 | Klein | 1 |
| 6 | Shipped `tcode_hints.json` Baseline | Schritt 2 | Klein | 1 |
| 7 | README-Doku für Hint-PR-Workflow | Schritt 6 | Klein | 1 |
| 8 | Tests für alles | Schritte 1-7 | Mittel | 1 |
| 9 | Tool-Registrierung in `server.py` | Schritt 4 | Klein | 1 |
| 10 | CLI `hints export` Command | Schritt 2 | Klein | 2 |
| 11 | Desktop-Backend-Support für Classifier | Schritt 3 | Mittel | 2 |
| 12 | `SINGLE_RECORD` + `TREE` Screen-Typen | Schritt 3 | Mittel | 2 |

Schritte 1, 2, 6 können parallel bearbeitet werden.

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Mitigation |
|---|---|---|
| Screen-Classifier erkennt Grid nicht (DOM-Varianten) | Mittel | Fallback auf `UNKNOWN` + hint_suggestion; Agent kann mit Einzeltools weiter |
| `ensure_screen_state` schlägt bei unbekannten Selektionsbildern fehl | Mittel | Warnings statt Abbruch; F8 wird trotzdem gedrückt |
| Popup-Erkennung per text_pattern zu fragil | Niedrig | Substring-Match (kein Regex) ist robust; Agent kann Hint nachbessern |
| Hint-Merge bei konkurrierenden User-/Repo-Hints | Niedrig | Klare Regel: User überschreibt Repo per tcode-Key; Popups per text_pattern dedupliziert |
| Performance-Overhead durch Hint-Loading | Niedrig | JSON ist klein, wird einmal pro Call geladen, Caching möglich |
| `~/.sapwebguimcp/` existiert nicht | Niedrig | `sap_save_tcode_hint` erstellt Verzeichnis + Datei automatisch |
| Desktop-Backend nicht unterstützt | Phase 1 akzeptiert | Explizit als WebGUI-only dokumentiert; Desktop-Support in Phase 2 |
| Verkettete Popups (Popup → Action → Popup → ...) | Niedrig | Max 1 Retry; danach UNKNOWN. Deckt 99% der Fälle |

---

## Abgrenzung zu bestehenden Tools

| Tool | Scope | Unterschied zu `sap_quick_report` |
|---|---|---|
| `sap_se16_query` | Nur SE16N | Transaktionsspezifisch, eigene Filter-Logik, eigene Pagination |
| `sap_sm37_lookup` | Nur SM37 | Transaktionsspezifisch, kennt SM37-Felder + Job-Log |
| `sap_transaction` + Einzeltools | Alles | Flexibel aber 4-6 Calls; `sap_quick_report` bündelt den häufigsten Flow |
| `sap_quick_report` | Generisch | Für jede Transaktion mit Selektionsbild → F8 → Ergebnis |

`sap_quick_report` ersetzt NICHT die dedizierten Tools — es ergänzt sie für Transaktionen ohne eigenes Tool.
