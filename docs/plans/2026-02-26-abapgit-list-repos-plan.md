# abapGit List Repos Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `sap_abapgit_list_repos` tool that lists all registered abapGit repositories with their metadata, so the agent can discover repo names before calling `sap_abapgit_pull`.

**Architecture:** Extend the existing `Z_ABAPGIT_PULL` ABAP report with a `P_ACTION` parameter. When `LIST`, it outputs pipe-delimited repo metadata via WRITE statements. A new Python MCP tool parses that output and returns structured `AbapGitRepoInfo` objects.

**Tech Stack:** ABAP (abapGit API), Python (Pydantic, Playwright, FastMCP)

---

### Task 1: Add `AbapGitRepoInfo` and `AbapGitListResult` models

**Files:**

- Modify: `src/sapguimcp/models/abapgit_models.py`
- Modify: `src/sapguimcp/models/__init__.py`
- Test: `unittests/test_abapgit_tools.py`

**Step 1: Write the failing test**

Add to `unittests/test_abapgit_tools.py` in the unit tests section:

```python
def test_abapgit_repo_info_model() -> None:
    """Test that AbapGitRepoInfo model validates correctly."""
    from sapguimcp.models.abapgit_models import AbapGitRepoInfo

    repo = AbapGitRepoInfo(
        name="Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
        url="https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
        package="Z_PKG",
        branch="refs/heads/main",
        last_pull_at="20260225120000.0000000",
        last_pull_by="DEVELOPER",
        is_offline=False,
    )
    assert repo.name == "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
    assert repo.url == "https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
    assert repo.package == "Z_PKG"
    assert repo.branch == "refs/heads/main"
    assert repo.is_offline is False


def test_abapgit_list_result_model() -> None:
    """Test that AbapGitListResult model validates correctly."""
    from sapguimcp.models.abapgit_models import AbapGitListResult, AbapGitRepoInfo

    result = AbapGitListResult(
        success=True,
        repos=[
            AbapGitRepoInfo(
                name="Z_REPO_A",
                url="https://github.com/org/Z_REPO_A",
                package="Z_PKG_A",
                branch="refs/heads/main",
            ),
        ],
    )
    assert result.success
    assert len(result.repos) == 1
    assert result.repos[0].name == "Z_REPO_A"


def test_abapgit_list_result_empty() -> None:
    """Test empty list result."""
    from sapguimcp.models.abapgit_models import AbapGitListResult

    result = AbapGitListResult(success=True, repos=[])
    assert result.success
    assert result.repos == []
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_abapgit_tools.py::test_abapgit_repo_info_model -v`
Expected: FAIL with `ImportError: cannot import name 'AbapGitRepoInfo'`

**Step 3: Write minimal implementation**

Add to `src/sapguimcp/models/abapgit_models.py`:

```python
from sapguimcp.models.base import ToolResult


class AbapGitRepoInfo(BaseModel):
    """Metadata for a single registered abapGit repository."""

    name: str = Field(description="Repository name in SAP (e.g. Z_MY_REPO)")
    url: str = Field(description="Remote Git URL")
    package: str = Field(description="ABAP development package (devclass)")
    branch: str = Field(description="Git branch name (e.g. refs/heads/main)")
    last_pull_at: str | None = Field(default=None, description="Last pull timestamp (ABAP timestampl)")
    last_pull_by: str | None = Field(default=None, description="SAP user who last pulled")
    is_offline: bool = Field(default=False, description="Whether this is an offline repo")


class AbapGitListResult(ToolResult):
    """Result of listing registered abapGit repositories."""

    repos: list[AbapGitRepoInfo] = Field(default_factory=list, description="Registered repositories")
```

Add the import of `ToolResult` at the top of `abapgit_models.py` (already has `BaseModel` from pydantic).

Update `src/sapguimcp/models/__init__.py` to export the new types:

