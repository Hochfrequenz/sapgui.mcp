"""
Desktop backend integration tests for abapGit tools.

Tests verify that the abapGit pull and list operations work via SAP GUI COM automation.
Mirrors the WebGUI tests in unittests/webgui/test_abapgit_tools.py.
"""

import os
import sys

import pytest

from sapwebguimcp.models.abapgit_models import AbapGitActionResult, AbapGitListResult
from sapwebguimcp.tools.abapgit_tools import _abapgit_list_repos, _abapgit_pull_via_api
from unittests.desktop.conftest import go_home, skip_no_creds, skip_not_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")

DEFAULT_TRANSPORT = os.environ.get("SAP_TEST_TRANSPORT", "S4UK902008")


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_abapgit_pull_public_repo(backend) -> None:
    """
    Test pulling a public repository via Z_ABAPGIT_PULL_MCP transaction on desktop backend.

    Verifies that the pull operation works via COM automation.
    """
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


@skip_not_sap
@skip_no_creds
@pytest.mark.anyio
async def test_abapgit_list_repos(backend) -> None:
    """
    Test listing registered abapGit repositories on desktop backend.

    Verifies that the LIST mode works via COM screen text reading.
    """
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
