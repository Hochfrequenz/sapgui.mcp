"""
Desktop backend integration tests for abapGit tools.

Tests verify that the abapGit pull and list operations work via SAP GUI COM automation.
Mirrors the WebGUI tests in unittests/webgui/test_abapgit_tools.py.
"""

import os
import re
import sys
import uuid
from unittest.mock import MagicMock

import pytest

from sapguimcp.tools.abapgit_tools import (
    _abapgit_list_repos,
    _abapgit_pull_via_api,
    _apply_list_filters,
    _validate_branch,
)
from unittests.desktop.conftest import go_home, require_repo_registered, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

DEFAULT_TRANSPORT = os.environ.get("SAP_TEST_TRANSPORT", "")
skip_no_transport = pytest.mark.skipif(not DEFAULT_TRANSPORT, reason="SAP_TEST_TRANSPORT environment variable not set")


# ---------------------------------------------------------------------------
# Pull tests
# ---------------------------------------------------------------------------


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_public_repo(backend) -> None:
    """Test pulling a public repository via COM automation."""
    await require_repo_registered(backend, "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    result = await _abapgit_pull_via_api(
        backend,
        repo="Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
        trkorr=DEFAULT_TRANSPORT,
        username=None,
        pat=None,
    )

    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"
    await go_home(backend)


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_returns_status_message(backend) -> None:
    """Verify that pull returns an actual status message, not 'status unknown'."""
    await require_repo_registered(backend, "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    result = await _abapgit_pull_via_api(
        backend,
        repo="Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
        trkorr=DEFAULT_TRANSPORT,
        username=None,
        pat=None,
    )

    assert result.success, f"Pull failed: {result.error}"
    assert result.message is not None, "Expected a status message, got None"
    assert "unknown" not in (result.message or "").lower(), (
        f"Got ambiguous status: {result.message}. Wait should have captured the ABAP MESSAGE."
    )
    await go_home(backend)


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_private_repo_with_pat(backend) -> None:
    """Test pulling a private repository with PAT authentication."""
    actual_pat = os.environ.get("ABAPGIT_PAT")
    if not actual_pat:
        pytest.skip("ABAPGIT_PAT environment variable not set")

    result = await _abapgit_pull_via_api(
        backend,
        repo="Z_PRIVATE_ABAPGIT_TEST_REPOSITORY",
        trkorr=DEFAULT_TRANSPORT,
        username=None,
        pat=actual_pat,
    )

    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"
    await go_home(backend)


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_repo_not_found(backend) -> None:
    """Test that pulling a non-existent repository returns a clear error."""
    result = await _abapgit_pull_via_api(
        backend,
        repo="NONEXISTENT_REPO_12345_GIBBERISH",
        trkorr=DEFAULT_TRANSPORT,
        username=None,
        pat=None,
    )

    assert not result.success, f"Expected failure but got success: {result.message}"
    assert result.error is not None
    assert "not found" in result.error.lower() or "Repository" in result.error
    await go_home(backend)


# The following tests never pull anything: the selectors are guaranteed not to be registered, so the report
# stops with "Repository not found" before it touches any transport or object.


@skip_no_sap
@pytest.mark.anyio
@pytest.mark.parametrize(
    "repo",
    [
        pytest.param(f"ZZ-MCP-NOT-REGISTERED-{uuid.uuid4().hex[:8].upper()}", id="hyphenated-name"),
        pytest.param(f"https://github.com/example-org/zz-mcp-not-registered-{uuid.uuid4().hex[:8]}", id="https-url"),
    ],
)
async def test_abapgit_pull_accepts_hyphenated_name_and_url_and_reaches_report(backend, repo: str) -> None:
    """Hyphenated names and https URLs pass validation and reach the report, which reports them as unknown."""
    result = await _abapgit_pull_via_api(backend, repo=repo, trkorr=None, username=None, pat=None)

    assert not result.success
    assert result.error is not None
    assert "invalid repository" not in result.error.lower(), f"Rejected client-side: {result.error}"
    error = result.error.lower()
    assert "transaction" not in error, f"The pull transaction is missing: {result.error}"
    assert "repository not found" in error, f"Unexpected report answer: {result.error}"
    await go_home(backend)


