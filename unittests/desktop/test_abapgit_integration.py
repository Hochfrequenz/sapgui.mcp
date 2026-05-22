"""
Desktop backend integration tests for abapGit tools.

Tests verify that the abapGit pull and list operations work via SAP GUI COM automation.
Mirrors the WebGUI tests in unittests/webgui/test_abapgit_tools.py.
"""

import os
import sys

import pytest

from sapguimcp.tools.abapgit_tools import _abapgit_list_repos, _abapgit_pull_via_api
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

DEFAULT_TRANSPORT = os.environ.get("SAP_TEST_TRANSPORT", "S4UK902008")


# ---------------------------------------------------------------------------
# Pull tests
# ---------------------------------------------------------------------------


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_pull_public_repo(backend) -> None:
    """Test pulling a public repository via COM automation."""
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
@pytest.mark.anyio
async def test_abapgit_pull_returns_status_message(backend) -> None:
    """Verify that pull returns an actual status message, not 'status unknown'."""
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
        f"Got ambiguous status: {result.message}. " "Wait should have captured the ABAP MESSAGE."
    )
    await go_home(backend)


@skip_no_sap
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


@skip_no_sap
@pytest.mark.anyio
async def test_abapgit_pull_without_trkorr_returns_transport_guidance(backend) -> None:
    """Test that pulling without trkorr returns actionable transport guidance."""
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
    result = await _abapgit_list_repos(backend)

    assert result.success, f"List failed: {result.error}"
    assert len(result.repos) > 0, "Expected at least one repo"

    repo_names = [r.name for r in result.repos]
    assert (
        "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY" in repo_names
    ), f"Expected Z_PUBLIC_ABAPGIT_TEST_REPOSITORY in {repo_names}"

    public_repo = next(r for r in result.repos if r.name == "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    assert "github.com" in public_repo.url
    assert public_repo.package
    assert public_repo.is_offline is False
    await go_home(backend)
