---
description: Look up an SAP table structure with SE11 and optionally browse its data with SE16
---

# Explore a Table

## Overview

This recipe shows how to explore an SAP table: first look up its structure (fields, types, descriptions), then optionally browse its actual data.

## Prerequisites

- SAP session is logged in and ready
- Authorization for SE11 (Data Dictionary) and optionally SE16 (Table Browser)

## Steps

### Step 1: Look Up the Table Structure

Use the specialized SE11 tool to get the table's field definitions:

```
sap_se11_lookup(names="TABLE_NAME", object_type="table")
```

This returns structured data including:

- Field names and their ABAP data types
- Field descriptions (labels)
- Key fields
- Field lengths

### Step 2: Browse Table Data (optional)

If you want to see actual data in the table, use the SE16 tool:

```
sap_se16_query(table="TABLE_NAME", max_hits=100)
```

To filter results, use field names from Step 1:

```
sap_se16_query(
    table="TABLE_NAME",
    filters={"FIELD1": "VALUE1", "FIELD2": "VALUE2"},
    max_hits=100
)
```

### Step 3: Find Related Tables

If you don't know the exact table name, search the catalog:

```
search_tables("keyword")
```

Or search by partial name:

```
search_tables("MARA")
```

## Error Handling

### "Table/structure not found"

- Check spelling (SAP table names are uppercase)
- Use `search_tables("keyword")` to find the correct name
- The object might be a structure -- try `sap_se11_lookup(names="NAME", object_type="structure")`

### "No authorization"

- User needs S_TABU_DIS authorization for the table's authorization group
- Try a different table or ask your SAP admin

### "Maximum number of hits reached"

- Add filters to narrow the result set
- Increase `max_hits` if you need more rows
- Use `output_file` parameter to write large results to disk
