# Workflow Learning Design

## Problem

Repetitive SAP-Aufgaben (z.B. 100 Business Partner anlegen) verbrauchen schnell den Kontext. Jeder Tool-Call und dessen Ergebnis bleibt im Kontext, bis dieser erschöpft ist.

## Lösungsansatz

Zweistufiges System:
1. **Subagent-Pattern** für flexible, kontextschonende Ausführung
2. **Workflow-Persistenz** für Wiederverwendung und Teilen

## Design

### Workflow-Ausführung mit Subagents

**Lernphase (Iteration 1-3):**
- Hauptagent spawnt Subagent mit Task-Beschreibung
- Subagent führt aus, gibt detailliertes Feedback
- Hauptagent extrahiert Learnings und verdichtet sie zu einem optimierten Workflow-Prompt

**Ausführungsphase (Iteration 4+):**
- Subagent bekommt optimierten Prompt + Daten
- Gibt nur knappes Ergebnis: "BP 12345 erstellt" / "Fehler: ..."
- Hauptkontext bleibt schlank

**Kontextverbrauch:**
- Lernphase: ~3 detaillierte Rückmeldungen
- Ausführungsphase: ~1 Zeile pro Iteration
- Statt 100x volle Tool-Logs nur 3 + 97 Kurzzeilen

### Workflow-Persistenz

**Zwei Quellen:**

```
sapwebguimcp/
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

| Tool | Zweck | GitHub Label |
|------|-------|--------------|
| `log_feedback` (existiert) | MCP-Bugs, Feature-Requests | `feedback` |
| `workflow_submit` (neu) | Funktionierende Workflows teilen | `workflow-submission` |

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

| Tool | Beschreibung |
|------|--------------|
| `workflow_list` | Listet alle verfuegbaren Workflows (bundled + user) |
| `workflow_run` | Fuehrt einen Workflow mit Subagent-Pattern aus |
| `workflow_save` | Speichert gelernten Workflow lokal |
| `workflow_submit` | Teilt Workflow via GitHub Issue |
| `workflow_delete` | Entfernt lokalen Workflow (bundled bleiben) |

## MCP Resources

| URI | Beschreibung |
|-----|--------------|
| `workflow://list` | Liste aller Workflows mit Metadaten |
| `workflow://{name}` | Vollstaendiger Workflow-Prompt |

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
