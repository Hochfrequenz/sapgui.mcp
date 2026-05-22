# abapGit Pull Status Bar Fix — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix `sap_abapgit_pull` returning "status unknown: SAP status bar was empty" on successful pulls by replacing hardcoded waits with `networkidle`.

**Architecture:** Replace `wait_for_timeout(3000)` + bare Enter + `wait_for_timeout(5000)` in `_run_pull_and_check_errors()` with `wait_for_load_state("networkidle", timeout=120_000)`. Remove the stale Enter press. Add workaround note to the tool description.

**Tech Stack:** Python, Playwright (`wait_for_load_state`), pytest + AsyncMock for unit tests.

---

### Task 1: Update the unit test for `_run_pull_and_check_errors` behavior

**Files:**

- Modify: `unittests/test_pat_validation.py` (add new test class at end of file)

**Step 1: Write the failing test**

Add a new test class at the bottom of `unittests/test_pat_validation.py` that verifies `_run_pull_and_check_errors` calls `wait_for_load_state("networkidle")` instead of hardcoded waits, and does NOT press Enter:

```python
class TestRunPullAndCheckErrors:
    """Tests for _run_pull_and_check_errors networkidle wait behavior."""

    @pytest.mark.anyio
    async def test_uses_networkidle_instead_of_hardcoded_waits(self) -> None:
        """After F8, should wait for networkidle instead of hardcoded timeouts."""
        from unittest.mock import AsyncMock, call, patch

        from sapguimcp.tools.abapgit_tools import _run_pull_and_check_errors

        mock_page = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        with patch(
            "sapguimcp.tools.abapgit_tools._handle_popup_error",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await _run_pull_and_check_errors(mock_page, "TEST_REPO")

        # Should press F8 to execute the report
        mock_page.keyboard.press.assert_any_call("F8")

        # Should wait for networkidle (not hardcoded timeouts)
        mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=120_000)

        # Should NOT press Enter (stale, risks re-executing report)
        enter_calls = [c for c in mock_page.keyboard.press.call_args_list if c == call("Enter")]
        assert enter_calls == [], f"Expected no Enter press, got {enter_calls}"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_pat_validation.py::TestRunPullAndCheckErrors -v`
Expected: FAIL — current code uses `wait_for_timeout` not `wait_for_load_state`, and presses Enter.

---

### Task 2: Fix `_run_pull_and_check_errors` to use networkidle

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py:390-402`

**Step 1: Replace the function body**

In `src/sapguimcp/tools/abapgit_tools.py`, replace `_run_pull_and_check_errors` (lines 390-402):

Old:

```python
async def _run_pull_and_check_errors(page: Page, repo: str) -> AbapGitActionResult | None:
    """Execute F8, confirm dialog, and check for popup errors. Returns error if found."""
    # Execute report with F8 and check for popup errors
    await page.keyboard.press("F8")
    await page.wait_for_timeout(3000)
    popup_result = await _handle_popup_error(page, repo)
    if popup_result:
        return popup_result

    # Confirm dialog and check again
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(5000)
    return await _handle_popup_error(page, repo)
```

New:

```python
async def _run_pull_and_check_errors(page: Page, repo: str) -> AbapGitActionResult | None:
    """Execute F8 and wait for SAP to finish processing. Returns error if found."""
    await page.keyboard.press("F8")
    try:
        await page.wait_for_load_state("networkidle", timeout=120_000)
    except TimeoutError:
        logger.warning("networkidle timeout after F8 — pull may still be running")

    return await _handle_popup_error(page, repo)
```

**Step 2: Run the test to verify it passes**

Run: `python -m pytest unittests/test_pat_validation.py::TestRunPullAndCheckErrors -v`
Expected: PASS

**Step 3: Run all related unit tests**

Run: `python -m pytest unittests/test_pat_validation.py unittests/test_abapgit_tools.py -v --ignore=unittests/test_sap_integration.py -k "not sap_mcp_client"`
Expected: All pass (existing tests for `_analyze_pull_result`, model tests, parser tests).

**Step 4: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py unittests/test_pat_validation.py
git commit -m "fix: use networkidle wait in abapgit pull instead of hardcoded timeouts

Replace wait_for_timeout(3s+5s) with wait_for_load_state('networkidle')
in _run_pull_and_check_errors. Remove stale Enter press that risked
re-executing the report on the selection screen.

Fixes: sap_abapgit_pull returning 'status unknown: SAP status bar was
empty' on successful pulls when deserialization exceeds 8 seconds."
```

---

### Task 3: Update the tool description with workaround note

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py:929-933`

**Step 1: Update the description**

In `src/sapguimcp/tools/abapgit_tools.py`, change the `sap_abapgit_pull` tool description (line 929-933):

Old:

```python
        description=(
            "Pull changes from a remote git repository using abapGit API. "
            "Uses the Z_ABAPGIT_PULL report/transaction for reliable execution. "
            "WARNING: This overwrites local ABAP objects with remote versions."
        ),
```

New:

```python
        description=(
            "Pull changes from a remote git repository using abapGit API. "
            "Uses the Z_ABAPGIT_PULL report/transaction for reliable execution. "
            "WARNING: This overwrites local ABAP objects with remote versions. "
            "If the tool reports 'status unknown', call sap_press_key('F8') "
            "followed by sap_read_status_bar() as a workaround."
        ),
