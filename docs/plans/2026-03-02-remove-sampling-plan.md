# Remove MCP Sampling / workflow_run — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the dead `workflow_run` tool, `get_sampling_tools()`, related models, docs, and all "requires sampling" references.

**Architecture:** Pure deletion — no new code. Remove sampling-dependent code from workflow_tools.py, sap_tool_impl.py, workflow_models.py, models/**init**.py, README, and docs. Keep all other workflow tools intact.

**Tech Stack:** Python, Pydantic, FastMCP

---

### Task 1: Remove `WorkflowError` and `WorkflowRunResult` from models

**Files:**

- Modify: `src/sapguimcp/models/workflow_models.py:57-77`
- Modify: `src/sapguimcp/models/__init__.py:161,163,321,323`

**Step 1: Delete `WorkflowError` and `WorkflowRunResult` from workflow_models.py**

In `src/sapguimcp/models/workflow_models.py`, delete lines 57-77 (the `WorkflowError` and `WorkflowRunResult` classes):

```python
# DELETE these two classes entirely:

class WorkflowError(BaseModel):
    """Details about a failed workflow item."""
    input_summary: str = ...
    error: str = ...

class WorkflowRunResult(ToolResult):
    """Result from workflow_run tool."""
    total: int = ...
    succeeded: int = ...
    failed: int = ...
    succeeded_items: list[str] = ...
    errors: list[WorkflowError] = ...
```

**Step 2: Remove imports from models/**init**.py**

In `src/sapguimcp/models/__init__.py`:

- Line 161: Remove `WorkflowError,` from the import block
- Line 163: Remove `WorkflowRunResult,` from the import block
- Line 321: Remove `"WorkflowError",` from `__all__`
- Line 323: Remove `"WorkflowRunResult",` from `__all__`

**Step 3: Run tests to verify nothing breaks**

Run: `cd /c/github/sapgui.mcp && python -m pytest unittests/ -x -q --ignore=unittests/test_sap_integration.py 2>&1 | tail -5`
Expected: All tests pass (no test imports WorkflowRunResult or WorkflowError)

**Step 4: Commit**

```bash
git add src/sapguimcp/models/workflow_models.py src/sapguimcp/models/__init__.py
git commit -m "refactor: remove WorkflowRunResult and WorkflowError models"
```

---

### Task 2: Remove `get_sampling_tools()` from sap_tool_impl.py

**Files:**

- Modify: `src/sapguimcp/tools/sap_tool_impl.py:1-2,40,378-395`

**Step 1: Update module docstring**

Change line 2 from:

```python
Standalone SAP tool implementations for use in MCP tools and sampling.
```

to:

```python
Standalone SAP tool implementations for use in MCP tools.
```

**Step 2: Remove `get_sampling_tools` from `__all__`**

Delete `"get_sampling_tools",` from the `__all__` list (line 40).

**Step 3: Delete the `get_sampling_tools()` function**

Delete lines 378-395 (the entire function).

**Step 4: Run tests**

Run: `cd /c/github/sapgui.mcp && python -m pytest unittests/ -x -q --ignore=unittests/test_sap_integration.py 2>&1 | tail -5`
Expected: All tests pass

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/sap_tool_impl.py
git commit -m "refactor: remove get_sampling_tools() from sap_tool_impl"
```

---

### Task 3: Remove `workflow_run` tool and `_execute_workflow_run` from workflow_tools.py

**Files:**

- Modify: `src/sapguimcp/tools/workflow_tools.py:7,34,41-126,261-276`

**Step 1: Update module docstring**

Change lines 7-8 from:

```python
Key feature: workflow_run uses server-side agent loops via ctx.sample()
to execute workflows without filling the client's context.
```

to:

```python
Workflows can be learned, saved, shared, and executed manually using
the prompts from workflow_list.
```

**Step 2: Remove the `get_sampling_tools` import**

Delete line 34:

```python
from sapguimcp.tools.sap_tool_impl import get_sampling_tools
```

**Step 3: Delete `_execute_workflow_run` function**

Delete the entire `_execute_workflow_run` function (lines 41-126).

**Step 4: Remove `WorkflowRunResult` and `WorkflowError` from imports**

In the import block (lines 16-25), remove `WorkflowError` and `WorkflowRunResult` from the imports:

```python
# BEFORE:
from sapguimcp.models import (
    Workflow,
    WorkflowDeleteResult,
    WorkflowError,
    WorkflowListResult,
    WorkflowRunResult,
    WorkflowSaveInput,
    WorkflowSaveResult,
    WorkflowSubmitResult,
)

# AFTER:
from sapguimcp.models import (
    Workflow,
    WorkflowDeleteResult,
    WorkflowListResult,
    WorkflowSaveInput,
    WorkflowSaveResult,
    WorkflowSubmitResult,
)
```

**Step 5: Delete the `workflow_run` tool registration**

Delete the `@mcp.tool` decorator and `workflow_run` function (lines 261-276):

```python
# DELETE this entire block:
    @mcp.tool(
        description=(
            "Execute a workflow for repetitive SAP tasks using server-side agent loops. "
            ...
        )
    )
    async def workflow_run(
        name: str,
        items: list[dict[str, str]],
        ctx: Context,
    ) -> WorkflowRunResult:
        return await _execute_workflow_run(name, items, ctx)
```

**Step 6: Clean up unused imports**

After removing `workflow_run`, check if `Context` is still used by other functions in the file. It is NOT used by any remaining tool (`workflow_list`, `workflow_save`, `workflow_submit`, `workflow_delete` — only `workflow_save` takes `Context | None` but as `_`).

Check: `workflow_save` has `_: Context | None = None` — so `Context` IS still needed. Keep the import.

**Step 7: Run tests**

Run: `cd /c/github/sapgui.mcp && python -m pytest unittests/ -x -q --ignore=unittests/test_sap_integration.py 2>&1 | tail -5`
Expected: All tests pass

**Step 8: Commit**

```bash
git add src/sapguimcp/tools/workflow_tools.py
git commit -m "refactor: remove workflow_run tool and sampling dependency"
```

---

### Task 4: Update README

**Files:**

- Modify: `README.md:485,489`

**Step 1: Remove `workflow_run` row from the table**

Delete line 485:

```markdown
| `workflow_run` | Run workflow in bulk (requires MCP Sampling support) |
```

**Step 2: Remove the sampling note**

Delete line 489:

```markdown
> **Note:** `workflow_run` requires MCP Sampling support. As of January 2026, Claude Desktop and Claude Code do NOT support this yet ([tracking issue](https://github.com/anthropics/claude-code/issues/1785)).
```

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: remove workflow_run and sampling note from README"
```

---

### Task 5: Delete sampling test docs

**Files:**

- Delete: `docs/testing/workflow-sampling-test.md`
- Delete: `docs/testing/workflow-sampling-copilot-setup.md`

**Step 1: Delete both files**

```bash
rm docs/testing/workflow-sampling-test.md
rm docs/testing/workflow-sampling-copilot-setup.md
```

**Step 2: Commit**

```bash
git add docs/testing/workflow-sampling-test.md docs/testing/workflow-sampling-copilot-setup.md
git commit -m "docs: remove sampling test documentation"
```

---

### Task 6: Update bulk-operations-performance.md

**Files:**

- Modify: `docs/bulk-operations-performance.md:94-119,134-136`

**Step 1: Remove section 3 (MCP Sampling)**

Delete lines 94-119 — the entire "### 3. MCP Sampling (workflow_run)" section including the trailing `---`.

**Step 2: Remove "For Context Optimization" recommendation**

Delete lines 134-136:

```markdown
### For Context Optimization

If context consumption is the bottleneck (not throughput), wait for MCP Sampling support in Claude Code, then use `workflow_run`.
```

**Step 3: Commit**

```bash
git add docs/bulk-operations-performance.md
git commit -m "docs: remove sampling section from bulk-operations performance doc"
```

---

### Task 7: Clean up comments in test_sap_integration.py

**Files:**

- Modify: `unittests/test_sap_integration.py:2165-2171,2276-2278`

**Step 1: Remove workflow_run comments**

In `unittests/test_sap_integration.py`, find and update the comment block around lines 2165-2171. Replace:

```python
    This is the "before" scenario that workflow_run with ctx.sample()
    is designed to optimize. Each iteration here adds to client context,
    whereas workflow_run would process all items server-side.

    Note: workflow_run with ctx.sample() cannot be tested here because
    the test client doesn't support MCP Sampling. This manual test
    documents the behavior that workflow_run would automate.
```

with:

```python
    This test documents the manual iteration pattern for EMMACL cases,
    showing navigation and context consumption per iteration.
```

**Step 2: Remove workflow_run context comparison comments**

Around lines 2276-2278, remove:

```python
    # With workflow_run using ctx.sample():
    # - 1 workflow_run call: ~1,500 tokens (call + result with 15 summaries)
    # Savings: ~16,500 tokens (91% reduction)
```

**Step 3: Run full test suite**

Run: `cd /c/github/sapgui.mcp && python -m pytest unittests/ -x -q --ignore=unittests/test_sap_integration.py 2>&1 | tail -5`
Expected: All tests pass

**Step 4: Commit**

```bash
git add unittests/test_sap_integration.py
git commit -m "docs: remove sampling references from integration test comments"
```

---

### Task 8: Final verification

**Step 1: Verify no remaining sampling references in src/**

Run: `grep -ri "sampling" src/`
Expected: No output (zero matches)

**Step 2: Verify no remaining `workflow_run` references in src/**

Run: `grep -ri "workflow_run" src/`
Expected: No output

**Step 3: Verify no remaining `get_sampling_tools` references**

Run: `grep -ri "get_sampling_tools" .`
Expected: Only matches in `docs/plans/` (historical design docs) — no matches in `src/` or `unittests/`

**Step 4: Run linting**

Run: `cd /c/github/sapgui.mcp && python -m pylint sapguimcp --disable=all --enable=E 2>&1 | tail -10`
Expected: No errors

**Step 5: Run type check**

Run: `cd /c/github/sapgui.mcp && python -m mypy --show-error-codes src/sapguimcp --strict 2>&1 | tail -5`
Expected: No new errors

**Step 6: Run formatting check**

Run: `cd /c/github/sapgui.mcp && python -m black --check src/sapguimcp unittests 2>&1 | tail -5`
Expected: All files OK