@pytest.mark.anyio
async def test_abapgit_pull_injection_is_rejected_without_sap_call() -> None:
    """An OK-code injection attempt is rejected client-side; the backend is never touched."""
    backend = MagicMock()
    result = await _abapgit_pull_via_api(backend, repo="REPO; DROP TABLE;", trkorr=None, username=None, pat=None)

    assert not result.success
    assert result.error is not None
    assert result.error.startswith("Invalid repository")
    assert backend.mock_calls == []


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_pull_without_trkorr_returns_transport_guidance(backend) -> None:
    """Test that pulling without trkorr returns actionable transport guidance."""
    await require_repo_registered(backend, "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    result = await _abapgit_pull_via_api(
        backend,
        repo="Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
        trkorr=None,
        username=None,
        pat=None,
    )

    assert not result.success, (
        f"Expected failure (transport required) but got success: {result.message}. "
        "Does this SAP system not require transport requests?"
    )
    assert result.error is not None

    error_lower = result.error.lower()
    assert "transport" in error_lower, f"Expected 'transport' in error but got: {result.error}"
    assert "se09" in error_lower, f"Expected guidance mentioning 'SE09' in error but got: {result.error}"
    assert "trkorr" in error_lower, f"Expected 'trkorr' in error but got: {result.error}"
    await go_home(backend)


# ---------------------------------------------------------------------------
# Pull with a branch (#996)
#
# The test repository must not be pinned to a commit: a successful pull with a branch clears the pin and the
# client can neither read nor restore it (docs/SAP_TEST_PREREQUISITES.md).
# ---------------------------------------------------------------------------

BRANCH_TEST_REPO = "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
BRANCH_TEST_BRANCH = "test/branch-switch"


async def _repo_branch(backend) -> str:  # type: ignore[no-untyped-def]
    """The branch the test repository is on, read from a fresh list (not the cached one)."""
    listed = await _abapgit_list_repos(backend)
    await go_home(backend)
    assert listed.success, f"List failed: {listed.error}"
    return next(r for r in listed.repos if r.name == BRANCH_TEST_REPO).branch


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_pull_unknown_branch_leaves_branch_unchanged(backend) -> None:
    """An unknown branch is refused by the report before anything changes (no transport needed)."""
    await require_repo_registered(backend, BRANCH_TEST_REPO)
    before = await _repo_branch(backend)

    result = await _abapgit_pull_via_api(
        backend,
        repo=BRANCH_TEST_REPO,
        trkorr=None,
        username=None,
        pat=None,
        branch=f"zz-no-such-branch-{uuid.uuid4().hex[:8]}",
    )
    await go_home(backend)

    assert not result.success
    assert "Branch not found" in (result.error or ""), result.error
    assert await _repo_branch(backend) == before


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_pull_branch_failure_restores_previous_branch(backend) -> None:
    """A pull that fails after the switch (transport required) restores the previous branch."""
    await require_repo_registered(backend, BRANCH_TEST_REPO)
    before = await _repo_branch(backend)

    result = await _abapgit_pull_via_api(
        backend, repo=BRANCH_TEST_REPO, trkorr=None, username=None, pat=None, branch=BRANCH_TEST_BRANCH
    )
    await go_home(backend)

    try:
        if result.success:
            pytest.fail(
                f"Expected failure (transport required) but the pull succeeded: {result.message}. "
                "Does this SAP system not require transport requests?"
            )
        assert "transport" in (result.error or "").lower(), result.error
        assert await _repo_branch(backend) == before
    finally:
        if await _repo_branch(backend) != before:  # only reachable when the pull unexpectedly succeeded
            short = before.removeprefix("refs/heads/")
            await _abapgit_pull_via_api(
                backend, repo=BRANCH_TEST_REPO, trkorr=DEFAULT_TRANSPORT or None, username=None, pat=None, branch=short
            )
            await go_home(backend)


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_branch_switch_and_back(backend) -> None:
    """Pull the test branch (the switch persists), then pull the original branch again."""
    await require_repo_registered(backend, BRANCH_TEST_REPO)
    before = await _repo_branch(backend)
    validated = _validate_branch(before)
    if isinstance(validated, str):
        pytest.skip(f"The current branch {before!r} cannot be passed as `branch`, so it could not be restored")
    original_short, _ = validated

    try:
        switched = await _abapgit_pull_via_api(
            backend,
            repo=BRANCH_TEST_REPO,
            trkorr=DEFAULT_TRANSPORT,
            username=None,
            pat=None,
            branch=BRANCH_TEST_BRANCH,
        )
        await go_home(backend)
        assert switched.success, f"Pull with branch failed: {switched.error}"
        assert switched.branch == f"refs/heads/{BRANCH_TEST_BRANCH}"
        assert await _repo_branch(backend) == f"refs/heads/{BRANCH_TEST_BRANCH}"
    finally:
        restored = await _abapgit_pull_via_api(
            backend,
            repo=BRANCH_TEST_REPO,
            trkorr=DEFAULT_TRANSPORT,
            username=None,
            pat=None,
            branch=original_short,
        )
        await go_home(backend)
        assert restored.success, (
            f"Restoring branch {before} failed, the test repository may be left on {BRANCH_TEST_BRANCH}: "
            f"{restored.error}"
        )
        assert restored.branch == before
        assert await _repo_branch(backend) == before


