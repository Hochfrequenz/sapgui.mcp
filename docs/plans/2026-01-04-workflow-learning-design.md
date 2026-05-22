# Workflow Learning Design

## Problem

Repetitive SAP-Aufgaben (z.B. 100 Business Partner anlegen) verbrauchen schnell den Kontext. Jeder Tool-Call und dessen Ergebnis bleibt im Kontext, bis dieser erschöpft ist.

**Beispielrechnung ohne Optimierung:**

- 100 Business Partner erstellen
- Pro BP: ~10 Tool-Calls (transaction, fill_form, keyboard, status_bar, etc.)
- Pro Tool-Call: ~500 Tokens (Name, Parameter, Ergebnis)
- Gesamt: 100 x 10 x 500 = **500.000 Tokens**

Das ueberschreitet typische Kontextlimits (128k-200k) bei weitem.

## Entscheidungsfindung

### Evaluierte Optionen

**Option A: Client-seitige Subagents**

- Claude Code's Task-Tool spawnt isolierte Subagents
- Pro: Einfach zu implementieren
- Contra: Nur Claude Code, nicht Claude Desktop/ChatGPT/Gemini

**Option B: Scripted Workflows (RPA-Stil)**

- Deterministische Schritte ohne LLM-Beteiligung
- Pro: Maximale Kontexteinsparung, kein LLM-Kosten pro Iteration
- Contra: Keine Flexibilitaet, bei SAP-Aenderungen bricht alles ab, "dann gleich RPA"

**Option C: Server-Side Agent Loops (gewaehlt)**

- MCP Server fuehrt eigene Agent-Loops aus via `ctx.sample()`
- Pro: Funktioniert mit ALLEN Clients, LLM-Flexibilitaet bleibt
- Pro: Massive Kontexteinsparung (Client sieht nur 1 Call -> 1 Result)
- Contra: Abhaengig von Client-Sampling-Support

### Annahmen (Stand Januar 2026)

1. **MCP Sampling ist weit verbreitet** - Die November 2025 Spec hat Sampling mit Tools
   eingefuehrt. Wir nehmen an, dass Claude Desktop, ChatGPT Desktop und andere
   Clients dies unterstuetzen oder bald unterstuetzen werden.

2. **LLM-Flexibilitaet ist wichtiger als Determinismus** - SAP-Screens koennen
   variieren (Sprache, Customizing, Popups). Ein LLM kann darauf reagieren,
   ein starres Script nicht.

3. **Kontexteinsparung ist kritisch** - Ohne Einsparung sind Bulk-Operationen
   praktisch nicht moeglich. 500k Tokens pro 100 Items ist nicht akzeptabel.

4. **Lernphase ist akzeptabel** - 2-3 manuelle Iterationen zum Lernen sind OK,
   wenn danach 97+ Iterationen automatisiert laufen.

### Fallback bei fehlendem Sampling-Support

Falls ein Client kein Sampling unterstuetzt, funktioniert `workflow_run` nicht.
Der User muss dann manuell iterieren (alter Modus). Die Tool-Beschreibung
macht klar, dass Sampling erforderlich ist.

## Design

### Server-Side Agent Loops mit ctx.sample()

Anstatt Client-seitige Subagents zu nutzen, fuehrt der MCP Server eigene Agent-Loops
aus. Dies nutzt FastMCP's `ctx.sample()` Feature (seit v2.14.1, MCP Spec November 2025).

**Vorteile:**

- Funktioniert mit **jedem MCP Client** (Claude Desktop, ChatGPT, Gemini)
- Client-Kontext sieht nur: 1 Tool-Call -> 1 Ergebnis
- LLM-Flexibilitaet bleibt erhalten (kein starres Script)
- Massive Kontexteinsparung: ~500k -> ~2k Tokens

**Ablauf:**

```python
@mcp.tool
async def workflow_run(
    name: str,
    items: list[dict],
    ctx: Context
) -> WorkflowRunResult:
    workflow = load_workflow(name)
    results = []

    for i, item in enumerate(items):
        await ctx.report_progress(progress=i, total=len(items))

        # Server-side agent loop - nutzt Client's LLM via Sampling
        result = await ctx.sample(
            messages=f"{workflow.prompt}\n\nData: {item}",
            tools=[sap_fill_form, sap_press_key, sap_read_status_bar, ...],
        )
        results.append(parse_result(result.text))

    return WorkflowRunResult(...)
```

**Lernphase:**

- Erste 2-3 Iterationen: Client-Agent fuehrt manuell aus, lernt
- Agent ruft `workflow_save` auf um optimierten Prompt zu speichern
- Danach: `workflow_run` nutzt gespeicherten Prompt server-seitig

**Kontextverbrauch:**