```

**Step 2: Run unit tests to verify nothing broke**

Run: `python -m pytest unittests/test_pat_validation.py unittests/test_abapgit_tools.py -v -k "not sap_mcp_client"`
Expected: All pass.

**Step 3: Run formatting and linting**

Run: `python -m black src/sapguimcp/tools/abapgit_tools.py unittests/test_pat_validation.py && python -m isort src/sapguimcp/tools/abapgit_tools.py unittests/test_pat_validation.py`
Expected: Files formatted (or already compliant).

Run: `python -m pylint src/sapguimcp/tools/abapgit_tools.py`
Expected: No new errors.

**Step 4: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py
git commit -m "docs: add F8 workaround note to sap_abapgit_pull description"
```

---

### Task 4: Update the stale comment in the E2E test

**Files:**

- Modify: `unittests/test_abapgit_tools.py:434-438`

**Step 1: Update the comment**

In `unittests/test_abapgit_tools.py`, the comment at lines 434-438 references the old behavior ("treats empty status bar as success"). Update it:

Old:

```python
    # KNOWN ISSUE: _analyze_pull_result treats empty status bar as success.
    # If the PAT is expired (HTTP 401), the ABAP report catches cx_root and
    # sends MESSAGE e398, but extract_status_bar.js may fail to capture it,
    # causing pull_result.success=True even though the pull didn't update code.
    # The real failure then only surfaces in step 4 (source code mismatch).
    # If this test fails at the assert below, check ABAPGIT_PAT validity first.
```

New:

```python
    # NOTE: If this test fails at the assert below, check ABAPGIT_PAT validity first.
    # An expired PAT causes cx_root in ABAP which may surface as a pull error.
```

**Step 2: Run formatting**

Run: `python -m black unittests/test_abapgit_tools.py && python -m isort unittests/test_abapgit_tools.py`

**Step 3: Commit**

```bash
git add unittests/test_abapgit_tools.py
git commit -m "chore: update stale comment in abapgit E2E test"
```

---

### Task 5: Add integration test verifying pull returns success with status message

This test runs against a real SAP system (auto-skipped on non-SAP machines via `sap_mcp_client` fixture).
It validates the fix end-to-end: a pull that previously returned "status unknown" should now return a
proper success message because `networkidle` waits for deserialization to complete.

**Files:**

- Modify: `unittests/test_abapgit_tools.py` (add new test after `test_abapgit_pull_public_repo`)

**Step 1: Add the integration test**

Add the following test after `test_abapgit_pull_public_repo` (around line 320) in `unittests/test_abapgit_tools.py`:

```python
@pytest.mark.anyio
async def test_abapgit_pull_returns_status_message(sap_mcp_client: ClientSession) -> None:
    """
    Verify that pull returns an actual status message, not 'status unknown'.

    This is a regression test for the bug where hardcoded waits expired before
    lo_repo->deserialize() finished, leaving the status bar empty.
    After the fix (networkidle wait), the tool should always report a status message
    on success — either 'Pull successful:' from ABAP or a clear error.
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull public repository
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
            "trkorr": TEST_REPOS["public"]["trkorr"],
        },
        AbapGitActionResult,
    )

    # The fix ensures we wait for deserialization to complete.
    # Result should be a clear success with a message, NOT "status unknown".
    assert result.success, f"Pull failed: {result.error}"
    assert result.message is not None, "Expected a status message, got None"
    assert "unknown" not in (result.message or "").lower(), (
        f"Got ambiguous status: {result.message}. "
        "networkidle wait should have captured the ABAP MESSAGE."
    )
```

**Step 2: Run formatting**

Run: `python -m black unittests/test_abapgit_tools.py && python -m isort unittests/test_abapgit_tools.py`

**Step 3: Commit**

```bash
git add unittests/test_abapgit_tools.py
git commit -m "test: add integration test verifying pull returns status message

Regression test for the empty status bar bug. Asserts that after the
networkidle fix, sap_abapgit_pull returns a proper success message
instead of 'status unknown'."
```

---

### Task 6: Add unit test for networkidle timeout graceful degradation

This test verifies that if `wait_for_load_state` times out (e.g., for an extremely long pull or
unexpected network behavior), the function degrades gracefully — logs a warning and continues to
the popup check instead of crashing.

**Files:**

- Modify: `unittests/test_pat_validation.py` (add to `TestRunPullAndCheckErrors` class)

**Step 1: Write the test**

Add to the `TestRunPullAndCheckErrors` class in `unittests/test_pat_validation.py`:

```python
    @pytest.mark.anyio
    async def test_networkidle_timeout_degrades_gracefully(self) -> None:
        """If networkidle times out, should log warning and continue (not crash)."""
        from unittest.mock import AsyncMock, patch

        from sapguimcp.tools.abapgit_tools import _run_pull_and_check_errors

        mock_page = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock(side_effect=TimeoutError("networkidle timeout"))

        with patch(
            "sapguimcp.tools.abapgit_tools._handle_popup_error",
            new_callable=AsyncMock,
            return_value=None,
        ):
            # Should NOT raise — timeout is caught and logged
            result = await _run_pull_and_check_errors(mock_page, "TEST_REPO")

        assert result is None  # No popup error found, continues to _analyze_pull_result
```

**Step 2: Run the test**

Run: `python -m pytest unittests/test_pat_validation.py::TestRunPullAndCheckErrors -v`
Expected: Both tests in the class PASS.

**Step 3: Run full test suite and formatting**

Run: `python -m pytest unittests/test_pat_validation.py unittests/test_abapgit_tools.py -v -k "not sap_mcp_client"`
Expected: All pass.

Run: `python -m black unittests/test_pat_validation.py && python -m isort unittests/test_pat_validation.py`

**Step 4: Commit**

```bash
git add unittests/test_pat_validation.py
git commit -m "test: verify networkidle timeout degrades gracefully in abapgit pull"
```
