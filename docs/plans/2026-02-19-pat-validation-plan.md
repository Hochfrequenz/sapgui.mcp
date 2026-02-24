# GitHub PAT Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Validate GitHub PATs on startup and fix the silent success bug in abapGit pull result analysis.

**Architecture:** Add `validate_github_pat()` to `abapgit_tools.py`, call it from `app_lifespan` in `server.py`. Change `_analyze_pull_result` fallback from success to failure. Follow existing patterns: `_check_cdp_available` for startup checks, `respx` for HTTP mocking, `@pytest.mark.anyio` for async tests.

**Tech Stack:** httpx (HTTP client), respx (HTTP mocking), pytest + anyio

---

### Task 1: `validate_github_pat()` — Mocked Tests

**Files:**

- Create: `unittests/test_pat_validation.py`

**Step 1: Write the failing tests**

```python
"""Tests for GitHub PAT validation."""

import pytest
import respx
from httpx import ConnectError, Response

from sapwebguimcp.tools.abapgit_tools import validate_github_pat


class TestValidateGithubPat:
    """Tests for validate_github_pat()."""

    @respx.mock
    @pytest.mark.anyio
    async def test_valid_pat(self) -> None:
        """Returns (True, username) for a valid PAT."""
        respx.get("https://api.github.com/user").mock(
            return_value=Response(200, json={"login": "test-user"})
        )
        valid, msg = await validate_github_pat("ghp_valid_token_123")
        assert valid is True
        assert msg == "test-user"

    @respx.mock
    @pytest.mark.anyio
    async def test_expired_pat(self) -> None:
        """Returns (False, 'Bad credentials') for a 401 response."""
        respx.get("https://api.github.com/user").mock(
            return_value=Response(401, json={"message": "Bad credentials"})
        )
        valid, msg = await validate_github_pat("ghp_expired_token_123")
        assert valid is False
        assert "Bad credentials" in msg

    @respx.mock
    @pytest.mark.anyio
    async def test_forbidden_pat(self) -> None:
        """Returns (False, ...) for a 403 response."""
        respx.get("https://api.github.com/user").mock(
            return_value=Response(403, json={"message": "Forbidden"})
        )
        valid, msg = await validate_github_pat("ghp_forbidden_token")
        assert valid is False
        assert "Forbidden" in msg

    @respx.mock
    @pytest.mark.anyio
    async def test_network_error(self) -> None:
        """Returns (False, 'GitHub API unreachable: ...') on connection error."""
        respx.get("https://api.github.com/user").mock(
            side_effect=ConnectError("Connection refused")
        )
        valid, msg = await validate_github_pat("ghp_any_token")
        assert valid is False
        assert "unreachable" in msg.lower()
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/test_pat_validation.py -v`
Expected: FAIL with `ImportError: cannot import name 'validate_github_pat'`

**Step 3: Commit failing tests**

```bash
git add unittests/test_pat_validation.py
git commit -m "test: add failing tests for validate_github_pat"
```

---

### Task 2: `validate_github_pat()` — Implementation

**Files:**

- Modify: `src/sapwebguimcp/tools/abapgit_tools.py` (add function near top, after imports)

**Step 1: Implement the function**

Add after the existing imports (line ~30) in `abapgit_tools.py`:

```python
import httpx

# ... (existing code) ...

async def validate_github_pat(pat: str) -> tuple[bool, str]:
    """
    Validate a GitHub PAT by calling GET /user.

    Returns:
        (True, github_username) if the token is valid.
        (False, error_message) if the token is invalid or unreachable.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {pat}"},
                timeout=5.0,
            )
        if resp.status_code == 200:
            login = resp.json().get("login", "unknown")
            return True, login
        msg = resp.json().get("message", f"HTTP {resp.status_code}")
        return False, msg
    except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
        return False, f"GitHub API unreachable: {exc}"
```

**Step 2: Run tests to verify they pass**

Run: `python -m pytest unittests/test_pat_validation.py -v`
Expected: All 4 tests PASS

**Step 3: Commit**

```bash
git add src/sapwebguimcp/tools/abapgit_tools.py
git commit -m "feat: add validate_github_pat function"
```

---

### Task 3: Real Integration Test — Expired PAT

**Files:**

- Modify: `unittests/test_pat_validation.py` (add test at bottom)

**Step 1: Write the real integration test**

Add to `test_pat_validation.py`:

