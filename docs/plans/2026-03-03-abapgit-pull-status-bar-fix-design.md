# Fix: abapGit Pull "Status Unknown" Empty Status Bar

**Date:** 2026-03-03
**Status:** Approved

## Problem

`sap_abapgit_pull` consistently returns "status unknown: SAP status bar was empty" even when the pull actually succeeds. Users must manually call `sap_press_key(F8)` then `sap_read_status_bar` as a workaround.

### Root Cause

`_run_pull_and_check_errors()` uses hardcoded `wait_for_timeout` calls (3s after F8, 5s after Enter) that expire before `lo_repo->deserialize()` finishes. The ABAP `MESSAGE s398` only fires after deserialization completes. For any repo that takes longer than ~8 seconds to pull, the status bar is empty when read.

Additionally, a bare `Enter` press after the F8 wait was speculative (no confirmed popup to confirm) and risks re-executing the report on the selection screen.

### Evidence

- SAP shows a progress percentage during pull, confirming active network traffic during deserialization
- The `edit_helpers.py` module uses `wait_for_load_state("networkidle")` successfully for similar SAP wait-for-completion patterns (check/activate)
- Git blame shows the Enter press and hardcoded waits date from the initial commit with no subsequent validation

## Solution

### 1. Replace hardcoded waits with `networkidle`

In `_run_pull_and_check_errors()`, replace `wait_for_timeout(3000)` + Enter + `wait_for_timeout(5000)` with `wait_for_load_state("networkidle", timeout=120_000)`. This waits until SAP finishes processing (progress percentage network traffic stops) with a generous 120s ceiling.

### 2. Remove bare Enter press

The Enter press after F8 has no confirmed purpose. Transport and overwrite checks are handled programmatically in the ABAP code. Removing it eliminates the risk of accidentally re-executing the report.

### 3. Document F8 workaround in tool description

Add guidance to the `sap_abapgit_pull` tool description: if the tool reports "status unknown", call `sap_press_key('F8')` then `sap_read_status_bar` as a fallback.

## Scope

### Changed

- `abapgit_tools.py`: `_run_pull_and_check_errors()` — networkidle wait, remove Enter
- `abapgit_tools.py`: `sap_abapgit_pull` tool description — add workaround note

### Unchanged

- `z_abapgit_pull.prog.abap` — ABAP report works correctly
- `extract_status_bar.js` — JS extraction works when message exists
- `_analyze_pull_result()` — existing retry logic serves as safety net
- No new test data needed (fix is in wait strategy, not parsing)

## Risk

Low. `wait_for_load_state("networkidle")` is proven in this codebase. The 120s timeout prevents infinite hangs. A `TimeoutError` catch logs a warning and continues to status bar analysis (graceful degradation).
