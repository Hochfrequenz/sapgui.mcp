# Onboarding Prompts Design

## Problem

New users (both Claude Code developers and Claude Desktop business users) don't know what the MCP server can do or how to get started. They need discoverable, guided entry points.

## Solution

Add 6 static markdown prompts to `src/sapguimcp/prompts/` using the existing auto-discovery system. No code changes required.

## Approach

**Static Recipes (Approach A)** -- chosen over parameterized prompts (B) and hub+auto-discovery (C) for simplicity. Zero code changes, follows existing patterns, easy to extend later.

## Prompt Set

| #   | Filename                     | Description                                                         | Audience   | Demonstrates           |
| --- | ---------------------------- | ------------------------------------------------------------------- | ---------- | ---------------------- |
| 1   | `getting_started.md`         | Overview of all capabilities, guides user to pick a task            | Both       | Discovery              |
| 2   | `explore_table.md`           | Look up table structure (SE11) and optionally browse data (SE16)    | Both       | Single-tool usage      |
| 3   | `explore_function_module.md` | Find and understand a function module's signature (SE37)            | Developers | Single-tool usage      |
| 4   | `explore_class.md`           | Look up a class or interface in SE24                                | Developers | Single-tool usage      |
| 5   | `create_business_partner.md` | Create a person or org BP, fill fields, save, handle errors, verify | Both       | Multi-tool chaining    |
| 6   | `abapgit_workflow.md`        | End-to-end ABAP development with Claude Code and abapGit            | Developers | Full lifecycle         |
| -   | `se16_bulk_read.md`          | (existing) Bulk table reading with filters                          | Both       | Pagination + filtering |

## Content Structure

Each prompt follows the existing template from `prompts/README.md`:

```markdown
---
description: One-line description shown in MCP prompt list (min 10 chars)
---

# Prompt Title

## Overview

Brief description of what this recipe accomplishes.

## Prerequisites

- User must be logged into SAP
- Required authorizations

## Steps

1. Step one with tool calls
2. Step two...

## Error Handling

Common errors and how to recover.
```

## Design Philosophy

The prompt set demonstrates a progression of complexity:

1. **Discovery** (`getting_started`) -- what's available
2. **Single specialized tool** (`explore_table`, `explore_function_module`, `explore_class`) -- one tool call, structured result
3. **Generic tool composition** (`create_business_partner`) -- no dedicated BP tool exists; instead, generic tools (`sap_transaction`, `sap_press_key`, `sap_fill_form`, `sap_read_status_bar`) are combined into a complete workflow
4. **Full lifecycle** (`abapgit_workflow`) -- MCP server as part of a broader development process

The BP prompt is the key teaching example: it shows that any SAP workflow can be automated by composing the generic tools, without needing a specialized tool for every transaction.

## Prompt Content Details

### 1. getting_started

Hub prompt that lists all available tool categories:

- SAP navigation tools (transactions, keyboard, screen reading)
- Specialized lookup tools (SE11, SE16, SE24, SE37, SE93)
- Transaction catalog search (offline, instant)
- Browser escape hatches (for edge cases)
- Session management (parallel agents)
- Workflow learning

Suggests common starting tasks and which prompt/tool to use.

### 2. explore_table

Combines SE11 (structure) and SE16 (data):

1. `sap_se11_lookup(name="TABLE_NAME")` to get field definitions
2. Optionally `sap_se16_query(table="TABLE_NAME")` to browse data
3. Error handling for "table not found" and authorization issues

### 3. explore_function_module

Uses SE37 lookup:

1. `sap_se37_lookup(name="FM_NAME")` to get signature
2. Explains import/export/tables/exceptions tabs
3. Error handling for "FM not found"

### 4. explore_class

Uses SE24 lookup:

1. `sap_se24_lookup(name="CLASS_NAME")` to get methods/attributes
2. Explains the difference between classes and interfaces
3. Error handling for "class not found"

### 5. create_business_partner

Multi-tool workflow demonstrating SAP automation:

1. `sap_transaction("BP")` -- open transaction
2. `sap_press_key("F5")` or `sap_press_key("Control+F5")` -- create person or org
3. `sap_fill_form({...})` -- fill name, address fields
4. `sap_press_key("Control+S")` -- save
5. `sap_read_status_bar()` -- check for success or errors
6. Handle missing obligatory fields (re-read screen, fill missing, retry)
7. Verification: display created BP or `sap_se16_query(table="BUT000", filters={"PARTNER": "..."})`

Draws from existing `skills/examples/create_business_partner_bp.md` and `workflows/bp-person-creation.md`.

### 6. abapgit_workflow

End-to-end developer workflow:

1. Write ABAP code locally with Claude Code
2. Push to Git repository
3. Pull in SAP via abapGit (`abapgit_pull_via_api` or manual)
4. Test using MCP server (navigate to transaction, verify behavior)
5. Iterate: fix, push, pull, test

Draws from existing `sap_knowledge.md` ABAP development section.

## Testing

Existing CI validates prompt format automatically via `test_prompts.py`. The test that checks prompt count will pass because it counts files dynamically (no hardcoded count).

## Non-Goals

- No parameterized prompts (arguments) -- can be added later
- No code changes to the prompt registration system
- No changes to the workflow system
- No auto-generation of the getting_started hub content
