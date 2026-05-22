# SE16 Data Browser MCP Tool Design

## Overview

Build an MCP tool for querying SAP table data via SE16N transaction, returning structured row data.

## Findings from Exploration

- **ARIA snapshots work for small tables** (tested T000 with 6 rows - all captured)
- **Each snapshot shows ~13 visible rows** due to lazy loading
- **PageDown DOES work for pagination** when grid is focused first
- **Pagination is gapless** - verified by comparing SAP's "Number of Hits" to collected rows (5000/5000 match)
- **Clipboard export doesn't work** - Ctrl+A only selects first row
- **File export doesn't work** in user's environment (confirmed by user)
- **German locale handling**: "Number of Hits" field uses dot as thousands separator (e.g., "5.000" = 5000)
- **YAML quoting**: Row names containing colons are wrapped in single quotes by YAML serializer

## Design Decision: Pagination-Based Collection

Use **iterative pagination** to collect all rows:

1. Navigate to SE16N, set table name and optional filters
2. Set `Max. Number of Hits` to limit results
3. Execute query (F8)
4. **Focus the grid** (click on `[role='grid']` selector)
5. Loop: snapshot → parse rows → PageDown → wait 1.5s → repeat
6. Stop when: collected rows == "Number of Hits" OR no new rows found
7. Return all collected rows

**Verified behavior:**

- ~13 rows visible per page
- PageDown scrolls to next set of rows
- Pages are contiguous (e.g., page ends at row 22, next page starts at row 23)
- **100% data integrity**: SAP says 5000 rows, we collect exactly 5000 rows (verified in stress test)

This approach:

- Can collect **5000+ rows reliably** (stress tested with TSTC table)
- No data loss between pages (verified)
- Each page takes ~1.6 seconds (7 rows/second throughput)

## Tool Signature

```python
async def sap_se16_query(
    table: str,                                    # Required: table name (e.g., "MARA", "T000")
    filters: dict[str, str] | None = None,         # Optional: {field_name: value} or {field_name: "low|high"}
    max_hits: int = 100,                           # Max rows to return (default 100)
    output_file: str | None = None,                # Optional: write JSON to file instead of inline
) -> SE16Result | SE16FileSummary:
```

**Tool Description (for MCP):**

> Query SAP table data via SE16N. Returns structured rows with column names.
>
> **Performance:** ~7 rows/second due to pagination.
>
> - 100 rows ≈ 14 seconds
> - 500 rows ≈ 1.5 minutes
> - 1000 rows ≈ 2.5 minutes
> - 5000 rows ≈ 12 minutes
>
> For large results, use `output_file` to write JSON to disk.

## Data Model

```python
class SE16Row(BaseModel):
    """A single row from SE16 query result.

    Design decision: Using dict[str, Any] to allow smart type coercion
    (numbers, dates) while maintaining Pydantic serializability. If a value
    cannot be safely coerced, it remains as string. All values are guaranteed
    JSON-serializable.
    """
    data: dict[str, Any]  # Column name -> value (coerced types where possible)

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

## Progress Reporting

Uses FastMCP's `ctx.report_progress()` during pagination:

```python
await ctx.report_progress(progress=rows_collected, total=total_hits)
```

This allows clients that support progress tokens to display collection progress.
Clients without support silently ignore these calls (no errors).

## Implementation Steps

1. **Create models** (`src/sapguimcp/models/se16_models.py`)
    - SE16Row, SE16Result, SE16FileSummary

2. **Create parsing logic** (`src/sapguimcp/parsers/se16_parser.py`)
    - Parse column headers from grid header row
    - Parse data rows matching cells to columns
    - Handle empty cells

3. **Create tool** (`src/sapguimcp/tools/se16_tools.py`)
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
3. Find data rows - match BOTH formats:
    - `- row "To select a row..."` (normal rows)
    - `- 'row "To select a row..."':` (YAML-quoted when values contain colons)
4. For each row, extract gridcell values (skip first "To select a row" cell)
5. Match gridcell values to column names positionally

**Important:** Use regex pattern `- '?row \"To select a row` to handle both formats.

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

- ~13 rows per page, requires pagination for larger result sets
- Each page takes ~1.6 seconds (7 rows/second throughput)
- No hard limit found - 5000 rows collected successfully in ~12 minutes
- Filter syntax limited to simple equality and ranges
- Row parsing requires handling YAML-quoted row names when values contain colons

## Performance Estimates (Verified)

| Rows | Pages | Time   | Rate  |
| ---- | ----- | ------ | ----- |
| 13   | 1     | ~2s    | 6.5/s |
| 50   | 4     | ~7s    | 7.1/s |
| 100  | 8     | ~14s   | 7.1/s |
| 500  | 39    | ~71s   | 7.0/s |
| 1000 | 77    | ~143s  | 7.0/s |
| 5000 | 385   | ~12min | 7.0/s |

**Stress Test Results (TSTC table, 5000 rows):**

- Collected: 5000/5000 rows (100% accuracy)
- Time: 739 seconds (12 min 19 sec)
- Rate: 7.0 rows/second
- Pages traversed: ~385
