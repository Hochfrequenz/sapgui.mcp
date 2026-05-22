# Design: Remove MCP Sampling / workflow_run

## Context

The `workflow_run` tool uses `ctx.sample()` to execute bulk SAP operations server-side. As of March 2026, no MCP client supports both sampling AND SAP authentication. The tool has never been tested end-to-end and is dead code. Remove it and all references to "missing sampling support."

The other workflow tools (`workflow_list`, `workflow_save`, `workflow_submit`, `workflow_delete`) work fine and stay.

## Changes

### 1. Remove `workflow_run` tool and its helper

**File:** `src/sapguimcp/tools/workflow_tools.py`

- Delete `_execute_workflow_run()` (lines 41-126)
- Delete the `workflow_run` tool registration (lines 261-276)
- Remove the `get_sampling_tools` import (line 34)

### 2. Remove `get_sampling_tools()`

**File:** `src/sapguimcp/tools/sap_tool_impl.py`

- Delete `get_sampling_tools()` function (lines 378-395)
- Remove it from `__all__` (line 40)
- Update the module docstring (line 2) — remove "and sampling" reference

### 3. Remove `WorkflowRunResult` and `WorkflowError` models

**File:** `src/sapguimcp/models/workflow_models.py`

- Delete `WorkflowError` class (lines 57-62)
- Delete `WorkflowRunResult` class (lines 64-77)

**File:** `src/sapguimcp/models/__init__.py`

- Remove `WorkflowError` and `WorkflowRunResult` from imports and `__all__`

### 4. Update README

**File:** `README.md`

- Remove `workflow_run` row from the workflow tools table
- Remove the sampling note/disclaimer below the table

### 5. Delete sampling test docs

- Delete `docs/testing/workflow-sampling-test.md`
- Delete `docs/testing/workflow-sampling-copilot-setup.md`

### 6. Update bulk-operations-performance doc

**File:** `docs/bulk-operations-performance.md`

- Remove section 3 ("MCP Sampling (workflow_run)")
- Remove the "For Context Optimization" recommendation that says to wait for sampling

### 7. Clean up references in other files

**File:** `unittests/test_sap_integration.py`

- Remove comments referencing `workflow_run` and `ctx.sample()` (the test itself stays — it tests EMMACL iteration, not workflow_run)

**File:** `docs/plans/2026-01-04-workflow-learning-design.md`

- This is a historical design doc. Leave it as-is (it documents what was designed, not what currently exists).

## What stays unchanged

- `workflow_list`, `workflow_save`, `workflow_submit`, `workflow_delete` tools
- `Workflow`, `WorkflowListResult`, `WorkflowSaveInput`, `WorkflowSaveResult`, `WorkflowDeleteResult`, `WorkflowSubmitResult` models
- `workflow_storage.py` (load/save/delete workflows)
- Bundled workflows in `src/sapguimcp/workflows/`
- All `sap_*_impl` functions in `sap_tool_impl.py` (used by MCP tools directly)
