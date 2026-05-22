# Onboarding Prompts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 6 static markdown prompts to help new users discover and use the SAP Web GUI MCP server.

**Architecture:** Pure content -- 6 new `.md` files in `src/sapguimcp/prompts/`. No code changes. The existing auto-discovery system (`register_prompts` in `__init__.py`) picks them up automatically. Existing CI tests validate format.

**Tech Stack:** Markdown with YAML frontmatter. Follows the template in `src/sapguimcp/prompts/README.md`.

---

### Task 1: Create `getting_started.md` prompt

**Files:**

- Create: `src/sapguimcp/prompts/getting_started.md`

**Step 1: Write the prompt file**

Create `src/sapguimcp/prompts/getting_started.md` with this content:

```markdown
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
search_transactions("Kundenauftrag") # German keywords work too

```

### 2. Look Up SAP Objects (specialized tools, structured results)

These tools return structured data -- faster and more reliable than manual navigation:

| Tool | What it does | Example |
|------|-------------|---------|
| `sap_se11_lookup` | Table/structure fields | `sap_se11_lookup(name="MARA")` |
| `sap_se16_query` | Browse table data | `sap_se16_query(table="T000")` |
| `sap_se24_lookup` | Class/interface details | `sap_se24_lookup(name="CL_SALV_TABLE")` |
| `sap_se37_lookup` | Function module signature | `sap_se37_lookup(name="RFC_READ_TABLE")` |
| `sap_se93_lookup` | Transaction metadata | `sap_se93_lookup(tcode="VA01")` |

### 3. Navigate and Interact with SAP (generic tools)

For any transaction -- not just the ones with specialized tools:

| Tool | What it does |
|------|-------------|
| `sap_transaction("TCODE")` | Open a transaction |
| `sap_press_key("F8")` | Press a key or shortcut |
| `sap_fill_form({...})` | Fill multiple form fields at once |
| `sap_get_screen_text()` | Read current screen content |
| `sap_read_status_bar()` | Read the status bar message |
| `sap_discover_fields()` | Find fillable fields on screen |
| `sap_discover_buttons()` | Find clickable buttons |
| `sap_close_popup()` | Dismiss popup dialogs |

### 4. Use Browser Escape Hatches (when SAP tools aren't enough)

Low-level browser tools for edge cases:

- `browser_snapshot()` -- accessibility tree
- `browser_screenshot()` -- visual screenshot
- `browser_click()` / `browser_fill()` -- direct element interaction

### 5. Run Parallel Agents (for bulk operations)

Open multiple SAP sessions for parallel work:

```

sap_transaction("BP", new_window=True) # Returns session_id
sap_session_bind(session_id="s2", agent_id="subagent-1")

```

## Common First Tasks

- **"What tables exist for X?"** -- Use `search_tables("keyword")`
- **"Show me the fields of table MARA"** -- Use `sap_se11_lookup(name="MARA")`
- **"Read data from table T000"** -- Use `sap_se16_query(table="T000")`
- **"What does function module X do?"** -- Use `sap_se37_lookup(name="FM_NAME")`
- **"Create a business partner"** -- Compose generic tools (see `create_business_partner` prompt)
- **"Develop ABAP with Claude Code"** -- See `abapgit_workflow` prompt

## Tips

- **Use `sap_get_capabilities()` for detailed help** -- returns keyboard shortcuts, tips, and best practices
- **Use `search_transactions()` before guessing** -- the catalog is instant and offline
- **Prefer specialized tools** (sap_se11_lookup, etc.) over manual navigation -- they're faster and return structured data
- **Use `sap_fill_form()` for batch field filling** -- ~10x faster than filling fields one by one
```

**Step 2: Run tests to verify the prompt is valid**

Run: `tox -e unit_tests -- unittests/test_prompts.py -v`
Expected: All tests PASS (file count increases from 1 to 2)

**Step 3: Commit**

```bash
git add src/sapguimcp/prompts/getting_started.md
git commit -m "feat(prompts): add getting_started onboarding prompt"
```

---

### Task 2: Create `explore_table.md` prompt

**Files:**

- Create: `src/sapguimcp/prompts/explore_table.md`

**Step 1: Write the prompt file**

Create `src/sapguimcp/prompts/explore_table.md` with this content:

```markdown
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

sap_se11_lookup(name="TABLE_NAME")

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
- The table might be a view or structure -- SE11 handles both

### "No authorization"

- User needs S_TABU_DIS authorization for the table's authorization group
- Try a different table or ask your SAP admin

### "Maximum number of hits reached"