- Add `AbapGitRepoInfo` and `AbapGitListResult` to the import from `abapgit_models` and `__all__`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_abapgit_tools.py::test_abapgit_repo_info_model unittests/test_abapgit_tools.py::test_abapgit_list_result_model unittests/test_abapgit_tools.py::test_abapgit_list_result_empty -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/models/abapgit_models.py src/sapguimcp/models/__init__.py unittests/test_abapgit_tools.py
git commit -m "feat: add AbapGitRepoInfo and AbapGitListResult models"
```

---

### Task 2: Add pipe-delimited line parser and test it

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py`
- Test: `unittests/test_abapgit_tools.py`

**Step 1: Write the failing test**

Add to `unittests/test_abapgit_tools.py` in the unit tests section:

```python
def test_parse_repo_list_output() -> None:
    """Test parsing pipe-delimited WRITE output from Z_ABAPGIT_PULL LIST mode."""
    from sapguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = (
        "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY|https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
        "|$Z_PUBLIC_ABAPGIT|refs/heads/main|20260225120000.0000000|DEVELOPER|\n"
        "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY|https://github.com/Hochfrequenz/Z_PRIVATE_ABAPGIT_TEST_REPOSITORY"
        "|$Z_PRIVATE_ABAPGIT|refs/heads/main|20260224150000.0000000|ADMIN|"
    )
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 2
    assert repos[0].name == "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
    assert repos[0].url == "https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
    assert repos[0].package == "$Z_PUBLIC_ABAPGIT"
    assert repos[0].branch == "refs/heads/main"
    assert repos[0].last_pull_at == "20260225120000.0000000"
    assert repos[0].last_pull_by == "DEVELOPER"
    assert repos[0].is_offline is False
    assert repos[1].name == "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY"


def test_parse_repo_list_output_with_offline() -> None:
    """Test parsing a repo line with offline flag set."""
    from sapguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = "Z_OFFLINE_REPO|file:///path|$Z_OFFLINE|refs/heads/main|||X\n"
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 1
    assert repos[0].name == "Z_OFFLINE_REPO"
    assert repos[0].is_offline is True
    assert repos[0].last_pull_at is None
    assert repos[0].last_pull_by is None


def test_parse_repo_list_output_empty() -> None:
    """Test parsing empty output."""
    from sapguimcp.tools.abapgit_tools import parse_repo_list_output

    assert parse_repo_list_output("") == []
    assert parse_repo_list_output("   \n  \n") == []


def test_parse_repo_list_output_skips_garbage() -> None:
    """Test that non-repo lines (SAP UI text, headers) are skipped."""
    from sapguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = (
        "Some SAP header text\n"
        "Z_REPO|https://github.com/org/Z_REPO|$Z_PKG|refs/heads/main|20260225120000.0000000|DEV|\n"
        "Another random line\n"
    )
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 1
    assert repos[0].name == "Z_REPO"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_abapgit_tools.py::test_parse_repo_list_output -v`
Expected: FAIL with `ImportError: cannot import name 'parse_repo_list_output'`

**Step 3: Write minimal implementation**

Add to `src/sapguimcp/tools/abapgit_tools.py`:

```python
from sapguimcp.models.abapgit_models import AbapGitRepoInfo

def parse_repo_list_output(raw_output: str) -> list[AbapGitRepoInfo]:
    """Parse pipe-delimited WRITE output from Z_ABAPGIT_PULL LIST mode.

    Expected format per line: name|url|package|branch|deserialized_at|deserialized_by|offline
    Lines that don't match (headers, empty, UI noise) are silently skipped.
    """
    repos: list[AbapGitRepoInfo] = []
    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        # Validate: first part should look like a repo name, second like a URL
        name = parts[0].strip()
        url = parts[1].strip()
        if not name or not url or "://" not in url and not url.startswith("file:"):
            continue
        repos.append(
            AbapGitRepoInfo(
                name=name,
                url=url,
                package=parts[2].strip() if len(parts) > 2 else "",
                branch=parts[3].strip() if len(parts) > 3 else "",
                last_pull_at=parts[4].strip() or None if len(parts) > 4 else None,
                last_pull_by=parts[5].strip() or None if len(parts) > 5 else None,
                is_offline=parts[6].strip().upper() == "X" if len(parts) > 6 else False,
            )
        )
    return repos
```

