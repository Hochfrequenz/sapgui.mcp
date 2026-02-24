# Design: SM30 Finish + SPRO Search Tool

**Date:** 2026-02-24
**Status:** Draft

## Motivation

Functional consultants in S/4HANA spend significant time navigating SAP's IMG (Implementation Guide) via SPRO to find and review configuration. The IMG tree has thousands of nodes nested 5–10 levels deep, making it one of SAP's most complex UIs. Most IMG activities ultimately open an SM30 table maintenance view.

This design covers two complementary tools:

1. **SM30** — Already implemented on `feat/sm30-tool`, needs merge with main and quality fixes
2. **SPRO Search** — New tool that uses the IMG's built-in search to find customizing activities by keyword

Together they enable a workflow: _"Find where X is configured"_ (SPRO Search) → _"Show me the current config"_ (SM30 Lookup).

## Tool 1: SM30 — Table Maintenance View (Finish Existing)

### Status

Code exists on `feat/sm30-tool` (3 commits, 7 behind main). Implementation follows the established pattern (models, parser, tool, tests). Needs the same quality fixes applied to SM37/SLG1/ST22/SE09:

### Quality Fixes Required

1. **Session threading:** Replace `sap_transaction_impl` with `navigate_transaction(page, "SM30")` from `sap_page_helpers.py`
2. **Strict typing:** Replace `page: Any` with `Page`, field locators with `Locator`
3. **Lang constants:** Ensure SM30 constants use public naming (`SM30_*`, not `_SM30_*`) and `bilingual_pattern()` for regex selectors
4. **Output file pattern:** Only write file on `result.success`
5. **Merge conflicts:** Resolve conflicts from 7 commits behind main (lang.py, models/**init**.py, etc.)

### No Design Changes

The SM30 tool design from the [general-purpose tools design](2026-02-22-general-purpose-tools-design.md) remains unchanged:

- Read-only display mode
- Dynamic column parsing from ARIA grid
- `SM30ViewResult` with `view_type: Literal["flat", "unsupported"]`
- SM34 redirect detection
- `dict[str, str]` for row values (no type coercion)

## Tool 2: SPRO Search — IMG Activity Finder (New)

### Tool

- `sap_spro_search(query: str)` — Search the IMG for customizing activities matching a keyword. Returns activity names, IMG paths, and linked transaction codes.

### Parameters

- `query: str` — Search keyword (e.g., "country", "tax", "pricing")
- `session: str | None` — Session ID for multi-session support
- `agent_id: str | None` — Agent identifier for binding check
- `output_file: str | None` — Write results to file if many matches

### Result Models

```python
class SPROActivity(BaseModel):
    activity_name: str  # e.g., "Define Countries"
    img_path: str       # e.g., "SAP Customizing > Enterprise Structure > Definition > ..."
    transaction_code: str  # e.g., "SM30" or "OY01" (the linked tcode)
    description: str    # Activity description if available

class SPROSearchResult(ToolResult):
    activities: list[SPROActivity]
    query: str
    activity_count: int
    retrieved_at: AwareDatetime
```

### Navigation Flow

1. Navigate to SPRO (`/nSPRO`)
2. Click "SAP Reference IMG" button to enter the IMG tree
3. Use Find function (F5 or Ctrl+F) to open search dialog
4. Enter search keyword
5. Parse search results
6. Return structured data

### Key Challenges

- **Unknown ARIA structure:** We have no SPRO snapshots yet. Exploration tests must be written first to capture the search UI and results format.
- **Search results format:** The IMG search may return results as a tree (filtered view) or as a flat list. The ARIA structure will determine the parser design.
- **DE/EN labels:** SPRO has bilingual labels like all SAP transactions. Need to discover the actual label text from snapshots.
- **IMG path extraction:** The hierarchical path (breadcrumb) may or may not be available in the search results. If not, we may need to expand result nodes to read their context.
- **No-results handling:** Need to detect "no matches found" state.

### MCP Annotations

```python
ToolAnnotations(readOnlyHint=True, openWorldHint=False)
```

### Implementation Risk

SPRO Search is **exploration-first**: we cannot finalize the parser design until we capture real ARIA snapshots. The implementation plan must include an exploration phase before parser development.

## Implementation Order

1. **SM30 first** (known work, ~1 session):
    - Merge main into `feat/sm30-tool`
    - Apply quality fixes
    - Run reviewer, implement findings
    - Push, squash merge

2. **SPRO Search second** (exploration + implementation, ~2 sessions):
    - Session 1: Exploration tests, capture snapshots, analyze ARIA structure
    - Session 2: Models, parser, tool, tests

## Branch Strategy

- SM30: Continue on existing `feat/sm30-tool` branch
- SPRO Search: New branch `feat/spro-search-tool` after SM30 is merged
