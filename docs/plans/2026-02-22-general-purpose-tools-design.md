# Design: General-Purpose SAP Tools (SM30, SM37, SLG1, ST22, SE09/SE10)

**Date:** 2026-02-22
**Status:** Approved (revised after expert review)
**Branches:** One per tool (independent, no cross-dependencies)

## Motivation

Junior-to-mid-level SAP consultants (functional and technical) in S/4 Utilities spend significant time on repetitive tasks: checking configuration tables, monitoring background jobs, reading application logs, analyzing short dumps, and reviewing transport requests. These are general-purpose SAP tools — not IS-U-specific — that benefit any SAP user.

The MCP server already covers ABAP development (SE38/SE37/SE24 edit), data dictionary (SE11), and table queries (SE16). The five tools below fill the remaining gaps for day-to-day consulting work.

## Tool 1: SM30 — Table Maintenance View (Read-Only)

### Tool

- `sap_sm30_lookup(view_name: str)` — Read-only. Opens SM30 in display mode, returns all entries.

> **Note:** SM30 edit was dropped from v1 scope. SM30 views vary wildly (flat tables, subscreens, multi-step dialogs, SM34 cluster maintenance). A generic edit tool is not feasible. Read-only display mode works because even complex views render a readable table in display mode.

### Parameters

- `view_name: str` — The maintenance view or table name (e.g., `V_T005`, `ZTRATE_CONFIG`)
- `session: str | None` — Session ID for multi-session support
- `agent_id: str | None` — Agent identifier for binding check
- `output_file: str | None` — Write results to file if large

### Result Models

```python
class SM30Row(BaseModel):
    values: dict[str, str]  # column_name -> value

class SM30ViewResult(ToolResult):
    view_name: str
    description: str
    view_type: Literal["flat", "unsupported"]  # Detect non-flat views and fail gracefully
    columns: list[str]
    rows: list[SM30Row]
    row_count: int
    retrieved_at: AwareDatetime
```

### Key Challenges

- SM30 views vary in structure (3 to 20+ columns) — parser must be dynamic
- DE/EN button labels: "Anzeigen"/"Display"
- Some views require SM34 (extended table maintenance) — detect and return `view_type: "unsupported"` with clear error
- Non-flat/hierarchical views: return `success=False` with explanation rather than garbage data

### MCP Annotations

```python
ToolAnnotations(readOnlyHint=True, openWorldHint=False)
```

### Branch

`feat/sm30-tool`

---

## Tool 2: SM37 — Job Log Monitoring

### Tool

- `sap_sm37_lookup(...)` — Read-only. Lists background jobs with filters, optionally reads job log.

### Parameters

- `job_name: str` — Job name (supports wildcards like `*BILLING*`, default `*`)
- `username: str | None` — Filter by user (default: `*` for all)
- `status: list[Literal["scheduled", "released", "active", "finished", "canceled"]] | None` — Status filter (default: all = leave checkboxes unchanged)
- `from_date: str | None` — Start date filter (YYYY-MM-DD, converted to SAP format)
- `to_date: str | None` — End date filter (YYYY-MM-DD, converted to SAP format)
- `include_log: bool` — Fetch job log for single-job results (default: False). Only works when exactly one job matches.
- `session: str | None` — Session ID
- `agent_id: str | None` — Agent identifier
- `output_file: str | None` — Write results to file if large

### Status Checkbox Mapping

| Status    | DE Label    | EN Label  |
| --------- | ----------- | --------- |
| scheduled | Eingeplant  | Scheduled |
| released  | Freigegeben | Released  |
| active    | Aktiv       | Active    |
| finished  | Beendet     | Finished  |
| canceled  | Abgebrochen | Canceled  |

**"all" = leave all checkboxes unchanged** (SAP default shows all statuses).

### Date Format Handling

ISO dates (YYYY-MM-DD) must be converted based on `SAP_LANGUAGE`:

- DE → `DD.MM.YYYY`
- EN → `MM/DD/YYYY`

A shared `format_sap_date(iso_date: str, language: str) -> str` helper will be added to a common utils module.

### Result Models

```python
class SM37Job(BaseModel):
    job_name: str
    job_number: str
    status: str  # Scheduled/Released/Active/Finished/Canceled
    start_time: str | None
    end_time: str | None
    duration: str | None
    user: str

class SM37JobLog(BaseModel):
    job_name: str
    job_number: str
    log_lines: list[str]

class SM37JobListResult(ToolResult):
    jobs: list[SM37Job]
    job_count: int
    filters_applied: dict[str, str]
    job_log: SM37JobLog | None  # Only populated when include_log=True and single job
    retrieved_at: AwareDatetime
```

### Key Challenges

