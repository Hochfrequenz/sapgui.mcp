# SE16 Data Browser MCP Tool Design

## Overview

Build an MCP tool for querying SAP table data via SE16N transaction, returning structured row data.

## Findings from Exploration

- **ARIA snapshots work for small tables** (tested T000 with 6 rows - all captured)
- **Lazy loading limits visible rows to ~14-15** (tested TSTC with 500 rows - only 14 visible)
- **PageDown/Ctrl+End don't change visible rows in snapshot** - lazy loading is server-side rendering
- **Clipboard export (Ctrl+A/C) doesn't work** - Ctrl+A only selects first row
- **File export doesn't work** in user's environment (confirmed by user)

## Design Decision

Use **Max Hits Limit + Warning** approach:

1. Set `Max. Number of Hits` field before executing query
2. Execute query (F8)
3. Check `Number of Hits` textbox for actual count
4. If count equals max hits, include warning that results may be truncated
5. Parse visible rows from ARIA snapshot

This approach:
- Works reliably for common use cases (LLM needs representative sample, not millions of rows)
- Simple implementation similar to SE11 parsing
- Clear feedback to user about truncation

## Tool Signature

```python
async def sap_se16_query(
    table: str,                                    # Required: table name (e.g., "MARA", "T000")
    filters: dict[str, str] | None = None,         # Optional: {field_name: value} or {field_name: "low|high"}
    max_hits: int = 100,                           # Max rows to return (default 100)
    output_file: str | None = None,                # Optional: write JSON to file instead of inline
) -> SE16Result | SE16FileSummary:
```

## Data Model

```python
class SE16Row(BaseModel):
    """A single row from SE16 query result."""
    data: dict[str, str]  # Column name -> value (all values as strings)

class SE16Result(ToolResult):
    """Result of SE16 query."""
    table: str
    total_hits: int
    returned_rows: int
    truncated: bool  # True if total_hits >= max_hits (may have more data)
    columns: list[str]  # Column names in order
    rows: list[SE16Row]
    retrieved_at: AwareDatetime

class SE16FileSummary(ToolResult):
    """Summary when output written to file."""
    output_file: str
    table: str
    total_hits: int
    returned_rows: int
    truncated: bool
    columns: list[str]
    sample_rows: list[SE16Row]  # First 5 rows as preview
```

## Implementation Steps

1. **Create models** (`src/sapwebguimcp/models/se16_models.py`)
   - SE16Row, SE16Result, SE16FileSummary

2. **Create parsing logic** (`src/sapwebguimcp/parsers/se16_parser.py`)
   - Parse column headers from grid header row
   - Parse data rows matching cells to columns
   - Handle empty cells

3. **Create tool** (`src/sapwebguimcp/tools/se16_tools.py`)
   - Navigate to SE16N
   - Set table name
   - Set filters if provided
   - Set max hits
   - Execute (F8)
   - Get snapshot
   - Parse results
   - Return SE16Result or write to file

4. **Write tests**
   - Unit tests for parser using captured snapshots
   - Integration test with T000 (small table)

## Parsing Strategy

From ARIA snapshot:
```yaml
- row "Column for row selection Client Name City...":
    - columnheader "Column for row selection": To select all...
    - columnheader "Client"
    - columnheader "Name"
    ...
- row "To select a row... 000 SAP AG Walldorf EUR...":
    - gridcell "To select a row..."
    - gridcell "000":
        - textbox
    - gridcell "SAP AG":
        - textbox
    ...
```

Parse strategy:
1. Find header row (contains `columnheader` elements)
2. Extract column names from columnheaders (skip "Column for row selection")
3. Find data rows (start with `- row "To select a row...`)
4. For each row, extract gridcell values (skip first "To select a row" cell)
5. Match gridcell values to column names positionally

## Filter Syntax

Support simple equality filters via the Selection Criteria grid:
- `{"MANDT": "100"}` - single value
- `{"MATNR": "MAT001|MAT100"}` - range (From-Value | To-Value)

Complex filters (wildcards, multiple values) deferred to future enhancement.

## Error Handling

- Table not found: Return SE16Result with success=False, error message
- No data: Return SE16Result with empty rows, success=True
- Network/timeout: Return SE16Result with success=False, error message

## Limitations

- Maximum ~14-15 rows visible in single snapshot (lazy loading)
- Setting max_hits > 500 may trigger SAP warnings
- Filter syntax limited to simple equality and ranges
