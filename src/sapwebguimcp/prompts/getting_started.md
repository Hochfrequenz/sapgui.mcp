---
description: Overview of SAP Web GUI MCP server capabilities and how to get started
---

# Getting Started with SAP Web GUI MCP Server

## Overview

This MCP server lets you automate SAP Web GUI through a Chrome browser. You can navigate transactions, fill forms, read data, and compose multi-step workflows -- all through tool calls.

## Prerequisites

- SAP Web GUI is accessible in the browser
- You have SAP login credentials
- The MCP server is running and connected

## What You Can Do

### 1. Search the Transaction Catalog (no SAP login needed)

Find the right transaction code from ~4,000 indexed transactions:

```
search_transactions("sales order")
search_transactions("VA", area="SD")
search_transactions("Kundenauftrag")  # German keywords work too
```

### 2. Look Up SAP Objects (specialized tools, structured results)

These tools return structured data -- faster and more reliable than manual navigation:

| Tool                | What it does              | Example                                                        |
| ------------------- | ------------------------- | -------------------------------------------------------------- |
| `sap_se11_lookup`   | Table/structure fields    | `sap_se11_lookup(names="MARA", object_type="table")`           |
| `sap_se16_query`    | Browse table data         | `sap_se16_query(table="T000")`                                 |
| `sap_se24_lookup`   | Class/interface details   | `sap_se24_lookup(classes="CL_SALV_TABLE")`                     |
| `sap_se37_lookup`   | Function module signature | `sap_se37_lookup(function_modules="RFC_READ_TABLE")`           |
| `sap_se93_lookup`   | Transaction metadata      | `sap_se93_lookup(tcodes="VA01")`                               |

### 3. Navigate and Interact with SAP (generic tools)

For any transaction -- not just the ones with specialized tools:

| Tool                       | What it does                      |
| -------------------------- | --------------------------------- |
| `sap_transaction("TCODE")` | Open a transaction                |
| `sap_keyboard("F8")`       | Press a key or shortcut           |
| `sap_fill_form({...})`     | Fill multiple form fields at once |
| `sap_get_screen_text()`    | Read current screen content       |
| `sap_read_status_bar()`    | Read the status bar message       |
| `sap_discover_fields()`    | Find fillable fields on screen    |
| `sap_discover_buttons()`   | Find clickable buttons            |
| `sap_close_popup()`        | Dismiss popup dialogs             |

### 4. Use Browser Escape Hatches (when SAP tools aren't enough)

Low-level browser tools for edge cases:

- `browser_snapshot()` -- accessibility tree
- `browser_screenshot()` -- visual screenshot
- `browser_click()` / `browser_fill()` -- direct element interaction

### 5. Run Parallel Agents (for bulk operations)

Open multiple SAP sessions for parallel work:

```
sap_transaction("BP", new_window=True)  # Returns session_id
sap_session_bind(session_id="s2", agent_id="subagent-1")
```

## Common First Tasks

- **"What tables exist for X?"** -- Use `search_tables("keyword")`
- **"Show me the fields of table MARA"** -- Use `sap_se11_lookup(names="MARA", object_type="table")`
- **"Read data from table T000"** -- Use `sap_se16_query(table="T000")`
- **"What does function module X do?"** -- Use `sap_se37_lookup(function_modules="FM_NAME")`
- **"Create a business partner"** -- Compose generic tools (see `create_business_partner` prompt)
- **"Develop ABAP with Claude Code"** -- See `abapgit_workflow` prompt

## Tips

- **Use `sap_get_capabilities()` for detailed help** -- returns keyboard shortcuts, tips, and best practices
- **Use `search_transactions()` before guessing** -- the catalog is instant and offline
- **Prefer specialized tools** (sap_se11_lookup, etc.) over manual navigation -- they're faster and return structured data
- **Use `sap_fill_form()` for batch field filling** -- ~10x faster than filling fields one by one