- SM37 selection screen has checkboxes for status — need to check/uncheck individually
- Job log requires selecting a row + clicking "Jobprotokoll"/"Job Log" button — separate navigation step
- Large result sets: cap at sensible limit or require filters
- Date format conversion needed (new shared helper)

### MCP Annotations

```python
ToolAnnotations(readOnlyHint=True, openWorldHint=False)
```

### Branch

`feat/sm37-tool`

---

## Tool 3: SLG1 — Application Log Reader

### Tool

- `sap_slg1_lookup(...)` — Read-only. Searches and reads application logs.

### Parameters

- `object: str` — Log object (e.g., `EABL`, `EA`, `/SAPTRX/`)
- `subobject: str | None` — Log subobject
- `external_id: str | None` — External identifier (installation number, billing doc, etc.)
- `from_date: str | None` — Start date (YYYY-MM-DD)
- `to_date: str | None` — End date (YYYY-MM-DD)
- `from_time: str | None` — Start time (HH:MM:SS)
- `to_time: str | None` — End time (HH:MM:SS)
- `session: str | None` — Session ID
- `agent_id: str | None` — Agent identifier
- `output_file: str | None` — Write results to file if large

### Tree Expansion Strategy

SLG1 uses an ALV Tree Control (nested `treeitem` roles in ARIA). Strategy:

1. **Expand only 2 levels**: log header → messages. Do NOT expand deeper sub-nodes.
2. **Limit to max 50 logs** in the list view. If more exist, return `log_count` with a truncation note.
3. **Limit to max 200 messages per log**. Add `messages_truncated: bool` to indicate truncation.
4. Expand each log node by clicking the expand icon, wait for AJAX, read messages.

### Result Models

```python
class SLG1Message(BaseModel):
    type: str  # S (Success), W (Warning), E (Error), I (Info), A (Abort)
    text: str
    timestamp: str | None

class SLG1LogEntry(BaseModel):
    log_number: str
    object: str
    subobject: str
    external_id: str
    date: str
    time: str
    user: str
    message_count: int
    messages: list[SLG1Message]
    messages_truncated: bool

class SLG1LogListResult(ToolResult):
    logs: list[SLG1LogEntry]
    log_count: int
    logs_truncated: bool  # True if more logs exist than were fetched
    retrieved_at: AwareDatetime
```

### Key Challenges

- ALV Tree Control in WebGUI is different from ALV grids — tree nodes have expand icons that trigger AJAX
- Must limit expansion depth and counts for performance
- Selection screen has many optional fields — only fill what's provided
- Best use case: debugging specific IS-U processes where object/subobject is known. Tool description should clarify this.

### MCP Annotations

```python
ToolAnnotations(readOnlyHint=True, openWorldHint=False)
```

### Branch

`feat/slg1-tool`

---

## Tool 4: ST22 — Short Dump Analysis

### Tool

- `sap_st22_lookup(...)` — Read-only. Lists short dumps and reads dump details.

### Parameters

- `date: str | None` — Date to search (YYYY-MM-DD, default: today). Uses toolbar buttons for today/yesterday, or date input for specific dates.
- `username: str | None` — Filter by user
- `program: str | None` — Filter by ABAP program name
- `dump_index: int | None` — Select the Nth dump from the list (0-based) to read details. If None, returns list only.
- `session: str | None` — Session ID
- `agent_id: str | None` — Agent identifier
- `output_file: str | None` — Write results to file if large

> **Note:** `dump_id` was replaced with `dump_index`. ST22 dumps are identified by date+time+server+process, not a single ID. The tool lists dumps, then the caller selects by index.

### Result Models

```python
class ST22Dump(BaseModel):
    index: int  # Position in the list (for use with dump_index)
    time: str
    program: str
    include: str | None
    error_type: str  # e.g., RABAX_STATE, MESSAGE_TYPE_X
    short_text: str
    user: str

class ST22DumpDetail(BaseModel):
    error_type: str
    short_text: str
    what_happened: str  # Extracted from "What happened" section
    how_to_correct: str  # Extracted from "How to correct" section
    program: str
    include: str | None
    line: int | None
    call_stack: list[str]
    raw_text: str  # Full dump text (truncated to ~10KB) as fallback

class ST22DumpListResult(ToolResult):
    dumps: list[ST22Dump]
    dump_count: int
    retrieved_at: AwareDatetime

class ST22DumpDetailResult(ToolResult):
    detail: ST22DumpDetail
    retrieved_at: AwareDatetime
```

> **Note:** `variables: dict[str, str]` removed from v1. Variable values in ST22 are deeply nested and spread across multiple pages. The `raw_text` field provides access to all dump content. Variable parsing can be added later.

### Key Challenges

- ST22 navigates by date via toolbar buttons (Today/Yesterday/date selection) — non-standard
- Dump detail is a long scrollable text document — use best-effort section parsing + raw_text fallback
- The ALV list view for dumps is standard and parseable
- Error types are SAP-internal codes — always include human-readable short_text

