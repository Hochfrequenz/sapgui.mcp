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
- The report [Z_ABAPGIT_PULL_MCP_SHORTCUT](https://github.com/Hochfrequenz/Z_ABAPGIT_PULL_MCP_SHORTCUT/blob/main/src/z_abapgit_pull_mcp_shortcut.prog.abap) installed in SAP -- this is required for the `sap_abapgit_pull` tool. The abapGit UI is too complex for browser automation, so this report provides a simple API to pull without clicking through the UI.
- A GitHub Personal Access Token (PAT) with `repo` scope (classic PAT) or Contents: Read permission (fine-grained PAT) -- required for `sap_abapgit_pull` to authenticate against the Git repository
- An existing SAP transport request -- `sap_abapgit_pull` records changes on a transport; the transport must already exist before pulling
- Claude Code opened in the local repository directory

## The Workflow

### Understanding abapGit Serialization (Important!)

abapGit uses a specific file format to serialize ABAP objects. **Incorrect serialization will cause pull failures in SAP.** Before writing or modifying ABAP code, you must understand how abapGit maps files to ABAP objects.

Key points:

- Each ABAP object is stored as a `.abap` source file plus one or more `.xml` metadata files
- **All filenames MUST be lowercase** (e.g., `zcl_my_class.clas.abap`, NOT `ZCL_MY_CLASS.clas.abap`). abapGit serializes and expects lowercase filenames even though the ABAP object names are uppercase. Uppercase filenames cause "File not found" errors during pull.
- File names must follow abapGit naming conventions (e.g., `z_my_report.prog.abap` + `z_my_report.prog.xml`)
- The `.xml` files contain object metadata (program attributes, text pools, etc.) that SAP needs for deserialization
- The `.abapgit.xml` in the repository root defines the package mapping and folder logic

**Read the serialization documentation:** [abapGit Serializer Documentation](https://docs.abapgit.org/user-guide/reference/supported.html)

**Study existing examples before writing code.** Check your repository for existing serialized objects and follow the same patterns. The [Z_PUBLIC_ABAPGIT_TEST_REPOSITORY](https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY) contains working examples of serialized reports with correct XML metadata.

### Step 1: Write ABAP Code Locally

Use Claude Code to generate or modify ABAP code in your local repository. The repository maps to one ABAP package in SAP.

### Step 2: Push to Git

Commit and push your changes to the Git repository.

### Step 3: Pull Changes into SAP via abapGit

**Option A: Use the API tool (recommended)**

This requires the `Z_ABAPGIT_PULL_MCP_SHORTCUT` report (see Prerequisites). It pulls without navigating the abapGit UI, which is much faster and more reliable.

```
sap_abapgit_pull(repo="YOUR_REPO_NAME", trkorr="DEVK900123", username="github-user", pat="ghp_...")
```

**Option B: Pull manually in SAP (slow, not recommended)**

The abapGit UI is complex and hard to automate via browser. Only use this as a fallback if `Z_ABAPGIT_PULL_MCP_SHORTCUT` is not installed.

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
- `sap_press_key("F8")` to execute
- `sap_read_status_bar()` to check results
- `sap_get_screen_text()` to read output

### Step 5: Iterate

Fix issues in Claude Code, push, pull in abapGit, test again.

## Exploring Objects Outside Your Package

Your abapGit repository only contains objects in one ABAP package. To understand objects outside your package (standard SAP FMs, classes, tables), use the lookup tools:

| Need to understand...         | Use                                                        |
| ----------------------------- | ---------------------------------------------------------- |
| A table's fields              | `sap_se11_lookup(names="TABLE_NAME", object_type="table")` |
| A function module's signature | `sap_se37_lookup(function_modules="FM_NAME")`              |
| A class's methods             | `sap_se24_lookup(classes="CLASS_NAME")`                    |
| Data in a table               | `sap_se16_query(table="TABLE_NAME")`                       |

## Recommended Transactions for ABAP Development

| Transaction | Purpose            | Notes                                      |
| ----------- | ------------------ | ------------------------------------------ |
| SE37        | Function Modules   | View signature, parameters, exceptions     |
| SE38        | Reports / Programs | View and test ABAP reports                 |
| SE24        | Classes            | Inspect methods, attributes, interfaces    |
| SE11        | Data Dictionary    | View table structures, data elements       |
| SE16        | Table Contents     | Browse actual data (read-only recommended) |

**Avoid SE80** (Object Navigator) -- its complex tree UI is difficult for the MCP server to navigate. Use the focused transactions above instead.
