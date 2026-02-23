# Design: GitHub PAT Validation for abapGit

## Problem

The `sap_abapgit_pull` tool silently succeeds when the GitHub PAT is expired or invalid.
The ABAP report catches the authentication error (`cx_root`), sends `MESSAGE e398`, but
`extract_status_bar.js` fails to capture it. The fallback logic in `_analyze_pull_result`
treats an empty status bar as success ("repo may be up to date"), masking the real error.

Users only discover the problem when SE38 source code doesn't match the expected marker —
a confusing failure far removed from the root cause.

## Solution

Two complementary fixes:

1. **Startup PAT validation** — validate the PAT via GitHub API on server startup
2. **Fix silent success** — change `_analyze_pull_result` fallback from success to failure

## Changes

### 1. Startup Validation (`server.py`)

In `app_lifespan`, after the CDP check, validate the effective PAT:

```python
effective_pat = settings.abapgit_pat or settings.github_pat
if effective_pat:
    valid, msg = await validate_github_pat(effective_pat)
    if valid:
        logger.info("[OK] GitHub PAT validated", github_user=msg)
    else:
        logger.warning(
            "[ACTION REQUIRED] GitHub PAT is invalid: %s. "
            "abapGit pulls will fail. Regenerate at "
            "https://github.com/settings/tokens", msg
        )
```

- Non-blocking: a bad PAT logs a warning but does not prevent server startup.
- Uses `httpx.AsyncClient` with a 5-second timeout.
- Calls `GET https://api.github.com/user` with `Authorization: token <PAT>`.
- Returns `(True, username)` on 200, `(False, error_message)` on 401 or network error.

### 2. New Function: `validate_github_pat()` (`abapgit_tools.py`)

```python
async def validate_github_pat(pat: str) -> tuple[bool, str]:
    """Validate a GitHub PAT by calling GET /user. Returns (valid, message)."""
```

- Lives in `abapgit_tools.py` alongside the pull logic it protects.
- HTTP 200 → `(True, login_name)`
- HTTP 401 → `(False, "Bad credentials")`
- HTTP 403 → `(False, "Forbidden — token may lack required scopes")`
- Network error → `(False, "GitHub API unreachable: <detail>")`

### 3. Fix Silent Success (`_analyze_pull_result`)

Change the fallback at the end of `_analyze_pull_result` (line ~298):

```python
# BEFORE: silent success
result_msg = "Pull completed (repo may be up to date)."
return AbapGitActionResult.success_result(...)

# AFTER: explicit failure
result_msg = (
    "Pull status unknown: SAP status bar was empty after pull. "
    "This may indicate an authentication failure (expired PAT) "
    "or a status bar extraction issue. Check SAP manually."
)
return AbapGitActionResult.failure_result(...)
```

### 4. Tests

| Test                                                    | Type                    | What it verifies                                                          |
| ------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------- |
| `test_validate_github_pat_expired_real`                 | Integration (real HTTP) | Hardcoded expired token hits GitHub API, gets 401, returns `(False, ...)` |
| `test_validate_github_pat_expired_mock`                 | Unit (respx mock)       | Mocked 401 response returns `(False, "Bad credentials")`                  |
| `test_validate_github_pat_valid_mock`                   | Unit (respx mock)       | Mocked 200 response returns `(True, "test-user")`                         |
| `test_validate_github_pat_network_error_mock`           | Unit (respx mock)       | Mocked connection error returns `(False, "GitHub API unreachable: ...")`  |
| `test_analyze_pull_result_empty_status_returns_failure` | Unit (mock)             | Empty status bar no longer returns success                                |

The real integration test uses the known expired token `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`
to prove the 401 detection works against actual GitHub infrastructure.

## Assumptions

- `httpx` is already a project dependency (used in feedback_tools.py).
- `respx` is already a test dependency (in pyproject.toml).
- The expired PAT `ghp_q7bKiC...` will remain revoked (safe to hardcode in tests).
- GitHub API rate limits for unauthenticated/invalid-token requests are generous enough
  for CI (60/hour per IP).
