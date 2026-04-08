# S/4 Utilities Customizing Roadmap

**Date**: 2026-04-08
**Branch**: `Customizing-Roadmap`

## Problem

Agents that perform S/4 Utilities customizing via the MCP server have no
structural orientation. They don't know what configuration areas exist under
"Branchenkomponente Versorgungsindustrie" in SPRO, how deep the tree goes, or
which branch to navigate to for a given task. This leads to:

- Agents wandering through SPRO blindly
- Wasted tool calls on `sap_spro_search` with vague keywords
- Missed configuration areas because the agent didn't know they exist
- Wrong navigation paths because the hierarchy is unknown

## Solution

A static customizing roadmap exposed as an MCP prompt (index) plus MCP
resources (detail branches). The roadmap covers the complete SPRO tree under
"Branchenkomponente Versorgungsindustrie" — 1,814 nodes across 8 depth levels.

### How it works

1. The agent loads the **index prompt** `s4_utilities_customizing_roadmap`
   which shows the first 2-3 levels of the SPRO tree (~15 main branches with
   their sub-branches).
2. Each main branch references a **detail resource** via
   `sap://spro/versorgungsindustrie/{branch_name}`.
3. The agent calls `ReadMcpResource` to load the full subtree of the relevant
   branch on demand.

This keeps the default context footprint small (~150 lines for the index)
while giving the agent access to the full 1,814-node tree when needed.

## Data Source

The SPRO tree was extracted by:

1. Opening SPRO in SAP WebGUI, navigating to Branchenkomponente
   Versorgungsindustrie
2. Expanding all nodes in the browser (the tree is lazy-loaded)
3. Downloading the full page HTML (14 MB)
4. Parsing the HTML with `parse_spro_html.py` to extract node names and
   hierarchy from the DOM structure (`<tr iidx=... rr=...>` rows with
   `lv="N"` level attributes and `tree#...#TEXT#i` text spans)

The tree structure lives in SAP tables (TNODEIMG/TNODEIMGT) but the mapping
from tree nodes to customizing activities is resolved at runtime by SAP
framework code — it is not stored in any table. The HTML approach bypasses
this limitation entirely.

### Limitations

- No transaction codes (TCODEs) per leaf node — these are only resolved when
  clicking on a node in SPRO. Planned as a follow-up.
- German only (matches the SPRO language setting used for the crawl).
- Static snapshot from 2026-04-08. Must be regenerated manually if the SPRO
  tree changes (SAP upgrades, new notes).

## File Structure

```
src/sapwebguimcp/
├── prompts/
│   └── s4_utilities_customizing_roadmap.md    # Index prompt (level 2+3)
├── data/
│   └── customizing/
│       └── versorgungsindustrie/
│           ├── kundenbeziehungen.md
│           ├── grundeinstellungen.md
│           ├── grundfunktionen.md
│           ├── geraeteverwaltung.md
│           ├── ... (~15 files, one per level-2 branch)
│           └── berechtigungsverwaltung.md
├── resources/
│   ├── __init__.py                            # + re-export
│   └── customizing_resource.py                # Auto-discovery registration
└── server.py                                  # + register call

customizing_roadmap/                           # Build tooling (NOT in package)
├── spro_expanded.html                         # Raw HTML dump (14 MB)
├── parse_spro_html.py                         # Parser/generator script
└── spro_tree_full.txt                         # Intermediate full tree output
```

## Components

### 1. Index Prompt

**File:** `src/sapwebguimcp/prompts/s4_utilities_customizing_roadmap.md`

Standard MCP prompt with YAML frontmatter. Contains:

- Level 2 branches as `##` headings
- Level 3 sub-branches as bullet lists under each heading
- A resource URI reference per level-2 branch

Example:

```markdown
---
description: S/4 Utilities Customizing Roadmap — SPRO-Baum unter Versorgungsindustrie
---

# S/4 Utilities Customizing Roadmap

Branchenkomponente Versorgungsindustrie — SPRO-Baum mit 1.814 Knoten.
Für Details zu einem Bereich: ReadMcpResource("sap://spro/versorgungsindustrie/{name}")

## Kundenbeziehungen
Resource: sap://spro/versorgungsindustrie/kundenbeziehungen
- Allgemeine Funktionen
- Identifikation
- Technische Objekte
- Geschäftspartnerübersicht
- Einstellungen für Objekt-Workbench
- Rechnungskorrektur
- Klärungsfälle
- Vertriebsvertragsmanagement

## Grundeinstellungen/Unternehmensstruktur
Resource: sap://spro/versorgungsindustrie/grundeinstellungen
- Buchungskreise - Sparten zuordnen
- Sparten - Spartentypen zuordnen
- ...
```

Filename must be snake_case with description ≥10 chars to pass existing
prompt validation.

### 2. Detail Files

**Directory:** `src/sapwebguimcp/data/customizing/versorgungsindustrie/`

