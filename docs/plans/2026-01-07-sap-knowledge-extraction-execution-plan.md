# SAP Knowledge Extraction - Execution Plan

## Overview

Extract field metadata for remaining SAP tables and transaction codes using **SE11** (ABAP Dictionary).

**Scope:**
- 233 `/US4G/*` tables (field metadata missing)
- 57 `EMMA*` tables (field metadata missing)
- 65 classic IS-U tables (field metadata missing)
- ~50+ transactions to verify via SE93
- **Total: 355 tables + transactions**

**Constraints:**
- Single SAP window (no parallel agents)
- ~15 minute session reliability
- Checkpoint after EVERY table/transaction
- **ALWAYS use keyboard shortcuts (F3, F7, Enter) - NEVER click buttons**
- **Autonomous execution - no user approval required during extraction**

**Why SE11 instead of SE16/DD03L:**
- SE16 on DD03L has lazy-loading pagination issues
- SE11 shows complete field list with descriptions on one screen
- Includes table Kurzbeschreibung (short description)
- More reliable for browser_snapshot extraction

---

## Critical Navigation Rules

### ALWAYS use keyboard shortcuts

| Action | Shortcut | Tool Call |
|--------|----------|-----------|
| Display (SE11) | F7 | `sap_keyboard("F7")` |
| Back | F3 | `sap_keyboard("F3")` |
| Enter/Confirm | Enter | `sap_keyboard("Enter")` |
| Execute/Run | F8 | `sap_keyboard("F8")` |
| Save | Ctrl+S | `sap_keyboard("Ctrl+S")` |

### NEVER do this
- ❌ Click "Execute" button
- ❌ Click "Back" button
- ❌ Use `browser_click` for standard navigation
- ❌ Use `sap_discover_buttons` then click

### Why?
- Keyboard shortcuts are faster and more reliable
- Button selectors can change or be ambiguous
- Shortcuts work consistently across SAP screens

---

## Phase 1: Setup & Verification

### 1.1 Verify existing data
```
Files to check:
- docs/plans/us4g_field_metadata_380_tables.json (existing 380 tables)
- docs/plans/sap_tables_consolidated.json (all table names)
- docs/plans/sap_transactions_consolidated.json (existing transactions)
```

### 1.2 Generate remaining tables list
Create `docs/plans/remaining_tables.json` with:
```json
{
  "us4g_remaining": ["<233 table names>"],
  "emma_remaining": ["<57 table names>"],
  "isu_remaining": ["<~75 table names>"],
  "total": 365
}
```

### 1.3 Create progress tracker
Create `docs/plans/extraction_progress.json`:
```json
{
  "tables": {
    "completed": [],
    "failed": [],
    "current_batch": null
  },
  "transactions": {
    "completed": [],
    "failed": [],
    "current_batch": null
  },
  "last_updated": null
}
```

---

## Phase 2: Table Metadata Extraction (SE11 - ABAP Dictionary)

### 2.1 Pre-session checklist
Before EACH agent session:
1. [ ] SAP logged in (`sap_login`)
2. [ ] Keepalive started (`sap_keepalive_start`)
3. [ ] Progress file read to know where to resume
4. [ ] Parser script available: `docs/plans/parse_se11_snapshot.py`

### 2.2 SE11 Field Display

**Transaction:** SE11 (ABAP Dictionary)
**Mode:** Display (F7)

**Data extracted per table:**
| Field | Source | Description |
|-------|--------|-------------|
| tabname | Input field | Table name |
| description | Kurzbeschreibung | Table short description |
| fieldname | Grid column | Field technical name |
| keyflag | Checkbox | X if key field |
| datatype | Grid column | ABAP data type (CHAR, NUMC, etc.) |
| length | Grid column | Field length |
| decimals | Grid column | Decimal places |
| rollname | Grid column | Data element name |
| field description | Grid column | Field short description |

### 2.3 Optimized SE11 workflow (5 tool calls per table)