Add `parse_repo_list_output` to `__all__` in `abapgit_tools.py`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_abapgit_tools.py::test_parse_repo_list_output unittests/test_abapgit_tools.py::test_parse_repo_list_output_with_offline unittests/test_abapgit_tools.py::test_parse_repo_list_output_empty unittests/test_abapgit_tools.py::test_parse_repo_list_output_skips_garbage -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py unittests/test_abapgit_tools.py
git commit -m "feat: add pipe-delimited repo list parser"
```

---

### Task 3: Add `sap_abapgit_list_repos` MCP tool implementation

**Files:**

- Modify: `src/sapguimcp/tools/abapgit_tools.py`

**Step 1: Add the list implementation function**

Add to `src/sapguimcp/tools/abapgit_tools.py`, after the `_abapgit_pull_via_api` function:

```python
from sapguimcp.models.abapgit_models import AbapGitListResult

async def _abapgit_list_repos() -> AbapGitListResult:
    """List all registered abapGit repositories via Z_ABAPGIT_PULL P_ACTION=LIST."""
    logger.info("Listing abapGit repositories")

    browser_manager = await get_browser_manager()
    page = await browser_manager.get_page()
    if not page:
        return AbapGitListResult(
            success=False,
            error="No active browser session. Call sap_login first.",
        )

    try:
        # Get OK-Code field
        okcode_result = await _get_okcode_field(page, "LIST")
        if isinstance(okcode_result, AbapGitActionResult):
            return AbapGitListResult(success=False, error=okcode_result.error)
        okcode_field = okcode_result

        # Enter transaction with LIST action
        tcode_with_params = "/nZ_ABAPGIT_PULL P_ACTION=LIST;"
        await page.bring_to_front()
        await page.wait_for_timeout(500)
        await okcode_field.click()
        await page.wait_for_timeout(200)
        await okcode_field.fill("")
        await okcode_field.fill(tcode_with_params)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        # Check if transaction was found
        status = await sap_read_status_bar_impl()
        status_msg = (status.message or "").lower()
        if "not found" in status_msg or "existiert nicht" in status_msg or "does not exist" in status_msg:
            return AbapGitListResult(
                success=False,
                error=(
                    "Transaction Z_ABAPGIT_PULL not found. "
                    "Ensure the report is deployed with LIST support. "
                    "See docs/plans/2026-02-26-abapgit-list-repos-design.md"
                ),
            )

        # Execute report with F8
        await page.keyboard.press("F8")
        await page.wait_for_timeout(3000)

        # Read the WRITE output from the screen via JavaScript
        raw_output = await page.evaluate("""
            () => {
                // Try to get text from the main content area (WRITE list output)
                const body = document.querySelector('#sapwd_main_window_root_contents') || document.body;
                return body.innerText || body.textContent || '';
            }
        """)

        if not raw_output:
            return AbapGitListResult(
                success=False,
                error="No output received from Z_ABAPGIT_PULL LIST mode",
            )

        repos = parse_repo_list_output(raw_output)
        logger.info("Found repositories", extra={"count": len(repos)})

        return AbapGitListResult(success=True, repos=repos)

    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("abapGit list repos failed")
        return AbapGitListResult(success=False, error=str(e))