# ---------------------------------------------------------------------------
# Pull by key
# ---------------------------------------------------------------------------


async def _test_repo(backend):  # type: ignore[no-untyped-def]
    """The test repository as listed now (fresh list); its key must be a 12-digit string."""
    listed = await _abapgit_list_repos(backend)
    await go_home(backend)
    assert listed.success, f"List failed: {listed.error}"
    repo = next(r for r in listed.repos if r.name == BRANCH_TEST_REPO)
    assert repo.key is not None
    assert re.fullmatch(r"[0-9]{12}", repo.key), "the listed key is not 12 digits"
    return repo


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_by_key(backend) -> None:
    """Pull the public test repository by the key from the list."""
    await require_repo_registered(backend, BRANCH_TEST_REPO)
    repo = await _test_repo(backend)
    result = await _abapgit_pull_via_api(
        backend, repo=None, trkorr=DEFAULT_TRANSPORT, username=None, pat=None, key=repo.key
    )
    await go_home(backend)
    assert result.success, f"Pull by key failed: {result.error}"
    assert result.repo_name == BRANCH_TEST_REPO


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_by_key_with_branch(backend) -> None:
    """Pull by key on the test branch, then by key on the original branch to restore it."""
    await require_repo_registered(backend, BRANCH_TEST_REPO)
    repo = await _test_repo(backend)
    before = repo.branch
    validated = _validate_branch(before)
    if isinstance(validated, str):
        pytest.skip(f"The current branch {before!r} cannot be passed as `branch`, so it could not be restored")
    original_short, _ = validated

    try:
        switched = await _abapgit_pull_via_api(
            backend,
            repo=None,
            trkorr=DEFAULT_TRANSPORT,
            username=None,
            pat=None,
            branch=BRANCH_TEST_BRANCH,
            key=repo.key,
        )
        await go_home(backend)
        assert switched.success, f"Pull by key with branch failed: {switched.error}"
        assert switched.branch == f"refs/heads/{BRANCH_TEST_BRANCH}"
        assert await _repo_branch(backend) == f"refs/heads/{BRANCH_TEST_BRANCH}"
    finally:
        restored = await _abapgit_pull_via_api(
            backend,
            repo=None,
            trkorr=DEFAULT_TRANSPORT,
            username=None,
            pat=None,
            branch=original_short,
            key=repo.key,
        )
        await go_home(backend)
        assert restored.success, (
            f"Restoring branch {before} failed, the test repository may be left on {BRANCH_TEST_BRANCH}: "
            f"{restored.error}"
        )
        assert restored.branch == before
        assert await _repo_branch(backend) == before


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_pull_by_unknown_key(backend) -> None:
    """An unknown key is reported by the report, needs no transport and changes nothing."""
    result = await _abapgit_pull_via_api(backend, repo=None, trkorr=None, username=None, pat=None, key="999999999999")
    await go_home(backend)
    assert not result.success
    assert "Repository not found: key 999999999999 (online only)" in (result.error or "")
    assert result.repo_name == "key 999999999999"