```
LOOP for each table in batch:

  STEP 1: Set table name and display (2 calls)
  - sap_set_field(label="Tabellenname, 16-stellig", value="<TABLE_NAME>")
  - sap_keyboard("F7")  // Display - NOT click!

  STEP 2: Capture screen (1 call)
  - snapshot = browser_snapshot()

  STEP 3: Parse and save (1 call)
  - Run: python docs/plans/parse_se11_snapshot.py '<snapshot>' '<TABLE_NAME>'
  - Script parses: table description, all fields with types/lengths/descriptions
  - Script appends to extraction_checkpoint.jsonl
  - Script updates extraction_progress.json

  STEP 4: Back to SE11 initial screen (1 call)
  - sap_keyboard("F3")

  TOTAL: 5 tool calls per table (vs 8+ with SE16 approach)

END LOOP
```

### 2.4 Pydantic-based extraction module

Located at `docs/plans/extraction_models.py`

**Usage:**
```bash
python docs/plans/extraction_models.py add_table '<snapshot_text>' '<table_name>'
```

Or from stdin:
```bash
echo '<snapshot>' | python docs/plans/extraction_models.py add_table - '<table_name>'
```

**Data files (JSON, Pydantic-validated):**
- `extracted_tables.json` - All table records
- `extracted_transactions.json` - All transaction records
- `extraction_progress.json` - Completed/failed tracking

**Check progress:**
```bash
python docs/plans/extraction_models.py summary
```

### 2.5 Session end
- Save final progress
- Log session summary (completed count, failed count)

---

## Phase 3: Transaction Extraction (SE93)

### 3.1 Transaction discovery workflow

**Goal:** For each transaction code, extract:
- Transaction code
- Title/description
- Program name
- Screen number (Dynpro)
- Package
- Transaction type

### 3.2 SE93 extraction steps

```
LOOP for each transaction code to verify:

  STEP 1: Navigate to SE93
  - If first: sap_transaction("SE93")
  - If subsequent: sap_keyboard("F3") then clear field

  STEP 2: Enter transaction code
  - sap_set_field(label="Transaction code", value="<tcode>")
  - sap_keyboard("Enter")  // Display transaction details

  STEP 3: Read screen
  - sap_get_screen_text() or sap_get_form_fields()
  - Extract: Program, Screen, Package, Description
  - If "does not exist": mark as not_found

  STEP 4: Save checkpoint IMMEDIATELY
  - Append to transaction_checkpoint.jsonl
  - Update extraction_progress.json

  STEP 5: Go back for next
  - sap_keyboard("F3")

END LOOP
```

### 3.3 Transactions to verify

**Priority 1: Core IS-U transactions**
```
ES30, ES31, ES32, ES33 - Installation/Anlage
EG30, EG31, EG32 - Device/Geraet
EC30, EC50, EC60 - Tariff/Move-in/Move-out
EA00, EA01 - Billing
EL01 - Order
```

**Priority 2: FI-CA transactions**
```
FPL9, FP01, FP02, FP03 - Account
FPVA, FPM1 - Dunning
```

**Priority 3: Utility transactions**
```
SE11, SE16, SE38, SE93 - Development tools
SM37 - Job monitoring
```

**Priority 4: Market communication (may not exist)**
```
/IDXGC/MM01, /IDXGC/GP01, /IDXGC/MP01
```

---

## Phase 4: Batch Organization

### Table extraction batches

**Tables per batch:** 20 (conservative for 15-min sessions)

#### US4G Batches (233 tables = 12 batches)
| Batch | Count | Tables |
|-------|-------|--------|
| US4G-01 | 20 | 1-20 |
| US4G-02 | 20 | 21-40 |
| US4G-03 | 20 | 41-60 |
| US4G-04 | 20 | 61-80 |
| US4G-05 | 20 | 81-100 |
| US4G-06 | 20 | 101-120 |
| US4G-07 | 20 | 121-140 |
| US4G-08 | 20 | 141-160 |
| US4G-09 | 20 | 161-180 |
| US4G-10 | 20 | 181-200 |
| US4G-11 | 20 | 201-220 |
| US4G-12 | 13 | 221-233 |

#### EMMA Batches (57 tables = 3 batches)
| Batch | Count | Tables |
|-------|-------|--------|
| EMMA-01 | 20 | 1-20 |
| EMMA-02 | 20 | 21-40 |
| EMMA-03 | 17 | 41-57 |

#### ISU Batches (~75 tables = 4 batches)
| Batch | Count | Tables |
|-------|-------|--------|
| ISU-01 | 20 | 1-20 |
| ISU-02 | 20 | 21-40 |
| ISU-03 | 20 | 41-60 |
| ISU-04 | 15 | 61-75 |