- Add filters to narrow the result set
- Increase `max_hits` if you need more rows
- Use `output_file` parameter to write large results to disk
```

**Step 2: Run tests**

Run: `tox -e unit_tests -- unittests/test_prompts.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/prompts/explore_table.md
git commit -m "feat(prompts): add explore_table prompt"
```

---

### Task 3: Create `explore_function_module.md` prompt

**Files:**

- Create: `src/sapguimcp/prompts/explore_function_module.md`

**Step 1: Write the prompt file**

Create `src/sapguimcp/prompts/explore_function_module.md` with this content:

```markdown
---
description: Find and understand a function module's signature using SE37
---

# Explore a Function Module

## Overview

This recipe shows how to look up an SAP function module's complete signature -- its import, export, and tables parameters plus exceptions.

## Prerequisites

- SAP session is logged in and ready
- Authorization for SE37 (Function Builder)

## Steps

### Step 1: Look Up the Function Module

Use the specialized SE37 tool:
```

sap_se37_lookup(name="FUNCTION_MODULE_NAME")

```

This returns structured data including:
- **Import parameters** -- inputs you must/can provide
- **Export parameters** -- outputs the FM returns
- **Tables parameters** -- table-type inputs/outputs
- **Exceptions** -- error conditions the FM can raise

### Step 2: Find Function Modules by Keyword

If you don't know the exact name, search the catalog:

```

search_function_modules("keyword")

```

Or search by partial name:

```

search_function_modules("RFC_READ")

```

### Step 3: Understand Parameter Details

For each parameter, the tool returns:
- Parameter name
- Associated type (data element, structure, or table type)
- Whether it's optional or required
- Default value (if any)
- Description

Use `sap_se11_lookup` to inspect complex parameter types (structures/tables).

## Error Handling

### "Function module not found"

- Check spelling (FM names are uppercase)
- Use `search_function_modules("keyword")` to find the correct name
- The FM might be in a different namespace (e.g., `/NAMESPACE/FM_NAME`)

### "No authorization"

- User needs S_DEVELOP authorization or display access to the function group
```

**Step 2: Run tests**

Run: `tox -e unit_tests -- unittests/test_prompts.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/prompts/explore_function_module.md
git commit -m "feat(prompts): add explore_function_module prompt"
```

---

### Task 4: Create `explore_class.md` prompt

**Files:**

- Create: `src/sapguimcp/prompts/explore_class.md`

**Step 1: Write the prompt file**

Create `src/sapguimcp/prompts/explore_class.md` with this content:

```markdown
---
description: Look up an ABAP class or interface with methods, attributes, and events using SE24
---

# Explore a Class or Interface

## Overview

This recipe shows how to look up an ABAP class or interface to understand its methods, attributes, and events.

## Prerequisites

- SAP session is logged in and ready
- Authorization for SE24 (Class Builder)

## Steps

### Step 1: Look Up the Class or Interface

Use the specialized SE24 tool:
```

sap_se24_lookup(name="CLASS_OR_INTERFACE_NAME")

```

This returns structured data including:
- **Methods** -- with parameters, visibility, and descriptions
- **Attributes** -- instance and static attributes with types
- **Events** -- events the class can raise
- **Interfaces** -- interfaces the class implements

### Step 2: Find Classes by Keyword

If you don't know the exact name, search the catalog:

```

search_classes("keyword")

```

Naming conventions:
- `CL_*` -- classes
- `IF_*` -- interfaces
- `ZCL_*` / `ZIF_*` -- custom classes/interfaces

### Step 3: Inspect Method Parameters

The tool returns method signatures with parameter details. For complex parameter types (structures, tables), use `sap_se11_lookup` to inspect the type definition.

## Error Handling

### "Class/interface not found"

- Check spelling (names are uppercase)
- Use `search_classes("keyword")` to find the correct name
- Distinguish between classes (`CL_*`) and interfaces (`IF_*`)

### "No authorization"

- User needs display access to the class or its development package
```

**Step 2: Run tests**

Run: `tox -e unit_tests -- unittests/test_prompts.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/prompts/explore_class.md
git commit -m "feat(prompts): add explore_class prompt"
```

---

### Task 5: Create `create_business_partner.md` prompt

**Files:**

- Create: `src/sapguimcp/prompts/create_business_partner.md`
- Reference: `src/sapguimcp/skills/examples/create_business_partner_bp.md` (existing, for field mappings)
- Reference: `src/sapguimcp/workflows/bp-person-creation.md` (existing, for workflow steps)

**Step 1: Write the prompt file**

Create `src/sapguimcp/prompts/create_business_partner.md` with this content:

```markdown
---
description: Create a business partner (person or organization) by composing generic SAP tools
---