@skip_no_sap
@skip_no_transport
@pytest.mark.anyio
async def test_abapgit_pull_by_key_updates_last_pull(backend) -> None:
    """The key binds the repository it belongs to: its last pull time moves, its package stays."""
    await require_repo_registered(backend, BRANCH_TEST_REPO)
    before = await _test_repo(backend)
    result = await _abapgit_pull_via_api(
        backend, repo=None, trkorr=DEFAULT_TRANSPORT, username=None, pat=None, key=before.key
    )
    await go_home(backend)
    assert result.success, f"Pull by key failed: {result.error}"
    after = await _test_repo(backend)
    assert after.key == before.key
    assert after.package == before.package
    assert after.last_pull_at is not None
    assert before.last_pull_at is None or after.last_pull_at > before.last_pull_at


# ---------------------------------------------------------------------------
# List tests
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_list_repos(backend) -> None:
    """Test listing registered abapGit repositories via COM screen text reading."""
    # Where the repo is not registered the test skips: the assertion below would otherwise fail on an
    # environment gap, and must not pass vacuously either.
    await require_repo_registered(backend, "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    result = await _abapgit_list_repos(backend)

    assert result.success, f"List failed: {result.error}"
    assert len(result.repos) > 0, "Expected at least one repo"

    repo_names = [r.name for r in result.repos]
    assert "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY" in repo_names, (
        f"Expected Z_PUBLIC_ABAPGIT_TEST_REPOSITORY in {repo_names}"
    )

    public_repo = next(r for r in result.repos if r.name == "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    assert "github.com" in public_repo.url
    assert public_repo.package
    assert public_repo.is_offline is False
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_list_repos_filters_and_counts(backend) -> None:
    """One read-only list call; the filters and counts are applied to it as the tool does (#997).

    The package is picked from the unfiltered list, so the test works on any system that has a repository.
    """
    raw = await _abapgit_list_repos(backend)
    assert raw.success, f"List failed: {raw.error}"
    assert raw.repos, "Expected at least one repo"
    assert raw.total_count is not None
    assert raw.total_count >= len(raw.repos)

    everything = _apply_list_filters(raw, name="*")
    assert everything.matched_count == len(raw.repos), "name='*' must equal the unfiltered count"
    assert everything.total_count == raw.total_count

    package = raw.repos[0].package
    by_package = _apply_list_filters(raw, package=package)
    assert by_package.matched_count >= 1
    # A plain value is a substring, so packages that merely contain it match as well.
    assert all(package.casefold() in r.package.casefold() for r in by_package.repos), "only matching packages"
    assert any(r.name == raw.repos[0].name for r in by_package.repos)
    assert by_package.matched_count <= by_package.total_count == raw.total_count

    compact = _apply_list_filters(raw, package=package, compact=True)
    assert all(set(r.model_dump()) == {"name", "package", "key"} for r in compact.repos)
    await go_home(backend)
