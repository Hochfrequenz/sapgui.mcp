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
sap_transaction("SE38")  # For reports
sap_transaction("SE24")  # For classes
```

Use the generic tools to interact with your code:

- `sap_fill_form()` to provide test inputs
- `sap_keyboard("F8")` to execute
- `sap_read_status_bar()` to check results
- `sap_get_screen_text()` to read output

### Step 5: Iterate

Fix issues in Claude Code, push, pull in abapGit, test again.

## Exploring Objects Outside Your Package

Your abapGit repository only contains objects in one ABAP package. To understand objects outside your package (standard SAP FMs, classes, tables), use the lookup tools:

| Need to understand...         | Use                                        |
| ----------------------------- | ------------------------------------------ |
| A table's fields              | `sap_se11_lookup(name="TABLE_NAME")`       |
| A function module's signature | `sap_se37_lookup(name="FM_NAME")`          |
| A class's methods             | `sap_se24_lookup(name="CLASS_NAME")`       |
| Data in a table               | `sap_se16_query(table="TABLE_NAME")`       |

## Recommended Transactions for ABAP Development

| Transaction | Purpose              | Notes                                    |
| ----------- | -------------------- | ---------------------------------------- |
| SE37        | Function Modules     | View signature, parameters, exceptions   |
| SE38        | Reports / Programs   | View and test ABAP reports               |
| SE24        | Classes              | Inspect methods, attributes, interfaces  |
| SE11        | Data Dictionary      | View table structures, data elements     |
| SE16        | Table Contents       | Browse actual data (read-only recommended) |

**Avoid SE80** (Object Navigator) -- its complex tree UI is difficult for the MCP server to navigate. Use the focused transactions above instead.
