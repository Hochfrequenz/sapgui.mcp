# Scripts - DEVELOPMENT USE ONLY

This directory contains **development and maintenance scripts** that are **NOT** part of the runtime MCP server.

```
===========================================================================
WARNING: These scripts are for DEVELOPERS/MAINTAINERS only.
They are NOT shipped with the package and NOT used at runtime.
===========================================================================
```

## Scripts Overview

| Script                    | Purpose                                          | When to Use                                     |
| ------------------------- | ------------------------------------------------ | ----------------------------------------------- |
| `consolidate_catalog.py`  | Build `transactions.json` from SE16 result files | After scraping TSTC with `sap_se16_query`       |
| `add_inline_results.py`   | Add inline SE16 results to catalog               | When SE16 returned results inline (not to file) |
| `recapture-snapshots.ps1` | Recapture HTML test snapshots in DE/EN           | When SAP UI changes or adding new tests         |
| `render_readme_demo.py`   | Render README demo composites + concat file      | Rebuilding the README GIF (see below)           |

## Transaction Catalog Building

The transaction catalog (`src/sapguimcp/data/transactions.json`) is built using these scripts:

### Step 1: Scrape TSTC Table

Use `sap_se16_query` in an SAP session to query the TSTC table with different prefix filters:

```python
# In Claude Code with SAP session active
await sap_se16_query(table="TSTC", filters={"TCODE": "VA*"}, max_hits=500, output_file="va_results.json")
await sap_se16_query(table="TSTC", filters={"TCODE": "MM*"}, max_hits=500, output_file="mm_results.json")
# ... repeat for other prefixes
```

### Step 2: Consolidate Results

```bash
python scripts/consolidate_catalog.py <tool-results-dir>
```

This reads all `mcp-sap-webgui-sap_se16_query-*.txt` result files in the given directory and creates `transactions.json`. It exits non-zero if the directory is missing or contains no result files.

### Step 3: Add Inline Results (if needed)

If some SE16 queries returned results inline instead of to files, edit `add_inline_results.py` to include them, then run:

```bash
python scripts/add_inline_results.py
```

## README Demo GIF

The README GIF is produced from a real agent run by the `readme-demo` skill
(`.claude/skills/readme-demo/SKILL.md`). The skill writes `readme-demo/transcript.md`
and beat-numbered screenshots into `readme-demo/frames/`. To (re)build the composites
and the GIF:

```bash
uv run --locked --group tests python scripts/render_readme_demo.py --workdir readme-demo
ffmpeg -f concat -safe 0 -i readme-demo/composite/concat.txt \
  -vf "fps=10,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
  readme-demo.gif
```

Copy `readme-demo.gif` to `docs/readme-demo.gif` and commit it. The GIF is a
re-timed composite of a real run — real messages, real screenshots; only the
pacing is edited (see the honesty note in
`docs/superpowers/specs/2026-10-06-readme-demo-design.md`).

## Test Snapshot Management

### Recapturing HTML Snapshots

When SAP UI changes or you need fresh test data:

```powershell
.\scripts\recapture-snapshots.ps1
```

This script:

1. Deletes existing HTML snapshots
2. Sets `SAP_LANGUAGE=DE` and runs integration tests
3. Sets `SAP_LANGUAGE=EN` and runs integration tests
4. Restores original language setting

**Requires:** Active SAP session via the MCP server.

## Directory Structure Rationale

```
sapgui.mcp/
├── src/sapguimcp/           # RUNTIME CODE - shipped with package
│   ├── catalog/                # Runtime catalog (loader, search)
│   │   └── scraper.py          # Dev helper, but co-located for imports
│   ├── data/
│   │   └── transactions.json   # Built by scripts, shipped with package
│   └── tools/                  # MCP tools
│
├── scripts/                    # DEVELOPMENT ONLY - NOT shipped
│   ├── consolidate_catalog.py
│   ├── add_inline_results.py
│   └── recapture-snapshots.ps1
│
└── unittests/                  # Tests - NOT shipped
    └── testdata/
        └── html_snapshots/     # Captured by recapture-snapshots.ps1
```

## Why Not in `src/`?

These scripts:

- Are **one-off utilities** for building/maintaining data
- Require **manual intervention** (editing, running with specific parameters)
- Should **NOT be importable** as part of the package
- Are **NOT included** in the built wheel/Docker image

The `scraper.py` module in `src/sapguimcp/catalog/` is an exception - it's co-located because it imports from the catalog models, but it's clearly marked as "DEVELOPMENT USE ONLY" in its docstring.