# Create a Business Partner

## Overview

This recipe demonstrates how to automate a complete SAP workflow by composing generic tools. There is no dedicated "create BP" tool -- instead, you combine `sap_transaction`, `sap_press_key`, `sap_fill_form`, and `sap_read_status_bar` to create a business partner from scratch.

This pattern works for **any SAP transaction**, not just BP.

## Prerequisites

- SAP session is logged in and ready
- Authorization for transaction BP
- Know the BP type: person (F5) or organization (Ctrl+F5)

## Steps

### Step 1: Open the BP Transaction
```

sap_transaction("BP")

```

Verify the screen shows "Geschaeftspartner pflegen" (DE) or "Maintain Business Partner" (EN).

### Step 2: Create a New Business Partner

For a **person** (natural person):

```

sap_press_key("F5")

```

For an **organization** (company):

```

sap_press_key("Control+F5")

```

A popup may appear asking to confirm the BP type. If so, confirm it.

### Step 3: Fill the Form Fields

Use `sap_fill_form` to fill all fields in one call. This is much faster than filling fields individually.

**Person fields:**

```

sap_fill_form({
"Anrede": "Herr",
"Vorname": "Max",
"Nachname": "Mustermann",
"Strasse": "Hauptstrasse 1",
"Hausnr.": "1",
"Postleitzahl": "10115",
"Ort": "Berlin",
"Land": "DE"
})

```

**Organization fields:**

```

sap_fill_form({
"Name 1": "Musterfirma GmbH",
"Strasse": "Industriestr.",
"Hausnr.": "42",
"Postleitzahl": "80331",
"Ort": "Muenchen",
"Land": "DE"
})

```

**Tip:** Field labels vary by system language and configuration. If `sap_fill_form` can't find a field by label, use `sap_discover_fields()` to see what's available on the current screen.

### Step 4: Save

```

sap_press_key("Control+S")

```

### Step 5: Check the Result

```

sap_read_status_bar()

```

**On success:** The status bar shows "Geschaeftspartner XXXXXXXXXX angelegt" with the new BP number.

**On error:** See Error Handling below.

### Step 6: Handle Missing Obligatory Fields

If save fails with "Pflichtfeld nicht gefuellt" (required field not filled):

1. Read the screen to identify what's missing:
```

sap_get_screen_text()

```

2. Look for fields marked as required or highlighted

3. Fill the missing fields:
```

sap_fill_form({"Missing Field Label": "value"})

```

4. Try saving again:
```

sap_press_key("Control+S")
sap_read_status_bar()

```

### Step 7: Verify the Created BP

**Option A: Display the BP in the same transaction**

```

sap_transaction("BP")

```

Enter the BP number and display it to confirm the data.

**Option B: Check the database table directly**

```

sap_se16_query(table="BUT000", filters={"PARTNER": "XXXXXXXXXX"})

```

This returns the BP master data record from the database.

### Step 8: Create Another BP

After a successful save, start over from Step 1:

```

sap_transaction("BP")

```

Do NOT try to navigate back -- just restart the transaction.

## Error Handling

### "Pflichtfeld nicht gefuellt" / "Required field not filled"

- Use `sap_get_screen_text()` to find which field is missing
- Required fields depend on the BP role and system configuration
- Common missing fields: Anrede (title), Suchbegriff (search term)

### "Dublette gefunden" / "Duplicate found"

- SAP found a similar BP via duplicate check
- Check if the BP already exists before creating a new one
- Can be overridden if an intentional duplicate

### "Nummernkreis erschoepft" / "Number range exhausted"

- Contact your SAP admin to extend the number range
- Or try a different BP grouping

## Key Takeaway

This workflow uses only generic tools: `sap_transaction`, `sap_press_key`, `sap_fill_form`, `sap_read_status_bar`, `sap_get_screen_text`, and `sap_se16_query`. The same pattern applies to **any** SAP transaction -- open it, fill fields, save, check the result.
```

**Step 2: Run tests**

Run: `tox -e unit_tests -- unittests/test_prompts.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/prompts/create_business_partner.md
git commit -m "feat(prompts): add create_business_partner prompt