- Ohne workflow_run: 100 Items x 10 Tool-Calls x 500 Tokens = ~500k Tokens
- Mit workflow_run: 1 Tool-Call + 1 Ergebnis = ~2k Tokens

### Workflow-Persistenz

**Zwei Quellen:**

```
sapguimcp/
├── workflows/              <- Bundled (im Package, von Devs reviewed)
│   ├── bp-creation.md
│   └── material-master.md

~/.sap-mcp/workflows/       <- User (lokal gelernt)
    └── bp-creation.md      <- Ueberschreibt bundled bei gleichem Namen
```

**Merge-Logik:**

1. Lade bundled Workflows aus Package
2. Lade User-Workflows aus lokalem Verzeichnis
3. User überschreibt Bundled bei gleichem Namen (für Anpassungen)

**Dateiformat:** Markdown mit YAML-Frontmatter

```markdown
---
description: Business Partner anlegen (Person)
author: kleink
applicable_when: Personen als Business Partner anlegen (natuerliche Personen)
not_applicable_when: Organisationen/Firmen anlegen - dafuer F6 statt F5
---

Oeffne Transaktion BP. Druecke F5 fuer neue Person...
```

### Workflow-Sharing

**Trennung von Feedback-Typen:**

| Tool                       | Zweck                            | GitHub Label          |
| -------------------------- | -------------------------------- | --------------------- |
| `log_feedback` (existiert) | MCP-Bugs, Feature-Requests       | `feedback`            |
| `workflow_submit` (neu)    | Funktionierende Workflows teilen | `workflow-submission` |

**Flow:**

```
User lernt Workflow (automatisch nach 2-3 Iterationen)
        |
        v
Lokal gespeichert (~/.sap-mcp/workflows/)
        |
        v
User: "Das funktioniert gut, teile es" -> workflow_submit -> GitHub Issue
        |
        v
Kollegen sehen Issue, koennen Workflow uebernehmen
        |
        v
Devs reviewen -> Aufnahme in bundled Workflows -> naechster Release
```

**Neuer User-Flow:**

- Tag 1: `workflow_list` zeigt bundled "bp-creation" -> sofort nutzbar
- Spaeter: User passt an -> lokale Kopie ueberschreibt
- Noch spaeter: `workflow_submit` teilt Verbesserung

## Datenmodell

```python
from pydantic import BaseModel, Field


class Workflow(BaseModel):
    """A learned, optimized workflow prompt for repetitive SAP tasks."""

    name: str = Field(
        description="Unique identifier for the workflow, e.g. 'bp-creation'"
    )
    description: str = Field(
        description="Short description of what the workflow does, "
        "e.g. 'Business Partner anlegen (Person)'"
    )
    author: str = Field(
        description="SAP username of the person who created/refined this workflow, "
        "e.g. 'kleink'"
    )
    prompt: str = Field(
        description="The optimized prompt containing step-by-step instructions "
        "and learnings from previous executions"
    )
    applicable_when: str = Field(
        description="Conditions under which this workflow should be used, "
        "e.g. 'Personen als Business Partner anlegen (natuerliche Personen)'"
    )
    not_applicable_when: str | None = Field(
        default=None,
        description="Conditions under which this workflow should NOT be used, "
        "e.g. 'Organisationen/Firmen anlegen - dafuer F6 statt F5'"
    )

    @classmethod
    def from_markdown(cls, name: str, content: str) -> "Workflow":
        """Parse a workflow from markdown with YAML frontmatter."""
        import yaml
        _, frontmatter, prompt = content.split("---", 2)
        meta = yaml.safe_load(frontmatter)
        return cls(name=name, prompt=prompt.strip(), **meta)

    def to_markdown(self) -> str:
        """Serialize workflow to markdown with YAML frontmatter."""
        lines = [
            "---",
            f"description: {self.description}",
            f"author: {self.author}",
            f"applicable_when: {self.applicable_when}",
        ]
        if self.not_applicable_when:
            lines.append(f"not_applicable_when: {self.not_applicable_when}")
        lines.append("---")
        lines.append("")
        lines.append(self.prompt)
        return "\n".join(lines)
```

## Tools

| Tool              | Beschreibung                                        |
| ----------------- | --------------------------------------------------- |
| `workflow_list`   | Listet alle verfuegbaren Workflows (bundled + user) |
| `workflow_run`    | Fuehrt einen Workflow mit Subagent-Pattern aus      |
| `workflow_save`   | Speichert gelernten Workflow lokal                  |
| `workflow_submit` | Teilt Workflow via GitHub Issue                     |
| `workflow_delete` | Entfernt lokalen Workflow (bundled bleiben)         |

## Browser-Multiplexing

### Aktueller Stand

