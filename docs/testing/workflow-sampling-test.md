# Workflow Sampling Manual Test

This document provides prompts for manually testing the workflow system with MCP Sampling.

## Why This Test is Manual (Not Automated)

The `workflow_run` tool uses `ctx.sample()` which requires the MCP client to provide an LLM for server-side agent loops. Our automated test framework uses a minimal `ClientSession` that doesn't support MCP Sampling - it's a protocol client, not an LLM client.

To properly test sampling, you need a real MCP client like Claude Desktop that can:
1. Receive sampling requests from the server
2. Execute them using its LLM
3. Return results back to the server

This is why we have automated tests for `workflow_list`, `workflow_save`, `workflow_delete` (which don't need sampling), but `workflow_run` must be tested manually.

**Requirements:**
- MCP client with Sampling support
- SAP Web GUI access with EMMACL transaction

**Important Limitation (January 2026):**
Neither Claude Desktop nor Claude Code support MCP sampling yet.
See [tracking issue #1785](https://github.com/anthropics/claude-code/issues/1785) for status.
Until this is resolved, `workflow_run` will fail with "Client does not support sampling".

## Test 1: Full Learning + Execution Flow

Copy and paste this prompt into Claude Desktop (or another sampling-compatible client):

```
I want to test the workflow system by clicking through EMMACL cases.

**Phase 1: Setup**
1. Login to SAP with sap_login
2. Open transaction EMMACL
3. Press F8 to execute without filters
4. Use sap_read_table to get the first 20 cases

**Phase 2: Learning (manual, 2-3 iterations)**
For the first 3 cases:
- Click on the case using sap_click_table_cell (row X, column "Fall")
- Note what screen opens (use sap_get_screen_info)
- Press F3 to go back
- Observe what works and what doesn't

**Phase 3: Save Workflow**
Based on what you learned, save a workflow using workflow_save with:
- name: "emmacl-case-review"
- description: "Click through EMMACL cases to review them"
- applicable_when: "Reviewing clearing cases in EMMACL"
- prompt: (write an optimized prompt based on what you learned)

**Phase 4: Bulk Execution**
Use workflow_run to process the remaining 12 cases:
- name: "emmacl-case-review"
- items: [{"row": "4"}, {"row": "5"}, ... {"row": "15"}]

Report the results: how many succeeded, how many failed.
Compare context usage between manual (Phase 2) and workflow (Phase 4).
```

## Test 2: Quick workflow_run Test (with bundled workflow)

If you just want to test `workflow_run` with the bundled BP creation workflow:

```
First, show me available workflows with workflow_list.

Then use workflow_run to create 3 test business partners:
- name: "bp-person-creation"
- items: [
    {"vorname": "Max", "nachname": "Mustermann", "strasse": "Hauptstr. 1", "plz": "10115", "ort": "Berlin"},
    {"vorname": "Erika", "nachname": "Musterfrau", "strasse": "Nebenstr. 2", "plz": "20095", "ort": "Hamburg"},
    {"vorname": "Hans", "nachname": "Test", "strasse": "Testweg 3", "plz": "80331", "ort": "München"}
  ]

Report the results and compare context usage to doing this manually.
```

## What to Watch For

1. **Progress reporting** - You should see "Processing 1/15..." updates
2. **Single tool result** - Only one `workflow_run` call in your context
3. **Aggregated results** - Summary showing succeeded/failed counts
4. **Error details** - If any fail, you'll see which items and why
5. **Context savings** - Compare token count before/after

## Expected Context Savings

| Approach | ~Tokens for 15 items |
|----------|---------------------|
| Manual iteration | ~18,000 tokens |
| workflow_run | ~2,000 tokens |
| **Savings** | **~89%** |

## Troubleshooting

**"Sampling not supported" error:**
Your MCP client doesn't support the Sampling feature. As of January 2026, neither Claude Desktop nor Claude Code support MCP sampling. See [tracking issue #1785](https://github.com/anthropics/claude-code/issues/1785).

**workflow_run fails immediately:**
- Check that the workflow exists (`workflow_list`)
- Verify item format matches what the workflow prompt expects
- Check SAP login status