Demonstrates composing generic tools (sap_transaction, sap_fill_form,
sap_press_key, sap_read_status_bar) into a complete workflow without
needing a dedicated BP tool."
```

---

### Task 6: Create `abapgit_workflow.md` prompt

**Files:**

- Create: `src/sapguimcp/prompts/abapgit_workflow.md`
- Reference: `src/sapguimcp/data/sap_knowledge.md` (lines 66-135, ABAP development section)

**Step 1: Write the prompt file**

Create `src/sapguimcp/prompts/abapgit_workflow.md` with this content:

```markdown
---
description: End-to-end ABAP development workflow using Claude Code with abapGit and this MCP server for testing
---

# ABAP Development with Claude Code and abapGit

## Overview

This recipe describes the full ABAP development lifecycle: write code locally with Claude Code, sync via abapGit, and test in SAP using this MCP server. Do not write ABAP code directly in the SAP GUI -- use Claude Code instead.

## Prerequisites

- Claude Code installed and configured
- This MCP server added to Claude Code configuration
- abapGit installed in the SAP system (see [abapGit docs](https://docs.abapgit.org/user-guide/getting-started/install.html))
- A Git repository linked to an ABAP package via abapGit
- Claude Code opened in the local repository directory

## The Workflow

### Step 1: Write ABAP Code Locally

Use Claude Code to generate or modify ABAP code in your local repository. The repository maps to one ABAP package in SAP.

### Step 2: Push to Git

Commit and push your changes to the Git repository.

### Step 3: Pull Changes into SAP via abapGit

**Option A: Use the API tool (if available)**
```

abapgit_pull_via_api(repo="YOUR_REPO_NAME")

```

**Option B: Pull manually in SAP**

1. Open abapGit in SAP:
```

sap_transaction("ZABAPGIT")

```
If the transaction doesn't exist, find the program:
```

search_transactions("abapgit")

```

2. Navigate to your repository and pull the latest changes

**Tip:** Use a separate SAP session (Modus) for abapGit so the MCP server doesn't need to switch between abapGit and your test transaction. Open a new session with:

```

sap_transaction("ZABAPGIT", new_window=True)

```

### Step 4: Test in SAP Using the MCP Server

Navigate to the relevant transaction and test your code:

```

sap_transaction("SE38") # For reports
sap_transaction("SE24") # For classes

```

Use the generic tools to interact with your code:
- `sap_fill_form()` to provide test inputs
- `sap_press_key("F8")` to execute
- `sap_read_status_bar()` to check results
- `sap_get_screen_text()` to read output

### Step 5: Iterate

Fix issues in Claude Code, push, pull in abapGit, test again.

## Exploring Objects Outside Your Package

Your abapGit repository only contains objects in one ABAP package. To understand objects outside your package (standard SAP FMs, classes, tables), use the lookup tools:

| Need to understand... | Use |
|----------------------|-----|
| A table's fields | `sap_se11_lookup(name="TABLE_NAME")` |
| A function module's signature | `sap_se37_lookup(name="FM_NAME")` |
| A class's methods | `sap_se24_lookup(name="CLASS_NAME")` |
| Data in a table | `sap_se16_query(table="TABLE_NAME")` |

## Recommended Transactions for ABAP Development

| Transaction | Purpose | Notes |
|------------|---------|-------|
| SE37 | Function Modules | View signature, parameters, exceptions |
| SE38 | Reports / Programs | View and test ABAP reports |
| SE24 | Classes | Inspect methods, attributes, interfaces |
| SE11 | Data Dictionary | View table structures, data elements |
| SE16 | Table Contents | Browse actual data (read-only recommended) |

**Avoid SE80** (Object Navigator) -- its complex tree UI is difficult for the MCP server to navigate. Use the focused transactions above instead.
```

**Step 2: Run tests**

Run: `tox -e unit_tests -- unittests/test_prompts.py -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/sapguimcp/prompts/abapgit_workflow.md
git commit -m "feat(prompts): add abapgit_workflow prompt"
```

---

### Task 7: Run full test suite and verify

**Step 1: Run the full unit test suite**

Run: `tox -e unit_tests -v`
Expected: All tests PASS including prompt validation (7 prompt files total: 6 new + 1 existing)

**Step 2: Run linting**

Run: `tox -e linting`
Expected: PASS (no Python changes)

**Step 3: Run spell check**

Run: `tox -e spell_check`
Expected: PASS (check for typos in prompt content)

**Step 4: Commit any fixes if needed**

If spell check or formatting catches issues, fix and commit.

---

### Task 8: Final commit and cleanup

**Step 1: Verify git status is clean**

```bash
git status
git log --oneline -8
```

Expected: 6 new commits (one per prompt) plus the design doc commit, all on main.

**Step 2: Done**

All 6 prompts are created, tested, and committed. The existing auto-discovery system handles registration automatically.
