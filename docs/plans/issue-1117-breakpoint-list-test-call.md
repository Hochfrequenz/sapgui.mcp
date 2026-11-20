# Issue #1117: test_breakpoint_list_prog calls the grid reader with the wrong arguments

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `test_breakpoint_list_prog` calls `_read_bp_grid_and_close_com` with the session only, the way the tool
`sap_breakpoint_list` does, so the live test reaches SAP's answer instead of failing with a `TypeError`.

**Architecture:** Test-only change. `_read_bp_grid_and_close_com(session)` in
`src/sapguimcp/tools/breakpoint_tools.py:166` takes one parameter and returns all grid rows; filtering by object is
done afterwards by `_filter_bp_rows(rows, object_type, object_name, method_name)`, which the test already calls. The
tool calls the helper correctly (`breakpoint_tools.py:975`). `breakpoint_tools.py` stays unchanged.

**Tech Stack:** Python, pytest (`-m integration` for live SAP GUI tests).

**Spec:** GitHub issue #1117.

## Global Constraints

- Leave `src/sapguimcp/tools/breakpoint_tools.py` unchanged (issue: "Leave `breakpoint_tools.py` unchanged").
- Out of scope: `test_breakpoint_set_prog_by_line` and `test_breakpoint_set_and_delete_roundtrip_prog` (#1025).
- Public repository: no system aliases, hostnames or user paths in commits or the PR body.
- This sprint has no SAP access: the live test cannot be run here. The live check on both systems stays open and is
  named in the PR body.

## Review Focus

- The call site is the only wrong call: a search for `_read_bp_grid_and_close_com` lists the definition, the tool's
  correct call and the test's call, nothing else. An offline AST guard that binds every call in the live tests to the
  helper's signature was considered and left out: it would add parser logic to guard a one-line test fix.

---

### Task 1: Call the grid reader with the session only

**Files:**

- Modify: `unittests/desktop/test_breakpoint_tools_integration.py:89`

**Interfaces:**

- Consumes: `_read_bp_grid_and_close_com(session: Any) -> tuple[list[dict[str, str]], str]` (unchanged).

**Task without a failing test first** (listed as such in the PR body): no exception of the test rule applies. The
task changes the failing test itself, a live SAP GUI integration test (`skip_no_sap`, `pytest.mark.integration`);
without SAP access it can be neither seen failing nor seen passing here. The defect is shown offline instead (Step 1).

- [ ] **Step 1: Show the defect offline**

Done by the orchestrating worker before the task starts (not committed): a scratch pytest file outside the
repository calls `_read_bp_grid_and_close_com(MagicMock(), "PROG", "ZREPORT", None)` and expects the `TypeError`
`takes 1 positional argument but 4 were given`; a second case calls it with the mock session only and expects a
`(rows, error)` tuple. Run through the pytest run prefix. Expected: both cases pass, which shows the four-argument
call fails and the one-argument call reaches the helper's body.

- [ ] **Step 2: Change the call**

Line 89 becomes:

```python
rows, read_err = await backend.com.run(lambda: _read_bp_grid_and_close_com(session))
```

Line 92 (`_filter_bp_rows(rows, "PROG", TEST_REPORT, None)`) stays as it is.

- [ ] **Step 3: Check collection and lint of the file**

Run: `bash <helper> run --prefix 3 --collect-only -q unittests/desktop/test_breakpoint_tools_integration.py`
Expected: exit 0, four tests collected, nothing executed. (The test gate runs `-m "not integration"`, which deselects
the whole file; never run this file with `-m integration` in this sprint.)

Run: `bash <helper> run --prefix 0 check unittests/desktop/test_breakpoint_tools_integration.py`
Expected: `All checks passed!`

Run: `bash <helper> run --prefix 0 format --check unittests/desktop/test_breakpoint_tools_integration.py`
Expected: `1 file already formatted`

- [ ] **Step 4: Commit**

```bash
git add unittests/desktop/test_breakpoint_tools_integration.py
git commit -m 'fix(#1117): test_breakpoint_list_prog calls the grid reader with the session only' -m 'Bugspecht-Sprint: bs-20261120-0924-rfw3'
```