One `.md` file per level-2 branch. Each file contains the complete subtree
from level 3 downward, using 2-space indentation per depth level.

Example `kundenbeziehungen.md`:

```markdown
Allgemeine Funktionen
  Formulare definieren
  Aktionsprofile definieren
  Kontextmenü definieren
  Generischen Interaction Layer/Object Layer erweitern
  Utilities Business Layer Objekte definieren
Identifikation
  Suchoptionen für Freitextsuche zum Geschäftspartner
  Identifikationsprofile definieren
  Anzahl der durch ein IC-Ereignis ausgelösten Ergebnisse einschränken
  BAdI: Identifikation und Stammdaten
```

No frontmatter, no headings — pure tree structure. The branch name is
encoded in the filename.

Filenames use snake_case derived from the German branch name. The
slugification rule: take the first word, lowercase it, replace Umlauts
(ä→ae, ö→oe, ü→ue, ß→ss), drop slashes and everything after them.

Examples:
- `Kundenbeziehungen` → `kundenbeziehungen.md`
- `Grundeinstellungen/Unternehmensstruktur` → `grundeinstellungen.md`
- `Grundfunktionen` → `grundfunktionen.md`
- `Geräteverwaltung` → `geraeteverwaltung.md`
- `Vertragskontokorrent (Inkasso/Exkasso)` → `vertragskontokorrent.md`

The parser generates a mapping table (branch name → filename) and writes it
as a comment at the top of the index prompt for traceability.

### 3. Resource Registration

**File:** `src/sapwebguimcp/resources/customizing_resource.py`

Auto-discovery pattern matching the existing prompt registration:

```python
"""MCP resources for SPRO customizing tree branches."""

import logging
from pathlib import Path

from fastmcp import FastMCP

__all__ = ["register_customizing_resources"]

logger = logging.getLogger(__name__)


def register_customizing_resources(mcp: FastMCP) -> None:
    """Scan data/customizing/ and register each .md as an MCP resource."""
    data_dir = Path(__file__).parent.parent / "data" / "customizing"

    if not data_dir.exists():
        logger.info("No customizing data directory, skipping resource registration")
        return

    registered = 0
    for area_dir in sorted(data_dir.iterdir()):
        if not area_dir.is_dir():
            continue
        area = area_dir.name

        for md_file in sorted(area_dir.glob("*.md")):
            branch = md_file.stem
            uri = f"sap://spro/{area}/{branch}"
            content = md_file.read_text(encoding="utf-8")

            def make_fn(c: str):
                def fn() -> str:
                    return c
                return fn

            mcp.resource(uri, description=f"SPRO tree: {area}/{branch}")(
                make_fn(content)
            )
            registered += 1

    logger.info("Registered customizing resources", extra={"count": registered})
```

### 4. Glue Code

**`src/sapwebguimcp/resources/__init__.py`** — add import + re-export:

```python
from sapwebguimcp.resources.customizing_resource import register_customizing_resources
```

**`src/sapwebguimcp/server.py`** — add call after existing resource
registrations (~line 321):

```python
register_customizing_resources(mcp)
```

### 5. Parser / Generator

**File:** `customizing_roadmap/parse_spro_html.py` (build tooling, not
packaged)

Extended with two output modes:

1. **`--index`**: Generates the index prompt `.md` (level 2+3 with resource
   URIs and YAML frontmatter)
2. **`--details`**: Generates one `.md` per level-2 branch into the target
   directory

Usage:

```bash
python parse_spro_html.py --index \
    --input spro_expanded.html \
    --output ../sapwebgui.mcp/src/sapwebguimcp/prompts/s4_utilities_customizing_roadmap.md

python parse_spro_html.py --details \
    --input spro_expanded.html \
    --output-dir ../sapwebgui.mcp/src/sapwebguimcp/data/customizing/versorgungsindustrie/
```

The parser reads the HTML, extracts tree rows, identifies the
Versorgungsindustrie subtree, and splits it by level-2 branches. Branch
names are slugified to snake_case for filenames.

## Tests

### Unit test: Resource registration

Verify that `register_customizing_resources` registers resources when files
exist:

- Create a temp directory with `area/branch.md` files
- Patch `Path(__file__).parent.parent / "data" / "customizing"` to the temp dir
- Call `register_customizing_resources(mcp)`
- Assert `mcp.resource` was called with correct URIs

### Unit test: Parser output

Verify that the parser generates correct index and detail files from a
minimal HTML fixture (a small fake SPRO tree HTML with 3 levels).

### Existing tests

The index prompt in `prompts/` must pass the existing prompt validation
tests (snake_case filename, valid YAML frontmatter, description ≥10 chars).
No changes needed to those tests.

## Out of Scope

- TCODE enrichment per leaf node (follow-up: re-crawl with click-through)
- English translation
- Risk classes / agent instructions per branch
- Other SPRO areas (FI, CO, MM, etc.)
- Automatic re-crawl (HTML dump remains a manual step)
- Changes to the existing prompt or resource registration patterns
