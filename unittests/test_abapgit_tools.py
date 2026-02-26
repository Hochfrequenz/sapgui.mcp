"""
Tests for abapGit MCP tools (sap_abapgit_pull, sap_read_se38_source).

These tests verify the abapGit integration functionality:
- Pull: Fetch and apply changes from remote git repository via Z_ABAPGIT_PULL
- SE38 Verification: Read ABAP report source code

Run with: pytest unittests/test_abapgit_tools.py -v
"""

import os

import pytest
from mcp import ClientSession

from sapwebguimcp.models import AbapGitActionResult, LoginResult

from .abapgit_test_helpers import TEST_REPOS, generate_test_marker, git_commit_and_push, modify_test_repo
from .conftest import call_tool_raw, call_tool_typed

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def abapgit_env_vars():
    """Set and clean up abapGit environment variables."""
    original_pat = os.environ.get("ABAPGIT_PAT")

    os.environ["ABAPGIT_PAT"] = "ghp_test_token_12345"

    yield

    # Restore original or remove
    if original_pat is not None:
        os.environ["ABAPGIT_PAT"] = original_pat
    else:
        os.environ.pop("ABAPGIT_PAT", None)


# =============================================================================
# Unit Tests (no SAP connection required)
# =============================================================================


def test_abapgit_action_result_model() -> None:
    """Test that AbapGitActionResult model validates correctly."""
    from datetime import UTC, datetime

    # Valid success result
    result = AbapGitActionResult(
        success=True,
        action="pull",
        repo_name="Test Repo",
        message="Pull completed",
        executed_at=datetime.now(UTC),
    )
    assert result.success
    assert result.action == "pull"
    assert result.repo_name == "Test Repo"
    assert result.error is None

    # Valid error result
    error_result = AbapGitActionResult(
        success=False,
        action="pull",
        repo_name="Test Repo",
        error="Something went wrong",
        executed_at=datetime.now(UTC),
    )
    assert not error_result.success
    assert error_result.error == "Something went wrong"


def test_abapgit_action_result_factory_success() -> None:
    """Test the success factory method."""
    result = AbapGitActionResult.success_result(
        action="pull",
        repo_name="BO4E",
        message="Pull completed successfully",
    )

    assert result.success is True
    assert result.action == "pull"
    assert result.repo_name == "BO4E"
    assert result.message == "Pull completed successfully"
    assert result.error is None
    assert result.executed_at is not None


def test_abapgit_action_result_factory_failure() -> None:
    """Test the failure factory method."""
    result = AbapGitActionResult.failure_result(
        action="pull",
        repo_name="TestRepo",
        error="Repository not found",
    )

    assert result.success is False
    assert result.action == "pull"
    assert result.repo_name == "TestRepo"
    assert result.error == "Repository not found"
    assert result.message is None
    assert result.executed_at is not None


def test_settings_abapgit_fields() -> None:
    """Test that settings include abapGit-related fields."""
    # Clear any existing env vars to test defaults
    os.environ.pop("ABAPGIT_PAT", None)

    # Force reload settings
    import sapwebguimcp.models.config

    sapwebguimcp.models.config._settings = None

    from sapwebguimcp.models.config import SapWebGuiSettings

    # Create fresh settings without .env file
    settings = SapWebGuiSettings(_env_file=None)  # type: ignore[call-arg]

    # Check that abapGit fields exist with correct defaults
    assert hasattr(settings, "abapgit_pat")
    assert settings.abapgit_pat is None


def test_settings_loads_abapgit_from_env(abapgit_env_vars: None) -> None:
    """Test that settings load abapGit values from environment."""
    # Force reload settings
    import sapwebguimcp.models.config

    sapwebguimcp.models.config._settings = None

    from sapwebguimcp.models.config import SapWebGuiSettings

    settings = SapWebGuiSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.abapgit_pat == "ghp_test_token_12345"


def test_abapgit_action_result_requires_action() -> None:
    """Test that action field is required."""
    from datetime import UTC, datetime

    import pydantic

    with pytest.raises(pydantic.ValidationError):
        AbapGitActionResult(
            success=True,
            repo_name="Test",
            executed_at=datetime.now(UTC),
        )  # type: ignore[call-arg]


