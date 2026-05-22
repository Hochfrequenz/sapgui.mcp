"""
Tests for abapGit MCP tools (sap_abapgit_pull, sap_read_se38_source).

These tests verify the abapGit integration functionality:
- Pull: Fetch and apply changes from remote git repository via Z_ABAPGIT_PULL_MCP
- SE38 Verification: Read ABAP report source code

Run with: pytest unittests/test_abapgit_tools.py -v
"""

import os

import pytest
from mcp import ClientSession

from sapguimcp.models import AbapGitActionResult, LoginResult
from sapguimcp.tools.abapgit_tools import (
    _enrich_transport_error,
    _is_no_task_error,
    _is_transport_required_error,
)

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
    import sapguimcp.models.config

    sapguimcp.models.config._settings = None

    from sapguimcp.models.config import SapGuiSettings

    # Create fresh settings without .env file
    settings = SapGuiSettings(_env_file=None)  # type: ignore[call-arg]

    # Check that abapGit fields exist with correct defaults
    assert hasattr(settings, "abapgit_pat")
    assert settings.abapgit_pat is None


def test_settings_loads_abapgit_from_env(abapgit_env_vars: None) -> None:
    """Test that settings load abapGit values from environment."""
    # Force reload settings
    import sapguimcp.models.config

    sapguimcp.models.config._settings = None

    from sapguimcp.models.config import SapGuiSettings

    settings = SapGuiSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.abapgit_pat == "ghp_test_token_12345"


def test_is_transport_required_error() -> None:
    """Test detection of transport-required error messages."""
    # Positive cases — various SAP transport error messages
    assert _is_transport_required_error("Transport required. Provide P_TRKORR= KS")
    assert _is_transport_required_error("transport erforderlich")
    assert _is_transport_required_error("Transport Required")
    assert _is_transport_required_error("Please provide P_TRKORR= for this operation")
    assert _is_transport_required_error("Transportauftrag fehlt")

    # Negative cases — unrelated errors
    assert not _is_transport_required_error("Repository not found")
    assert not _is_transport_required_error("Pull successful")
    assert not _is_transport_required_error("Authentication failed")
    assert not _is_transport_required_error("")


def test_enrich_transport_error_adds_guidance() -> None:
    """Test that transport errors get actionable guidance appended."""
    # Transport error should get guidance
    enriched = _enrich_transport_error("Transport required. Provide P_TRKORR= KS")
    assert "Transport required" in enriched
    assert "SE09" in enriched
    assert "trkorr=" in enriched

    # Non-transport error should pass through unchanged
    original = "Repository not found"
    assert _enrich_transport_error(original) == original


def test_enrich_transport_error_strips_trailing_period() -> None:
    """Test that enriched error does not produce double-period sentence boundary."""
    enriched = _enrich_transport_error("Transport required.")
    # Should not have ". ." or ".." at the junction (but "..." in repo=... is fine)
    assert ". ." not in enriched, f"Double period at sentence boundary in: {enriched}"
    # The original trailing period should be stripped before appending guidance
    assert not enriched.startswith("Transport required.. "), f"Trailing period not stripped: {enriched}"

    enriched2 = _enrich_transport_error("Transport required. Provide P_TRKORR= KS.")
    assert ". ." not in enriched2, f"Double period at sentence boundary in: {enriched2}"


def test_enrich_transport_error_german() -> None:
    """Test that German transport errors also get guidance."""
    enriched = _enrich_transport_error("Transport erforderlich")
    assert "SE09" in enriched
    assert "trkorr=" in enriched


def test_is_no_task_error() -> None:
    """Test detection of no-task-in-transport error messages."""
    # Positive cases
    assert _is_no_task_error("User KLEINK has no modifiable task in S4UK902263")
    assert _is_no_task_error("Benutzer KLEINK hat keine modifizierbare Aufgabe")
    assert _is_no_task_error("has no task in transport")

    # Negative cases
    assert not _is_no_task_error("Transport required. Provide P_TRKORR=")
    assert not _is_no_task_error("Pull successful")
    assert not _is_no_task_error("")


def test_enrich_no_task_error_adds_guidance() -> None:
    """Test that no-task errors get actionable guidance appended."""
    enriched = _enrich_transport_error("User KLEINK has no modifiable task in S4UK902263")
    assert "has no modifiable task" in enriched
    assert "SE09" in enriched
    assert "task" in enriched.lower()

    # Non-task error should pass through unchanged
    original = "Repository not found"
    assert _enrich_transport_error(original) == original


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


def test_abapgit_list_result_failure_requires_error() -> None:
    """Test that AbapGitListResult(success=False) requires a non-empty error string."""
    import pytest
    from pydantic import ValidationError

    from sapguimcp.models.abapgit_models import AbapGitListResult

    with pytest.raises(ValidationError):
        AbapGitListResult(success=False, error=None)

    with pytest.raises(ValidationError):
        AbapGitListResult(success=False, error="")

    # Valid failure case
    result = AbapGitListResult(success=False, error="Something went wrong")
    assert not result.success
    assert result.error == "Something went wrong"