Der MCP-Server arbeitet mit einem einzelnen Browser und einem Tab. Alle Workflow-Iterationen laufen sequentiell.

### Zukuenftige Erweiterung

SAP Web GUI unterstuetzt bis zu 6 parallele Sessions (via `/o` Prefix). Das Design ist darauf vorbereitet:

```
Heute:      [Tab 1] -> Item 1 -> Item 2 -> Item 3 -> ... (sequentiell)

Spaeter:    [Tab 1] -> Item 1 -> Item 7  -> Item 13 -> ...
            [Tab 2] -> Item 2 -> Item 8  -> Item 14 -> ...
            [Tab 3] -> Item 3 -> Item 9  -> Item 15 -> ...
            [Tab 4] -> Item 4 -> Item 10 -> Item 16 -> ...
            [Tab 5] -> Item 5 -> Item 11 -> Item 17 -> ...
            [Tab 6] -> Item 6 -> Item 12 -> Item 18 -> ...
```

### Vorbereitung im Design

- `workflow_run` akzeptiert optional `parallel: int = 1` Parameter
- Subagents sind bereits isoliert und koennen parallel spawnen
- Progress Reporting funktioniert auch bei paralleler Ausfuehrung
- `WorkflowRunResult` aggregiert Ergebnisse unabhaengig von Ausfuehrungsreihenfolge

**Aktuell nicht implementiert** - aber das Design blockiert eine spaetere Erweiterung nicht.

## Steuerung und Erkennung

### Proaktive Nutzung

Der Agent erkennt repetitive Aufgaben anhand von Schluesselwoertern und nutzt das Subagent-Pattern automatisch. Der User muss nicht wissen dass es Subagents gibt.

**Tool-Beschreibung als Trigger:**

```python
@mcp.tool(
    description=(
        "Execute a workflow for repetitive SAP tasks using subagents. "
        "Use this when the user requests bulk operations like "
        "'create 100...', 'for each entry...', 'repeat for all...'. "
        "Preserves main context by running iterations in isolated subagents."
    )
)
async def workflow_run(...):
```

### Lernphase vs. Ausfuehrungsphase

Der Agent hat explizite Kontrolle:

- Nach 2-3 erfolgreichen Iterationen entscheidet der Agent: "Genug gelernt"
- Ruft `workflow_save` auf um den optimierten Prompt zu speichern
- Nutzt danach `workflow_run` fuer den Rest

Wenn Iteration 2 fehlschlaegt, kann der Agent weiter explorieren statt automatisch zu wechseln.

### Workflow-Submit als Nudge

Nach erfolgreicher Ausfuehrung schlaegt der Agent vor:

> "98/100 erfolgreich. Dieser Workflow koennte anderen helfen - soll ich ihn mit dem Team teilen?"

User entscheidet explizit, wird aber sanft angestupst.

## Fehlerbehandlung

### Continue on Error

`workflow_run` laeuft durch alle Items und sammelt Fehler:

```python
class WorkflowError(BaseModel):
    input_summary: str = Field(
        description="Identifying info of the failed item, e.g. 'Max Mustermann, Berlin'"
    )
    error: str = Field(
        description="What went wrong, e.g. 'Pflichtfeld PLZ leer'"
    )


class WorkflowRunResult(BaseModel):
    total: int = Field(description="Total items to process, e.g. 100")
    succeeded: int = Field(description="Successfully completed, e.g. 95")
    failed: int = Field(description="Failed items, e.g. 5")
    succeeded_items: list[str] = Field(
        description="Short confirmations, e.g. ['BP 12345: Max Mustermann']"
    )
    errors: list[WorkflowError]
```

### Progress Reporting

`workflow_run` meldet Fortschritt via FastMCP Context:

```python
from fastmcp import Context

@mcp.tool
async def workflow_run(
    name: str,
    items: list[dict],
    ctx: Context
) -> WorkflowRunResult:
    total = len(items)
    for i, item in enumerate(items):
        await ctx.report_progress(progress=i, total=total)
        # Subagent ausfuehren...
    await ctx.report_progress(progress=total, total=total)
```

Der Client sieht: "23/100 verarbeitet..." in Echtzeit.

### Intelligentes Retry durch Agent

Das Ziel ist die Aufgabe perfekt zu loesen, nicht nur zu berichten:

```
workflow_run(100 items)
    -> 95 OK, 5 failed
Agent: "5 fehlgeschlagen, versuche nochmal..."
workflow_run(5 items)
    -> 4 OK, 1 failed (gleiches Item, gleicher Fehler)
Agent: "1 Item scheitert wiederholt, frage User..."
```

Kein kompliziertes Retry im Tool - der Agent nutzt sein Urteilsvermoegen.