### MCP Annotations

```python
ToolAnnotations(readOnlyHint=True, openWorldHint=False)
```

### Branch

`feat/st22-tool`

---

## Tool 5: SE09 — Transport Organizer (Read-Only)

### Tool

- `sap_se09_lookup(...)` — Read-only. Lists transport requests with their tasks and optionally objects.

> **Renamed** from `sap_transport_lookup` to follow `sap_{tcode}_lookup` convention.

### Parameters

- `username: str | None` — Filter by owner (default: current user)
- `request_type: Literal["workbench", "customizing", "all"]` — Request type (default: `"all"`)
- `status: Literal["modifiable", "released", "all"]` — Status filter (default: `"modifiable"`)
- `request_number: str | None` — View details of a specific request
- `include_objects: bool` — Expand to object level (default: False). When False, only lists requests and tasks.
- `session: str | None` — Session ID
- `agent_id: str | None` — Agent identifier
- `output_file: str | None` — Write results to file if large

### Result Models

```python
class TransportObject(BaseModel):
    pgmid: str  # R3TR, LIMU, etc.
    object_type: str  # PROG, FUNC, TABL, CLAS, etc.
    object_name: str

class TransportTask(BaseModel):
    task_number: str
    description: str
    owner: str
    status: str  # Modifiable/Released
    objects: list[TransportObject]  # Empty unless include_objects=True

class TransportRequest(BaseModel):
    request_number: str
    description: str
    owner: str
    status: str
    target_system: str
    date: str | None
    tasks: list[TransportTask]

class TransportListResult(ToolResult):
    requests: list[TransportRequest]
    request_count: int
    retrieved_at: AwareDatetime
```

### Key Challenges

- SE09 tree control: Request → Tasks is one level of expansion (feasible). Tasks → Objects is second level (fragile, optional).
- Default `include_objects=False` for reliability — only expand to request+task level
- Tree nodes in WebGUI require clicking expand icons and waiting for AJAX
- Released requests may not show objects (already imported) — handle gracefully

### MCP Annotations

```python
ToolAnnotations(readOnlyHint=True, openWorldHint=False)
```

### Branch

`feat/se09-transport-tool`

---

## Cross-Cutting Concerns

### DE/EN Support

All tools follow the established pattern: detect language from `SAP_LANGUAGE` setting, use appropriate button labels and field selectors.

### Date Format Helper (New)

A shared helper `format_sap_date(iso_date: str, language: str) -> str` will be added for SM37, SLG1, and ST22. Converts ISO dates based on language:

- DE → `DD.MM.YYYY`
- EN → `MM/DD/YYYY`

### Session/Agent/Output File Parameters

All tools include `session`, `agent_id`, and `output_file` parameters per established codebase convention.

### `retrieved_at` Field

All result models include `retrieved_at: AwareDatetime` per established convention.

### Testing Strategy

Each tool follows the existing pattern:

1. **Exploration tests** — Capture YAML snapshots from real SAP screens
2. **Parser unit tests** — Validate parsing against captured snapshots (offline, no SAP needed)
3. **Integration tests** — End-to-end against real SAP (auto-skip if unavailable)

### Error Handling

- Return `ToolResult(success=False, error="...")` on failure
- Navigate back to initial screen on error (don't leave SAP in broken state)
- Handle popups (authorization errors, etc.)

### MCP Tool Annotations

All five tools are read-only: `ToolAnnotations(readOnlyHint=True, openWorldHint=False)`.

### Implementation Order

No dependencies between tools — implement in any order, each on its own branch. Recommended order by value:

1. SM37 (job monitoring) — simplest selection screen, immediate value
2. SM30 (table maintenance) — high value for functional consultants
3. ST22 (short dumps) — high value for technical consultants
4. SLG1 (application logs) — complements SM37
5. SE09 (transports) — nice-to-have, straightforward

## Review History

- **2026-02-22**: Initial design approved
- **2026-02-22**: Revised after expert review (Python/MCP/SAP):
    - Dropped SM30 edit tool (SM30 views too varied for generic editing)
    - Added `view_type` detection for SM30 (flat vs unsupported)
    - Replaced ST22 `dump_id` with `dump_index` (dumps have no single ID)
    - Added `raw_text` fallback for ST22 detail, removed `variables` from v1
    - Added SLG1 tree expansion strategy with depth and count limits
    - Added SM37 date format helper and status checkbox DE/EN mapping
    - Made SE09 object expansion optional (`include_objects=False` default)
    - Added `retrieved_at`, `session`, `agent_id`, `output_file` to all tools
    - Renamed `sap_transport_lookup` → `sap_se09_lookup`
    - Added MCP `ToolAnnotations` to all tools
