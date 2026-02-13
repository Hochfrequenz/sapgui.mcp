---
description: Step-by-step guide for reading SAP table data using SE16 with filters
---

# SE16 Bulk Read

## Overview

This recipe guides a subagent through reading SAP table data using the `sap_se16_query` tool.
Follow these exact steps - they have been validated by the main agent.

## Prerequisites

- SAP session is logged in and ready
- User has authorization for SE16

## Steps

### Step 1: Discover Field Names (if filtering)

If you need to filter by specific fields, first look up the table structure using `sap_se11_lookup`:

```
sap_se11_lookup(names="<TABLE_NAME>", object_type="table")
```

This returns the table's fields with their names, types, and descriptions. Use these field names in your filters.

### Step 2: Query the Table

Use the `sap_se16_query` tool with the target table and optional filters:

```
sap_se16_query(
    table="<TABLE_NAME>",
    filters={"FIELD1": "VALUE1", "FIELD2": "VALUE2"},
    max_hits=100
)
```

Parameters:

- `table` (required): The SAP table name (e.g., "MARA", "BKPF")
- `filters` (optional): Dictionary of field names to filter values
- `max_hits` (optional): Maximum number of rows to return (default: 100)
- `output_file` (optional): Path to write results as JSON file
- `session` (optional): Session ID for multi-session scenarios

### Step 3: Process Results

The tool returns a structured result with:

- `success`: Boolean indicating if the query succeeded
- `rows`: List of row objects with field values
- `returned_rows`: Number of rows returned
- `total_hits`: Total matching rows in SAP
- `columns`: List of column names
- `truncated`: Whether results were limited by max_hits

### Step 4: Handle Large Result Sets

For tables with many rows:

1. Use `max_hits` to limit initial results
2. Add filters to narrow the result set
3. Use `output_file` to write large results to disk

## Error Handling

### "No authorization for table"

- Check user has S_TABU_DIS authorization for the table's authorization group
- Try SE16N instead if available

### "Table does not exist"

- Verify table name spelling
- Use SE11 to check if table exists in the system

### "Maximum number of hits reached"

- Add filters to reduce result set
- Increase `max_hits` if you need more rows

## Success Criteria

- Query returns `success: true`
- Data matches expected format
- No error messages in status bar