### Transaction extraction batches

**Transactions per batch:** 15-20 (faster than tables)

| Batch | Transactions |
|-------|--------------|
| TCODE-01 | ES30-ES33, EG30-EG32, EC30, EC50, EC60, EA00, EA01, EL01 |
| TCODE-02 | FPL9, FP01, FP02, FP03, FPVA, FPM1, SE11, SE16, SE38, SE93, SM37 |
| TCODE-03 | /IDXGC/* and any additional discovered |

---

## Phase 5: Output Format

### Table metadata (extraction_checkpoint.jsonl)
```jsonl
{"tabname": "/US4G/ART_MALO", "description": "Marktlokation Artikel", "extracted_at": "2026-01-07T14:30:00Z", "fields": [{"fieldname": "MANDT", "position": 1, "keyflag": "X", "datatype": "CLNT", "length": 3, "decimals": 0, "rollname": "MANDT", "description": "Mandant"}]}
```

**Key additions vs previous plan:**
- `description`: Table Kurzbeschreibung (from SE11 header)
- `fields[].description`: Field Kurzbeschreibung (from SE11 grid)

### Transaction metadata (transaction_checkpoint.jsonl)
```jsonl
{"tcode": "ES31", "extracted_at": "2026-01-07T15:00:00Z", "status": "exists", "title": "Anlage aendern", "program": "SAPLES30", "dynpro": "110", "package": "EE01"}
{"tcode": "FP02", "extracted_at": "2026-01-07T15:01:00Z", "status": "not_found", "title": null, "program": null}
```

---

## Phase 6: Error Handling

### Common errors and recovery

| Error | Detection | Recovery |
|-------|-----------|----------|
| Session timeout | Page unresponsive | Re-login, resume from progress |
| Table not found | Status bar message | Log to failed, continue |
| No authorization | Status bar message | Log to failed, continue |
| Popup appears | popup in tool response | `sap_dismiss_popup`, retry |
| Slow response | Tool timeout | Retry once, then skip |

### Recovery procedure
```
1. Check sap_session_status()
2. If not logged in: sap_login()
3. sap_keepalive_start()
4. Read extraction_progress.json
5. Resume from last incomplete item
```

---

## Phase 7: Agent Instructions Template

### Table extraction agent prompt (SE11 - AUTONOMOUS)
```
## Task: Extract SAP table metadata - Batch {BATCH_ID}

### AUTONOMOUS EXECUTION - NO USER APPROVAL REQUIRED
This agent runs without user interaction. Continue processing all tables.
On ANY error: log to failed list, continue to next table immediately.

### CRITICAL RULES
- ALWAYS use keyboard shortcuts: F7 (display), F3 (back)
- NEVER click buttons - use sap_keyboard only
- Use browser_snapshot() to capture screen data
- Run parse_se11_snapshot.py script to save checkpoints
- Continue on errors - do not stop for user input

### Setup (run once at start)
1. sap_session_status() - if not logged in: sap_login()
2. sap_keepalive_start(interval_seconds=120)
3. sap_transaction("SE11")
4. Read docs/plans/extraction_progress.json to find resume point

### Tables to process
{LIST_OF_TABLES}

### For EACH table (6 tool calls):
1. sap_set_field(label="Tabellenname, 16-stellig", value="{TABLE}")
2. sap_keyboard("F7")  // Display table structure
3. snapshot = browser_snapshot()  // Capture all field data
4. Write snapshot to: C:\github\sapwebgui.mcp\docs\plans\temp_snapshot.txt
5. Bash: python C:/github/sapwebgui.mcp/docs/plans/extraction_models.py process_snapshot C:/github/sapwebgui.mcp/docs/plans/temp_snapshot.txt
   (Table name extracted from snapshot automatically - no bash path expansion issues)
6. sap_keyboard("F3")  // Back to SE11 initial screen

### Error handling (AUTONOMOUS - NO USER INPUT):
- If table not found: Script logs to failed, continue
- If parse error: Script logs to failed, continue
- If SAP timeout: sap_login(), sap_transaction("SE11"), resume
- If popup: sap_dismiss_popup(), retry once, then skip

### On completion: Report summary of completed/failed counts
```

### Transaction extraction agent prompt (SE93 - AUTONOMOUS)
```
## Task: Extract SAP transaction metadata - Batch {BATCH_ID}

### AUTONOMOUS EXECUTION - NO USER APPROVAL REQUIRED
This agent runs without user interaction. Continue processing all transactions.
On ANY error: log to failed list, continue to next transaction immediately.

### CRITICAL RULES
- ALWAYS use keyboard shortcuts: F3 (back), Enter
- NEVER click buttons - use sap_keyboard only
- Continue on errors - do not stop for user input

### Setup (run once at start)
1. sap_session_status() - if not logged in: sap_login()
2. sap_keepalive_start(interval_seconds=120)
3. sap_transaction("SE93")
4. Read docs/plans/extraction_progress.json to find resume point

### Transactions to verify
{LIST_OF_TCODES}

### For EACH transaction (4 tool calls):
1. sap_set_field(label="Transaction code", value="{TCODE}")
2. sap_keyboard("Enter")  // Display transaction details
3. screen = sap_get_screen_text() - extract program, screen, package, description
4. Append to docs/plans/transaction_checkpoint.jsonl using Bash
5. sap_keyboard("F3")

### Error handling (AUTONOMOUS - NO USER INPUT):
- If "does not exist": Log status="not_found", continue
- If SAP timeout: sap_login(), sap_transaction("SE93"), resume
- If popup: sap_dismiss_popup(), retry once, then skip

### On completion: Report summary of completed/failed counts
```

---

## Phase 8: MCP Resource Creation

After extraction, expose the data as MCP resources so LLMs can query SAP metadata.

### 8.1 Pydantic Models (STRICT TYPING)

Create `src/sapwebguimcp/models/sap_knowledge.py`:

```python
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum


class SAPDataType(str, Enum):
    """SAP ABAP data types."""
    CHAR = "CHAR"      # Character
    NUMC = "NUMC"      # Numeric character
    CLNT = "CLNT"      # Client
    DATS = "DATS"      # Date
    TIMS = "TIMS"      # Time
    DEC = "DEC"        # Packed decimal
    CURR = "CURR"      # Currency
    QUAN = "QUAN"      # Quantity
    INT1 = "INT1"      # 1-byte integer
    INT2 = "INT2"      # 2-byte integer
    INT4 = "INT4"      # 4-byte integer
    FLTP = "FLTP"      # Floating point
    LANG = "LANG"      # Language
    UNIT = "UNIT"      # Unit
    RAW = "RAW"        # Raw bytes
    LCHR = "LCHR"      # Long character
    LRAW = "LRAW"      # Long raw
    STRING = "STRING"  # String
    RAWSTRING = "RAWSTRING"  # Raw string
    SSTRING = "SSTRING"  # Short string
    # Add more as discovered


class TableField(BaseModel):
    """A single field in an SAP table."""
    fieldname: str = Field(..., description="Technical field name")
    position: int = Field(..., ge=1, description="Field position in table")
    keyflag: Literal["X", ""] = Field("", description="X if key field")
    datatype: str = Field(..., description="ABAP data type (CHAR, NUMC, DATS, etc.)")
    length: int = Field(..., ge=0, description="Field length in bytes/characters")
    decimals: int = Field(0, ge=0, description="Decimal places (for DEC/CURR types)")
    rollname: str | None = Field(None, description="Data element name")
    domname: str | None = Field(None, description="Domain name")
    description: str | None = Field(None, description="Field Kurzbeschreibung (from SE11)")


class TableMetadata(BaseModel):
    """Metadata for an SAP database table."""
    tabname: str = Field(..., description="Technical table name")
    description: str | None = Field(None, description="Table Kurzbeschreibung (from SE11)")
    tabclass: Literal["TRANSP", "INTTAB", "CLUSTER", "POOL", "VIEW", "APPEND"] | None = Field(
        None, description="Table class"
    )
    fields: list[TableField] = Field(default_factory=list, description="Table fields")
    key_fields: list[str] = Field(default_factory=list, description="Key field names")

    def model_post_init(self, __context) -> None:
        """Populate key_fields from fields."""
        if not self.key_fields and self.fields:
            self.key_fields = [f.fieldname for f in self.fields if f.keyflag == "X"]


class TransactionStatus(str, Enum):
    """Transaction existence status."""
    EXISTS = "exists"
    NOT_FOUND = "not_found"
    NO_AUTH = "no_authorization"


class TransactionMetadata(BaseModel):
    """Metadata for an SAP transaction code."""
    tcode: str = Field(..., description="Transaction code")
    title: str | None = Field(None, description="Transaction title/description")
    program: str | None = Field(None, description="ABAP program name")
    dynpro: str | None = Field(None, description="Screen number")
    package: str | None = Field(None, description="Development package")
    ttype: str | None = Field(None, description="Transaction type (P=Program, R=Report, O=OO)")
    status: TransactionStatus = Field(..., description="Verification status")


class TableSearchResult(BaseModel):
    """Search result for table queries."""
    tabname: str
    description: str | None = None
    field_count: int = 0


class FieldSearchResult(BaseModel):
    """Search result for field queries."""
    tabname: str = Field(..., description="Table containing the field")
    field: TableField


class SAPKnowledgeBase(BaseModel):
    """Complete SAP knowledge base."""
    tables: list[TableMetadata] = Field(default_factory=list)
    transactions: list[TransactionMetadata] = Field(default_factory=list)

    def get_table(self, name: str) -> TableMetadata | None:
        """Get table by name (case-insensitive)."""
        name_upper = name.upper()
        return next((t for t in self.tables if t.tabname.upper() == name_upper), None)

    def get_transaction(self, tcode: str) -> TransactionMetadata | None:
        """Get transaction by code (case-insensitive)."""
        tcode_upper = tcode.upper()
        return next((t for t in self.transactions if t.tcode.upper() == tcode_upper), None)

    def search_tables(self, pattern: str) -> list[TableSearchResult]:
        """Search tables by name pattern."""
        pattern_upper = pattern.upper()
        return [
            TableSearchResult(
                tabname=t.tabname,
                description=t.description,
                field_count=len(t.fields)
            )
            for t in self.tables
            if pattern_upper in t.tabname.upper() or
               (t.description and pattern_upper in t.description.upper())
        ]

    def search_fields(self, pattern: str) -> list[FieldSearchResult]:
        """Search fields across all tables."""
        pattern_upper = pattern.upper()
        results = []
        for t in self.tables:
            for f in t.fields:
                if pattern_upper in f.fieldname.upper() or \
                   (f.description and pattern_upper in f.description.upper()):
                    results.append(FieldSearchResult(tabname=t.tabname, field=f))
        return results
```

### 8.2 Data files location

```
src/sapwebguimcp/data/
├── sap_field_registry.json      (existing - field selectors)
├── sap_table_metadata.json      (NEW - extracted table fields)
├── sap_transaction_metadata.json (NEW - extracted transactions)
```

### 8.3 Resource URIs to implement

| Resource URI | Description | Returns |
|--------------|-------------|---------|
| `sap://tables` | List all known tables | Array of table names with descriptions |
| `sap://tables/{table_name}` | Get table details | Table with all field definitions |
| `sap://tables/{table_name}/fields` | Get fields only | Array of field objects |
| `sap://transactions` | List all transactions | Array of tcodes with titles |
| `sap://transactions/{tcode}` | Get transaction details | Program, screen, package, etc. |
| `sap://search/tables?q={pattern}` | Search tables by name/desc | Matching tables |
| `sap://search/fields?q={pattern}` | Search fields across tables | Matching fields with table context |

### 8.4 Implementation pattern

Create `src/sapwebguimcp/resources/sap_knowledge_resource.py`:

```python
from fastmcp import FastMCP
from importlib import resources
import json

from sapwebguimcp.models.sap_knowledge import (
    SAPKnowledgeBase,
    TableMetadata,
    TransactionMetadata,
    TableSearchResult,
    FieldSearchResult,
)

__all__ = ["register_sap_knowledge_resources"]

# Global knowledge base instance (loaded once)
_kb: SAPKnowledgeBase | None = None


def _get_knowledge_base() -> SAPKnowledgeBase:
    """Load and cache the SAP knowledge base."""
    global _kb
    if _kb is None:
        tables_data = _load_json("sap_table_metadata.json")
        transactions_data = _load_json("sap_transaction_metadata.json")
        _kb = SAPKnowledgeBase(
            tables=[TableMetadata.model_validate(t) for t in tables_data],
            transactions=[TransactionMetadata.model_validate(t) for t in transactions_data],
        )
    return _kb


def _load_json(filename: str) -> list:
    return json.loads(
        resources.files("sapwebguimcp.data")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )


def register_sap_knowledge_resources(mcp: FastMCP) -> None:
    """Register SAP knowledge resources with strict Pydantic typing."""

    @mcp.resource("sap://tables")
    def list_tables() -> list[TableSearchResult]:
        """List all known SAP tables with descriptions."""
        kb = _get_knowledge_base()
        return [
            TableSearchResult(
                tabname=t.tabname,
                description=t.description,
                field_count=len(t.fields)
            )
            for t in kb.tables
        ]

    @mcp.resource("sap://tables/{table_name}")
    def get_table(table_name: str) -> TableMetadata | None:
        """Get full metadata for a specific table including all fields."""
        return _get_knowledge_base().get_table(table_name)

    @mcp.resource("sap://tables/{table_name}/fields")
    def get_table_fields(table_name: str) -> list[dict] | None:
        """Get only the fields for a specific table."""
        table = _get_knowledge_base().get_table(table_name)
        if table:
            return [f.model_dump() for f in table.fields]
        return None

    @mcp.resource("sap://transactions")
    def list_transactions() -> list[TransactionMetadata]:
        """List all known SAP transactions."""
        return _get_knowledge_base().transactions

    @mcp.resource("sap://transactions/{tcode}")
    def get_transaction(tcode: str) -> TransactionMetadata | None:
        """Get details for a specific transaction."""
        return _get_knowledge_base().get_transaction(tcode)

    @mcp.resource("sap://search/tables")
    def search_tables(q: str) -> list[TableSearchResult]:
        """Search tables by name or description pattern."""
        return _get_knowledge_base().search_tables(q)

    @mcp.resource("sap://search/fields")
    def search_fields(q: str) -> list[FieldSearchResult]:
        """Search fields across all tables by fieldname or description."""
        return _get_knowledge_base().search_fields(q)
```

### 8.4 Register in server.py

```python
from sapwebguimcp.resources.sap_knowledge_resource import register_sap_knowledge_resources

# In server setup:
register_sap_knowledge_resources(mcp)
```

### 8.5 Data format for resources

**sap_table_metadata.json:**
```json
[
  {
    "tabname": "/US4G/ART_MALO",
    "description": "Marktlokation Artikel",
    "fields": [
      {"fieldname": "MANDT", "position": 1, "keyflag": "X", "datatype": "CLNT", "length": 3, "decimals": 0, "rollname": "MANDT", "description": "Mandant"},
      {"fieldname": "MALO_ID", "position": 2, "keyflag": "X", "datatype": "CHAR", "length": 33, "decimals": 0, "rollname": "/US4G/MALO_ID", "description": "Marktlokations-ID"}
    ]
  }
]
```

**Note:** Both table `description` and field `description` come from SE11 Kurzbeschreibung fields.

**sap_transaction_metadata.json:**
```json
[
  {"tcode": "ES31", "title": "Anlage aendern", "program": "SAPLES30", "dynpro": "110", "package": "EE01", "status": "exists"},
  {"tcode": "FP02", "title": null, "program": null, "status": "not_found"}
]
```

---

## Phase 9: Execution Checklist

### Before starting extraction
- [ ] Generate remaining_tables.json
- [ ] Create extraction_progress.json
- [ ] Create extraction_checkpoint.jsonl (empty)
- [ ] Create transaction_checkpoint.jsonl (empty)
- [ ] Verify SAP accessible

### Per-batch execution
- [ ] Start agent with correct batch prompt
- [ ] Monitor for keyboard shortcut usage (not clicks!)
- [ ] Verify checkpoint files growing
- [ ] Check progress.json updates

### After extraction complete
- [ ] Merge checkpoints into final JSON files
- [ ] Validate completeness (all tables/transactions accounted for)
- [ ] Copy final JSON to `src/sapwebguimcp/data/`
- [ ] Create `sap_knowledge_resource.py`
- [ ] Register resources in `server.py`
- [ ] Update `resources/__init__.py`
- [ ] Test resources work: `ListMcpResourcesTool`, `ReadMcpResourceTool`

---

## Appendix A: Remaining US4G Tables (233)

Generate by comparing:
- `sap_tables_consolidated.json` → `alle_us4g_tabellen` (613)
- `us4g_field_metadata_380_tables.json` → completed (380)

**Diff = 233 remaining**

---

## Appendix B: EMMA Tables (57)

```
EMMAC_BASIC, EMMAC_BPA, EMMAC_BPC, EMMAC_BPC_PROCID, EMMAC_CANCODE,
EMMAC_CANCODET, EMMAC_CCAT_BND, EMMAC_CCAT_CND, EMMAC_CCAT_COB,
EMMAC_CCAT_HDR, EMMAC_CCAT_HDRT, EMMAC_CCAT_MOB, EMMAC_CCAT_MSG,
EMMAC_CCAT_PRI, EMMAC_CCAT_SOP, EMMAC_CCAT_SOP_B, EMMAC_CCSTATUS,
EMMAC_CCSTATUST, EMMAC_CREACODE, EMMAC_CREACODET, EMMAC_CSTAT_ASS,
EMMAC_CTYPE, EMMAC_CTYPET, EMMAC_CWL_BTN, EMMAC_CWL_BTNT, EMMAC_CWL_SHL,
EMMAC_CWL_SHLT, EMMAC_FWM, EMMAC_FWMT, EMMAC_FWM_ACTION, EMMAC_MSGSUPRS,
EMMAC_MSG_OBJ, EMMAC_MSG_SUPRES, EMMAC_SOPTXTID, EMMAC_SOPTXTIDT,
EMMAC_WUI_CCAT, EMMAC_WUI_OBJ, EMMAC_WUI_PROC, EMMAC_WUI_REP,
EMMAC_WUI_REPT, EMMA_BPA, EMMA_BPAT, EMMA_BPC, EMMA_BPCT, EMMA_CACTOR,
EMMA_CACTOR_CD, EMMA_CASE, EMMA_CMSG_LINK, EMMA_CMSG_LNK_CD,
EMMA_COBJECT, EMMA_COBJECT_CD, EMMA_CSOLP, EMMA_HDR, EMMA_INT,
EMMA_JOBRUNIDMSG, EMMA_MASSACT_INF, EMMA_TCODE
```

---

## Appendix C: Classic IS-U Tables (~75)

```
EANL, EANLD, EANLD1, EANLDATA, EANLDATASAP, EANLH, EANLHD, EANLHDATA,
EANLHDATASAP, EANLHKEY, EUIINSTLN, EUIINSTLN_DATA, EUIINSTLN_DATA_PROFSEL,
EUIINSTLN_KEY, EUIINSTLN_KEY_PROFSEL, EUIINSTLN_PROFSEL, EUITRANS,
EUITRANS_DATA, EUITRANS_DATA_OP, EUITRANS_DATA_PROFSEL, EUITRANS_KEY,
EUITRANS_KEY_PROFSEL, EUITRANS_PROFSEL, EVBS, EVBSCOND, EVBSD, EVBSD1,
EVBST, EVBS_OHNE_CI_INCLUDE, ESERVICE, ESERVICED, ESERVICEDET,
ESERVICEDOCITM, ESERVICEDOCUMENT, ESERVICEKEY, ESERVICE_DEFAULTING,
ESERVPROV, ESERVPROV001QR, ESERVPROV001QR_APPLDATA_IN,
ESERVPROV001QR_APPLDATA_OUT, ESERVPROVBDIDQR_APPLDATA_IN, ERCH, ERCHARC,
ERCHC, ERCHC_DISP, ERCHC_DISP_SEL, ERCHC_SHORT, ERCHC_STABLE, ERCHE,
ERCHE_I1, ERCHE_M18, ERCHE_STABLE, ERCHH, ERCHO, ERCHOD, ERCHO_STABLE,
ERCHP, ERCHP_STABLE, ERCHR, ERCHR_I, ERCHR_STABLE, ERCHT, EVERSREASON,
EVERSREASONT, EVERSW
```

---

## Appendix D: Transactions to Verify

### Already verified (10 exist, 4 missing)
See `sap_transactions_consolidated.json`

### To verify next
```
ES30    Anlage anlegen
ES33    Vertrag aendern
ES80    Geraetewechsel
EG30    Geraeteeinbau
EG32    Geraet anzeigen
EC60    Auszugsbeleg anlegen
EA01    Abrechnung starten
FP01    Vertragskonto anlegen
SM37    Job monitoring
SU01    User maintenance
PFCG    Role maintenance
```