def test_abapgit_action_result_requires_repo_name() -> None:
    """Test that repo_name field is required."""
    from datetime import UTC, datetime

    import pydantic

    with pytest.raises(pydantic.ValidationError):
        AbapGitActionResult(
            success=True,
            action="pull",
            executed_at=datetime.now(UTC),
        )  # type: ignore[call-arg]


def test_abapgit_repo_info_model() -> None:
    """Test that AbapGitRepoInfo model validates correctly."""
    from sapwebguimcp.models.abapgit_models import AbapGitRepoInfo

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
    from sapwebguimcp.models.abapgit_models import AbapGitListResult, AbapGitRepoInfo

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
    from sapwebguimcp.models.abapgit_models import AbapGitListResult

    result = AbapGitListResult(success=True, repos=[])
    assert result.success
    assert result.repos == []


def test_parse_repo_list_output() -> None:
    """Test parsing pipe-delimited WRITE output from Z_ABAPGIT_PULL LIST mode."""
    from sapwebguimcp.tools.abapgit_tools import parse_repo_list_output

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
    from sapwebguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = "Z_OFFLINE_REPO|file:///path|$Z_OFFLINE|refs/heads/main|||X\n"
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 1
    assert repos[0].name == "Z_OFFLINE_REPO"
    assert repos[0].is_offline is True
    assert repos[0].last_pull_at is None
    assert repos[0].last_pull_by is None


def test_parse_repo_list_output_empty() -> None:
    """Test parsing empty output."""
    from sapwebguimcp.tools.abapgit_tools import parse_repo_list_output

    assert parse_repo_list_output("") == []
    assert parse_repo_list_output("   \n  \n") == []


def test_parse_repo_list_output_skips_garbage() -> None:
    """Test that non-repo lines (SAP UI text, headers) are skipped."""
    from sapwebguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = (
        "Some SAP header text\n"
        "Z_REPO|https://github.com/org/Z_REPO|$Z_PKG|refs/heads/main|20260225120000.0000000|DEV|\n"
        "Another random line\n"
    )
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 1
    assert repos[0].name == "Z_REPO"


# =============================================================================
# Integration Tests (require SAP connection)
# =============================================================================


@pytest.mark.anyio
async def test_abapgit_pull_public_repo(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a public repository via Z_ABAPGIT_PULL transaction.

    This test verifies that the sap_abapgit_pull tool can:
    1. Call the Z_ABAPGIT_PULL transaction with parameters
    2. Successfully pull from a public repository

    The test repo is a submodule at unittests/abapgit_repos/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull public repository (uses PAT from env for authentication)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
            "trkorr": TEST_REPOS["public"]["trkorr"],
        },
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"


@pytest.mark.anyio
async def test_abapgit_pull_private_repo_with_pat(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a private repository with PAT authentication.

    Uses PAT from ABAPGIT_PAT environment variable.
    The test repo is a submodule at unittests/abapgit_repos/Z_PRIVATE_ABAPGIT_TEST_REPOSITORY
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull private repository (requires PAT)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY",
            "trkorr": TEST_REPOS["private"]["trkorr"],
        },
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"


@pytest.mark.anyio
async def test_abapgit_pull_repo_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test that pulling a non-existent repository returns a clear error.
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Try to pull non-existent repo
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "NONEXISTENT_REPO_12345_GIBBERISH",
            "trkorr": TEST_REPOS["public"]["trkorr"],
        },
        AbapGitActionResult,
    )

    # Should fail with repo not found error
    assert not result.success, f"Expected failure but got success: {result.message}"
    assert result.error is not None
    # Error should mention not found
    assert "not found" in result.error.lower() or "Repository" in result.error


@pytest.mark.anyio
async def test_abapgit_pull_with_explicit_pat(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling with an explicitly provided PAT (overriding env).
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Get the actual PAT from environment for explicit passing
    actual_pat = os.environ.get("ABAPGIT_PAT")
    if not actual_pat:
        pytest.skip("ABAPGIT_PAT environment variable not set")

    # Pull with explicit PAT
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY",
            "trkorr": TEST_REPOS["private"]["trkorr"],
            "pat": actual_pat,
        },
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"