def test_parse_repo_list_output() -> None:
    """Test parsing tilde-delimited WRITE output from Z_ABAPGIT_PULL_MCP_SHORTCUT LIST mode."""
    from sapguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = (
        "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY~https://github.com/Hochfrequenz/Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"
        "~$Z_PUBLIC_ABAPGIT~refs/heads/main~20260225120000.0000000~DEVELOPER~\n"
        "Z_PRIVATE_ABAPGIT_TEST_REPOSITORY~https://github.com/Hochfrequenz/Z_PRIVATE_ABAPGIT_TEST_REPOSITORY"
        "~$Z_PRIVATE_ABAPGIT~refs/heads/main~20260224150000.0000000~ADMIN~"
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

    raw_output = "Z_OFFLINE_REPO~file:///path~$Z_OFFLINE~refs/heads/main~~~X\n"
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
        "Z_REPO~https://github.com/org/Z_REPO~$Z_PKG~refs/heads/main~20260225120000.0000000~DEV~\n"
        "Another random line\n"
    )
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 1
    assert repos[0].name == "Z_REPO"


def test_parse_repo_list_output_initial_timestamp() -> None:
    """Test that initial ABAP TIMESTAMPL (all zeros) is treated as None."""
    from sapguimcp.tools.abapgit_tools import parse_repo_list_output

    raw_output = "Z_REPO~https://github.com/org/Z_REPO~$Z_PKG~refs/heads/main~00000000000000.0000000~~\n"
    repos = parse_repo_list_output(raw_output)
    assert len(repos) == 1
    assert repos[0].last_pull_at is None


# =============================================================================
# Integration Tests (require SAP connection)
# =============================================================================


@pytest.mark.anyio
async def test_abapgit_pull_public_repo(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a public repository via Z_ABAPGIT_PULL_MCP transaction.

    This test verifies that the sap_abapgit_pull tool can:
    1. Call the Z_ABAPGIT_PULL_MCP transaction with parameters
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
        f"Got ambiguous status: {result.message}. " "networkidle wait should have captured the ABAP MESSAGE."
    )


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
    # NOTE: If this test fails at the assert below, check ABAPGIT_PAT validity first.
    # An expired PAT causes cx_root in ABAP which may surface as a pull error.
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
async def test_abapgit_list_repos(sap_mcp_client: ClientSession) -> None:
    """
    Test listing registered abapGit repositories.

    Requires Z_ABAPGIT_PULL_MCP to be deployed with LIST support.
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
    assert (
        "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY" in repo_names
    ), f"Expected Z_PUBLIC_ABAPGIT_TEST_REPOSITORY in {repo_names}"

    # Check that the public repo has expected metadata
    public_repo = next(r for r in result.repos if r.name == "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY")
    assert "github.com" in public_repo.url
    assert public_repo.package  # Should have a package
    assert public_repo.is_offline is False


@pytest.mark.anyio
async def test_abapgit_pull_without_trkorr_returns_transport_guidance(sap_mcp_client: ClientSession) -> None:
    """
    Test that pulling without trkorr on a system requiring transports
    returns an actionable error with guidance to use sap_se09_lookup.

    Fixes #254.
    """
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull without trkorr — SAP should require a transport request
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"},
        AbapGitActionResult,
    )

    # The pull should fail because no transport was provided
    assert not result.success, (
        f"Expected failure (transport required) but got success: {result.message}. "
        "Does this SAP system not require transport requests?"
    )
    assert result.error is not None

    # Error should contain actionable guidance
    error_lower = result.error.lower()
    assert "transport" in error_lower, f"Expected 'transport' in error but got: {result.error}"
    assert "se09" in error_lower, f"Expected guidance mentioning 'SE09' in error but got: {result.error}"
    assert "trkorr" in error_lower, f"Expected 'trkorr' in error but got: {result.error}"


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


@pytest.mark.anyio
async def test_abapgit_pull_transport_without_user_task(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling with a transport where the logged-in user has no task (Aufgabe).

    Bug report: when user KLEINK had no task in a transport, the pull silently
    succeeded but nothing was actually written. The tool should detect this
    condition and return a clear error.

    Uses S4UK902263 — a workbench transport (not released) where KLEINK
    has no task. This transport is hardcoded because we need a specific
    transport on our test system where the test user has no task —
    there is no good way to make this fully configurable (frickelig).
    """
    # Login first
    login_result = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull with a workbench transport where KLEINK has no task
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {
            "repo": "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY",
            "trkorr": "S4UK902263",
        },
        AbapGitActionResult,
    )

    # The pull must fail — the user has no task in this transport,
    # so nothing can actually be written. Previously this silently
    # reported success because the ABAP log was not checked.
    assert not result.success, (
        f"Pull silently succeeded with a transport where user has no task. "
        f"message={result.message}, error={result.error}"
    )
    assert result.error is not None
    error_lower = result.error.lower()
    assert "task" in error_lower, f"Expected 'task' in error but got: {result.error}"
    assert result.action == "pull"