```

**Step 2: Register the tool**

In `register_abapgit_tools()`, add before the existing `sap_abapgit_pull` registration:

```python
    @mcp.tool(
        annotations=ToolAnnotations(
            title="abapGit List Repositories",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        description=(
            "List all registered abapGit repositories with their metadata. "
            "Returns repo names, Git URLs, packages, branches, and last pull timestamps. "
            "Use this to discover the correct repo name before calling sap_abapgit_pull."
        ),
    )
    async def sap_abapgit_list_repos() -> AbapGitListResult:
        """
        List all registered abapGit repositories.

        Returns:
            AbapGitListResult with list of AbapGitRepoInfo objects

        Example:
            sap_abapgit_list_repos()
        """
        return await _abapgit_list_repos()
```

**Step 3: Commit**

```bash
git add src/sapguimcp/tools/abapgit_tools.py
git commit -m "feat: add sap_abapgit_list_repos MCP tool"
```

---

### Task 4: Extend the ABAP report with LIST mode

**Files:**

- Modify: `unittests/abapgit_repos/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY/src/z_abapgit_pull.prog.abap`

**Step 1: Add P_ACTION parameter and LIST logic**

Replace the full ABAP report with:

```abap
*&---------------------------------------------------------------------*
*& Report Z_ABAPGIT_PULL
*&---------------------------------------------------------------------*
  REPORT z_abapgit_pull.

* Selection screen with readable labels and F4 help
  SELECTION-SCREEN BEGIN OF BLOCK b1 WITH FRAME TITLE TEXT-001.
    PARAMETERS:
      p_action TYPE c LENGTH 4 DEFAULT 'PULL',  " Action: PULL or LIST
      p_repo   TYPE string LOWER CASE,           " Repository name
      p_trkorr TYPE trkorr.                       " Transport request (F4 available)
  SELECTION-SCREEN END OF BLOCK b1.

  SELECTION-SCREEN BEGIN OF BLOCK b2 WITH FRAME TITLE TEXT-002.
    PARAMETERS:
      p_user   TYPE string LOWER CASE,             " GitHub username
      p_token  TYPE string LOWER CASE.              " GitHub PAT (Personal Access Token)
  SELECTION-SCREEN END OF BLOCK b2.

  START-OF-SELECTION.

* --- LIST mode: output all registered repos as pipe-delimited lines ---
    IF p_action = 'LIST'.
      TRY.
          LOOP AT zcl_abapgit_repo_srv=>get_instance( )->list( ) INTO DATA(li_repo_list).
            DATA(lv_offline) = li_repo_list->is_offline( ).
            DATA(lv_offline_flag) = COND string( WHEN lv_offline = abap_true THEN 'X' ELSE '' ).
            DATA(lv_url) = COND string( WHEN lv_offline = abap_false
                                        THEN CAST zcl_abapgit_repo_online( li_repo_list )->get_url( )
                                        ELSE '' ).
            WRITE: / li_repo_list->get_name( ) NO-GAP,
                     '|' NO-GAP, lv_url NO-GAP,
                     '|' NO-GAP, li_repo_list->get_package( ) NO-GAP,
                     '|' NO-GAP, li_repo_list->ms_data-branch_name NO-GAP,
                     '|' NO-GAP, li_repo_list->ms_data-deserialized_at NO-GAP,
                     '|' NO-GAP, li_repo_list->ms_data-deserialized_by NO-GAP,
                     '|' NO-GAP, lv_offline_flag NO-GAP.
          ENDLOOP.
        CATCH cx_root INTO DATA(lx_list_error).
          MESSAGE e398(00) WITH lx_list_error->get_text( ) '' '' ''.
      ENDTRY.
      RETURN.
    ENDIF.

* --- PULL mode (existing logic, unchanged) ---
    IF p_repo IS INITIAL.
      MESSAGE e398(00) WITH 'P_REPO is required for PULL action' '' '' ''.
      RETURN.
    ENDIF.

    TRY.
        DATA lo_repo TYPE REF TO zcl_abapgit_repo_online.

        LOOP AT zcl_abapgit_repo_srv=>get_instance( )->list( iv_offline = abap_false ) INTO DATA(li_repo).
          IF li_repo->get_name( ) CS p_repo.
            lo_repo ?= li_repo.
            EXIT.
          ENDIF.
        ENDLOOP.

        IF lo_repo IS NOT BOUND.
          MESSAGE e398(00) WITH 'Repository not found:' p_repo '' ''.
          RETURN.
        ENDIF.

        IF p_user IS NOT INITIAL AND p_token IS NOT INITIAL.
          zcl_abapgit_login_manager=>set(
            iv_uri      = lo_repo->get_url( )
            iv_username = p_user
            iv_password = p_token ).
        ENDIF.

        DATA(ls_checks) = lo_repo->deserialize_checks( ).

        IF ls_checks-transport-required = abap_true AND p_trkorr IS INITIAL.
          MESSAGE e398(00) WITH 'Transport required. Provide P_TRKORR=' ls_checks-transport-type '' ''.
          RETURN.
        ENDIF.
        ls_checks-transport-transport = p_trkorr.

        " Auto-confirm all overwrite decisions (MCP automation requires non-interactive mode)
        " Decision values: ' ' = undecided, 'Y' = overwrite, 'N' = skip
        LOOP AT ls_checks-overwrite ASSIGNING FIELD-SYMBOL(<ls_overwrite>).
          <ls_overwrite>-decision = 'Y'.
        ENDLOOP.

        lo_repo->deserialize(
          is_checks = ls_checks
          ii_log    = NEW zcl_abapgit_log( ) ).

        MESSAGE s398(00) WITH 'Pull successful:' lo_repo->get_name( ) '' ''.

      CATCH cx_root INTO DATA(lx_error).
        MESSAGE e398(00) WITH lx_error->get_text( ) '' '' ''.
    ENDTRY.
```

Note: `p_repo` is no longer `OBLIGATORY` since LIST mode doesn't need it. Instead, a runtime check returns an error if `p_repo` is empty in PULL mode.

**Step 2: Commit**

```bash
git add unittests/abapgit_repos/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY/src/z_abapgit_pull.prog.abap
git commit -m "feat: extend Z_ABAPGIT_PULL with LIST mode"
```

---

### Task 5: Add integration test for `sap_abapgit_list_repos`

**Files:**

- Modify: `unittests/test_abapgit_tools.py`

**Step 1: Write the integration test**

Add to the integration tests section:

```python
@pytest.mark.anyio
async def test_abapgit_list_repos(sap_mcp_client: ClientSession) -> None:
    """
    Test listing registered abapGit repositories.

    Requires Z_ABAPGIT_PULL to be deployed with LIST support.
    Verifies that at least the known test repos are returned.
    """
    from sapguimcp.models.abapgit_models import AbapGitListResult

    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # List repos
    result = await call_tool_typed(sap_mcp_client, "sap_abapgit_list_repos", {}, AbapGitListResult)
    assert result.success, f"List failed: {result.error}"
    assert len(result.repos) > 0, "Expected at least one repo"

    # Check that known test repos are present
    repo_names = [r.name for r in result.repos]
    assert "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY" in repo_names, (
        f"Expected Z_PUBLIC_ABAPGIT_TEST_REPOSITORY in {repo_names}"
    )

    # Check that the public repo has expected metadata
    public_repo = next(r for r in result.repos if r.name == "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    assert "github.com" in public_repo.url
    assert public_repo.package  # Should have a package
    assert public_repo.is_offline is False
```

**Step 2: Commit**

```bash
git add unittests/test_abapgit_tools.py
git commit -m "test: add integration test for sap_abapgit_list_repos"
```

---

### Task 6: Deploy updated ABAP report to SAP and run integration test

**Step 1: Deploy the updated Z_ABAPGIT_PULL report**

Use `sap_abapgit_pull` to pull the updated report into SAP (since the report itself is in the test repo):

```
sap_abapgit_pull(repo="Z_PUBLIC_ABAPGIT_TEST_REPOSITORY", trkorr="<transport>")
```

If the report cannot self-update (because the `OBLIGATORY` flag on `p_repo` prevents calling with `P_ACTION=LIST` on the old version), manually update via SE38.

**Step 2: Run the integration test**

Run: `python -m pytest unittests/test_abapgit_tools.py::test_abapgit_list_repos -v`
Expected: PASS

**Step 3: Run all abapGit tests to verify nothing is broken**

Run: `python -m pytest unittests/test_abapgit_tools.py -v`
Expected: All tests PASS (existing pull tests should still work since P_ACTION defaults to PULL)
