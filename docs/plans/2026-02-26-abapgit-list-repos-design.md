# Design: `sap_abapgit_list_repos` Tool

**Date**: 2026-02-26
**Status**: Approved
**Problem**: No way to discover registered abapGit repositories — `sap_abapgit_pull` requires the exact SAP-internal repo name, which is undiscoverable without manually navigating the ZABAPGIT UI.

## Solution

Extend `Z_ABAPGIT_PULL` with a `P_ACTION` parameter and add a new MCP tool `sap_abapgit_list_repos`.

## ABAP Changes — Extend `Z_ABAPGIT_PULL`

Add `P_ACTION TYPE c LENGTH 4 DEFAULT 'PULL'` to the selection screen. When `P_ACTION = 'LIST'`:

- Loop through `zcl_abapgit_repo_srv=>get_instance( )->list( )` (both online and offline)
- WRITE one pipe-delimited line per repo with fields: `name|url|package|branch_name|deserialized_at|deserialized_by|offline`
- Return immediately (skip pull logic)

The existing pull logic runs unchanged when `P_ACTION = 'PULL'` (the default).

### Output format

One WRITE line per repo:

```
Z_PUBLIC_ABAPGIT_TEST_REPOSITORY|https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY|Z_PKG|refs/heads/main|20260225120000.0000000|DEVELOPER|
```

## Python Changes

### New model — `AbapGitRepoInfo` in `abapgit_models.py`

```python
class AbapGitRepoInfo(BaseModel):
    name: str
    url: str
    package: str
    branch: str
    last_pull_at: str | None = None
    last_pull_by: str | None = None
    is_offline: bool = False

class AbapGitListResult(ToolResult):
    repos: list[AbapGitRepoInfo] = []
```

### New tool — `sap_abapgit_list_repos` in `abapgit_tools.py`

- Calls `Z_ABAPGIT_PULL` with `P_ACTION=LIST` via OK-Code (same mechanism as pull)
- Presses F8 to execute
- Reads WRITE output from screen via `page.evaluate()` (JS text extraction — same approach as existing `verify_abap_report_content`)
- Parses pipe-delimited lines into `AbapGitRepoInfo` objects
- Returns `AbapGitListResult`
- Registered as `readOnly` in `register_abapgit_tools()`

### Screen reading strategy

After F8, SAP shows a classic WRITE list. Extract text via JavaScript that reads content from the report output area — reuse the JS-based extraction pattern from `verify_abab_report_content` in the existing abapgit_tools.py.

## Testing

- **Unit test**: pipe-delimited line parsing with sample data (offline, no SAP needed)
- **Integration test**: call `sap_abapgit_list_repos` against real SAP, verify known test repos appear with correct metadata