@pytest.mark.anyio
async def test_abapgit_e2e_public_repo_pull_and_verify(sap_mcp_client: ClientSession) -> None:
    """
    End-to-end test: modify git repo, push, pull via SAP, verify in SE38.

    This test:
    1. Modifies the ABAP report in the git submodule with a unique marker
    2. Commits and pushes to GitHub
    3. Pulls via sap_abapgit_pull
    4. Verifies the pulled code via sap_read_se38_source
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    repo_config = TEST_REPOS["public"]

    # 1. Generate unique marker and modify the test file
    test_marker = generate_test_marker()
    expected_text = modify_test_repo("public", test_marker)

    # 2. Commit and push to GitHub
    success, output = git_commit_and_push("public", f"test: E2E public repo test {test_marker}")
    assert success, f"Git push failed: {output}"

    # 3. Pull via abapGit
    # KNOWN ISSUE: _analyze_pull_result treats empty status bar as success.
    # If the PAT is expired (HTTP 401), the ABAP report catches cx_root and
    # sends MESSAGE e398, but extract_status_bar.js may fail to capture it,
    # causing pull_result.success=True even though the pull didn't update code.
    # The real failure then only surfaces in step 4 (source code mismatch).
    # If this test fails at the assert below, check ABAPGIT_PAT validity first.
    pull_result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": repo_config["name"],
            "trkorr": repo_config["trkorr"],
        },
        AbapGitActionResult,
    )
    assert pull_result.success, f"Pull failed: {pull_result.error}"

    # 4. Verify in SE38
    verify_result = await call_tool_raw(
        sap_mcp_client,
        "sap_read_se38_source",
        {"program_name": repo_config["report"]},
    )

    assert verify_result.get("success"), f"SE38 read failed: {verify_result.get('error')}"
    source_code = verify_result.get("source_code", "")
    assert expected_text in source_code, (
        f"Expected text '{expected_text}' not found in source code. " f"Got source: {source_code[:500]}..."
    )


@pytest.mark.anyio
async def test_abapgit_e2e_private_repo_pull_and_verify(sap_mcp_client: ClientSession) -> None:
    """
    End-to-end test for private repository with PAT authentication.

    This test:
    1. Modifies the ABAP report in the private git submodule with a unique marker
    2. Commits and pushes to GitHub (requires write access)
    3. Pulls via sap_abapgit_pull with PAT authentication
    4. Verifies the pulled code via sap_read_se38_source
    """
    # Check if PAT is configured
    if not os.environ.get("ABAPGIT_PAT"):
        pytest.skip("ABAPGIT_PAT not set - skipping private repo test")

    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    repo_config = TEST_REPOS["private"]

    # 1. Generate unique marker and modify the test file
    test_marker = generate_test_marker()
    expected_text = modify_test_repo("private", test_marker)

    # 2. Commit and push to GitHub
    success, output = git_commit_and_push("private", f"test: E2E private repo test {test_marker}")
    assert success, f"Git push failed: {output}"

    # 3. Pull via abapGit (with PAT from env)
    pull_result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": repo_config["name"],
            "trkorr": repo_config["trkorr"],
        },
        AbapGitActionResult,
    )
    assert pull_result.success, f"Pull failed: {pull_result.error}"

    # 4. Verify in SE38
    verify_result = await call_tool_raw(
        sap_mcp_client,
        "sap_read_se38_source",
        {"program_name": repo_config["report"]},
    )

    assert verify_result.get("success"), f"SE38 read failed: {verify_result.get('error')}"
    source_code = verify_result.get("source_code", "")
    assert expected_text in source_code, (
        f"Expected text '{expected_text}' not found in source code. " f"Got source: {source_code[:500]}..."
    )


@pytest.mark.anyio
async def test_abapgit_pull_invalid_repo_name(sap_mcp_client: ClientSession) -> None:
    """
    Test that invalid repository names are rejected with a clear error.
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Try to pull with invalid repo name containing special characters
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "REPO; DROP TABLE;",  # Injection attempt
        },
        AbapGitActionResult,
    )

    # Should fail with validation error
    assert not result.success, "Expected failure for invalid repo name"
    assert result.error is not None
    assert "invalid" in result.error.lower() or "alphanumeric" in result.error.lower()
