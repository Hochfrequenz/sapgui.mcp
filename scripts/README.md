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
python scripts/consolidate_catalog.py
```

This reads all `*_results.json` files and creates `transactions.json`.

### Step 3: Add Inline Results (if needed)

If some SE16 queries returned results inline instead of to files, edit `add_inline_results.py` to include them, then run:

```bash
python scripts/add_inline_results.py
```

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
