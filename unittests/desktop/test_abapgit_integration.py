"""
Desktop backend integration tests for abapGit tools.

Tests verify that the abapGit pull and list operations work via SAP GUI COM automation.
Mirrors the WebGUI tests in unittests/webgui/test_abapgit_tools.py.
"""

import os
import sys
import uuid
from unittest.mock import MagicMock

import pytest

from sapguimcp.tools.abapgit_tools import _abapgit_list_repos, _abapgit_pull_via_api, _apply_list_filters
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