```python
class TestValidateGithubPatReal:
    """Integration tests hitting real GitHub API."""

    @pytest.mark.anyio
    async def test_expired_pat_real(self) -> None:
        """Prove that GitHub returns 401 for a known expired token."""
        # This token was revoked on 2026-02-19.
        # It is safe to hardcode because it is already public and inactive.
        expired_pat = "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"
        valid, msg = await validate_github_pat(expired_pat)
        assert valid is False
        assert "Bad credentials" in msg
```

**Step 2: Run just this test to verify it passes**

Run: `python -m pytest unittests/test_pat_validation.py::TestValidateGithubPatReal -v`
Expected: PASS (real HTTP 401 from GitHub)

**Step 3: Commit**

```bash
git add unittests/test_pat_validation.py
git commit -m "test: add real integration test for expired PAT"
```

---

### Task 4: Startup Validation in `app_lifespan`

**Files:**

- Modify: `src/sapwebguimcp/server.py:88-108` (the `app_lifespan` function)

**Step 1: Write the failing test**

Add to `unittests/test_pat_validation.py`:

```python
import logging

from sapwebguimcp.server import app_lifespan


class TestStartupPatValidation:
    """Tests for PAT validation during server startup."""

    @respx.mock
    @pytest.mark.anyio
    async def test_startup_logs_valid_pat(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Startup logs [OK] when PAT is valid."""
        # Mock CDP check to succeed
        respx.get("http://localhost:9222/json/version").mock(
            return_value=Response(200, json={"Browser": "Chrome/120"})
        )
        # Mock GitHub API to succeed
        respx.get("https://api.github.com/user").mock(
            return_value=Response(200, json={"login": "hf-kklein"})
        )
        # Set a PAT in settings
        monkeypatch.setenv("ABAPGIT_PAT", "ghp_fake_valid_token")
        # Reset cached settings so monkeypatch takes effect
        from sapwebguimcp.models import config as config_mod
        monkeypatch.setattr(config_mod, "_settings", None)

        with caplog.at_level(logging.INFO):
            async with app_lifespan(None):  # type: ignore[arg-type]
                pass
        assert "[OK] GitHub PAT validated" in caplog.text
        assert "hf-kklein" in caplog.text

    @respx.mock
    @pytest.mark.anyio
    async def test_startup_logs_expired_pat(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Startup logs [ACTION REQUIRED] when PAT is expired."""
        # Mock CDP check to succeed
        respx.get("http://localhost:9222/json/version").mock(
            return_value=Response(200, json={"Browser": "Chrome/120"})
        )
        # Mock GitHub API to return 401
        respx.get("https://api.github.com/user").mock(
            return_value=Response(401, json={"message": "Bad credentials"})
        )
        monkeypatch.setenv("ABAPGIT_PAT", "ghp_fake_expired_token")
        from sapwebguimcp.models import config as config_mod
        monkeypatch.setattr(config_mod, "_settings", None)

        with caplog.at_level(logging.WARNING):
            async with app_lifespan(None):  # type: ignore[arg-type]
                pass
        assert "[ACTION REQUIRED]" in caplog.text
        assert "Bad credentials" in caplog.text

    @respx.mock
    @pytest.mark.anyio
    async def test_startup_skips_when_no_pat(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Startup skips PAT validation when no PAT is configured."""
        respx.get("http://localhost:9222/json/version").mock(
            return_value=Response(200, json={"Browser": "Chrome/120"})
        )
        monkeypatch.delenv("ABAPGIT_PAT", raising=False)
        monkeypatch.delenv("GITHUB_PAT", raising=False)
        from sapwebguimcp.models import config as config_mod
        monkeypatch.setattr(config_mod, "_settings", None)

        with caplog.at_level(logging.INFO):
            async with app_lifespan(None):  # type: ignore[arg-type]
                pass
        assert "GitHub PAT" not in caplog.text
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest unittests/test_pat_validation.py::TestStartupPatValidation -v`
Expected: FAIL (app_lifespan doesn't validate PAT yet)

**Step 3: Implement startup validation**

Modify `app_lifespan` in `server.py` (lines 88-108). Add after the CDP check (line 100), before `try: yield`:

```python
from sapwebguimcp.tools.abapgit_tools import validate_github_pat

# ... inside app_lifespan, after CDP check, before try/yield:

    # Validate GitHub PAT if configured (non-blocking, warns only)
    effective_pat = _settings.abapgit_pat or _settings.github_pat
    if effective_pat:
        pat_valid, pat_msg = await validate_github_pat(effective_pat)
        if pat_valid:
            logger.info("[OK] GitHub PAT validated (user: %s)", pat_msg)
        else:
            logger.warning(
                "[ACTION REQUIRED] GitHub PAT is invalid: %s. "
                "abapGit pulls will fail. Regenerate at https://github.com/settings/tokens",
                pat_msg,
            )
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest unittests/test_pat_validation.py::TestStartupPatValidation -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add unittests/test_pat_validation.py src/sapwebguimcp/server.py
git commit -m "feat: validate GitHub PAT on server startup"
```

---

### Task 5: Fix Silent Success in `_analyze_pull_result`

**Files:**

- Modify: `src/sapwebguimcp/tools/abapgit_tools.py:296-298`

**Step 1: Write the failing test**

Add to `unittests/test_pat_validation.py`:

```python
from unittest.mock import AsyncMock, patch

from sapwebguimcp.models.abapgit_models import AbapGitActionResult
from sapwebguimcp.tools.abapgit_tools import _analyze_pull_result


class TestAnalyzePullResultFallback:
    """Tests for the _analyze_pull_result silent success fix."""

    @pytest.mark.anyio
    async def test_empty_status_returns_failure(self) -> None:
        """Empty status bar should return failure, not success."""
        mock_status = type("Status", (), {"message": "", "type": "none"})()
        mock_page = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        with (
            patch(
                "sapwebguimcp.tools.abapgit_tools.sap_read_status_bar_impl",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
            patch(
                "sapwebguimcp.tools.abapgit_tools._check_screen_for_errors",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await _analyze_pull_result(mock_page, "TEST_REPO")

        assert result.success is False
        assert "unknown" in result.message.lower() or "empty" in result.message.lower()
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_pat_validation.py::TestAnalyzePullResultFallback -v`
Expected: FAIL (`assert result.success is False` fails because it currently returns True)

**Step 3: Fix the fallback**

Modify `abapgit_tools.py` lines 296-298. Replace:

```python
    # Return success - either with status or assume up to date
    result_msg = f"Pull completed. Status: {final_msg}" if final_msg else "Pull completed (repo may be up to date)."
    return AbapGitActionResult.success_result(action="pull", repo_name=repo, message=result_msg)
```

With:

```python
    # Treat ambiguous result as failure — empty status bar may mask auth errors
    result_msg = (
        f"Pull completed. Status: {final_msg}"
        if final_msg
        else "Pull status unknown: SAP status bar was empty after pull. "
        "This may indicate an authentication failure (expired PAT) "
        "or a status bar extraction issue. Check SAP manually."
    )
    if not final_msg:
        return AbapGitActionResult.failure_result(action="pull", repo_name=repo, error=result_msg)
    return AbapGitActionResult.success_result(action="pull", repo_name=repo, message=result_msg)
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_pat_validation.py::TestAnalyzePullResultFallback -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/sapwebguimcp/tools/abapgit_tools.py unittests/test_pat_validation.py
git commit -m "fix: treat empty status bar as failure in _analyze_pull_result"
```

---

### Task 6: Formatting, Linting, Full Test Suite

**Step 1: Run formatters**

```bash
python -m black src/ unittests/
python -m isort src/ unittests/
npm run format
```

**Step 2: Run linting**

```bash
python -m pylint src/sapwebguimcp/tools/abapgit_tools.py src/sapwebguimcp/server.py
```

**Step 3: Run full unit test suite (exclude E2E)**

```bash
python -m pytest unittests/ -v --ignore=unittests/test_abapgit_tools.py -x
python -m pytest unittests/test_pat_validation.py -v
```

**Step 4: Fix any issues, commit**

```bash
git add -A
git commit -m "style: formatting and lint fixes"
```

---

### Task 7: Create Branch and Push

**Step 1: Create feature branch and push**

```bash
git checkout -b feat/pat-validation
git push -u origin feat/pat-validation
```

**Step 2: Remove the KNOWN ISSUE comment from E2E test**

The comment added in `docs/abapgit-silent-success-comment` branch (lines 318-322 of
`test_abapgit_tools.py`) can be shortened now that the bug is fixed. Update to reference
the fix instead of documenting a known issue.
