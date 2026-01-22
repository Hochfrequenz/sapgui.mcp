"""
Tests for abapGit MCP tools (sap_abapgit_pull, sap_abapgit_stage).

These tests verify the abapGit integration functionality:
- Pull: Fetch and apply changes from remote git repository
- Stage: Prepare local changes for commit/push

Run with: pytest unittests/test_abapgit_tools.py -v
"""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import AbapGitActionResult, LoginResult

from .conftest import call_tool_typed


# =============================================================================
# Integration Tests (require SAP connection)
# =============================================================================


@pytest.mark.anyio
async def test_abapgit_pull_public_repo(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a public repository (Z_ABAP4GEWINNT).

    This test verifies that the sap_abapgit_pull tool can:
    1. Navigate to ZABAPGIT transaction
    2. Find a repository by name pattern
    3. Click the menu arrow to expand actions
    4. Click Pull to initiate the pull operation

    Public repos should work without PAT authentication.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull the public Z_ABAP4GEWINNT repo
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "ABAP4GEWINNT"},
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"
    assert "ABAP4GEWINNT" in result.repo_name
    assert result.message is not None
    assert "Pull initiated" in result.message


@pytest.mark.anyio
async def test_abapgit_pull_private_repo_with_pat(
    sap_mcp_client: ClientSession,
) -> None:
    """
    Test pulling a private repository (HFQ BO4E) with PAT authentication.

    This test verifies that:
    1. The tool can authenticate using ABAPGIT_PAT from environment
    2. Private repos can be pulled when proper credentials are provided
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull the HFQ BO4E repo (private, requires PAT)
    # PAT is loaded from ABAPGIT_PAT environment variable
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "BO4E"},
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"
    assert "BO4E" in result.repo_name
    assert result.message is not None


@pytest.mark.anyio
async def test_abapgit_pull_repo_not_found(sap_mcp_client: ClientSession) -> None:
    """
    Test that pulling a non-existent repository returns an appropriate error.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Try to pull a repo that doesn't exist
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "NONEXISTENT_REPO_12345"},
        AbapGitActionResult,
    )

    # Should fail with a meaningful error
    assert not result.success
    assert result.error is not None
    assert "not found" in result.error.lower() or "repo" in result.error.lower()


@pytest.mark.anyio
async def test_abapgit_pull_by_package_name(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a repository by matching its SAP package name.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull by package name pattern (/HFQ/BO4E)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "/HFQ/BO4E"},
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Pull failed: {result.error}"
    assert result.action == "pull"
    assert "BO4E" in result.repo_name


@pytest.mark.anyio
async def test_abapgit_stage_opens_staging_view(sap_mcp_client: ClientSession) -> None:
    """
    Test that the stage action opens the staging view for a repository.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Open staging view for BO4E repo
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_stage",
        {"repo": "BO4E"},
        AbapGitActionResult,
    )

    # Verify the result
    assert result.success, f"Stage failed: {result.error}"
    assert result.action == "stage"
    assert "BO4E" in result.repo_name
    assert result.message is not None


@pytest.mark.anyio
async def test_abapgit_pull_without_login_fails(
    sap_mcp_client: ClientSession,
) -> None:
    """
    Test that calling pull without logging in first returns an error.

    Note: This test intentionally does NOT call sap_login first.
    """
    # Try to pull without logging in - should fail
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "ABAP4GEWINNT"},
        AbapGitActionResult,
    )

    # Should fail because we haven't logged in
    assert not result.success
    assert result.error is not None


@pytest.mark.anyio
async def test_abapgit_pull_with_explicit_pat(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling with an explicitly provided PAT parameter.

    This verifies that the tool accepts PAT as a parameter and uses it
    for authentication instead of the environment variable.
    """
    import os

    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Get PAT from environment for this test
    pat = os.environ.get("ABAPGIT_PAT")
    if not pat:
        pytest.skip("ABAPGIT_PAT environment variable not set")

    # Pull with explicit PAT parameter
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "BO4E", "pat": pat},
        AbapGitActionResult,
    )

    assert result.success, f"Pull with explicit PAT failed: {result.error}"


@pytest.mark.anyio
async def test_abapgit_pull_custom_tcode(sap_mcp_client: ClientSession) -> None:
    """
    Test that the tcode parameter can be customized.

    This verifies that the tool uses the specified transaction code
    instead of the default ZABAPGIT.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull with explicit tcode (same as default, just testing the parameter)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "ABAP4GEWINNT", "tcode": "ZABAPGIT"},
        AbapGitActionResult,
    )

    assert result.success, f"Pull with custom tcode failed: {result.error}"


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
        action="stage",
        repo_name="Test Repo",
        error="Something went wrong",
        executed_at=datetime.now(UTC),
    )
    assert not error_result.success
    assert error_result.error == "Something went wrong"


def test_abapgit_action_result_action_values() -> None:
    """Test that action field only accepts valid values."""
    from datetime import UTC, datetime

    # Valid actions
    for action in ["pull", "stage", "diff", "check"]:
        result = AbapGitActionResult(
            success=True,
            action=action,  # type: ignore[arg-type]
            repo_name="Test",
            executed_at=datetime.now(UTC),
        )
        assert result.action == action


def test_settings_abapgit_fields() -> None:
    """Test that settings include abapGit-related fields."""
    import os

    # Clear any existing env vars to test defaults
    for var in ["ABAPGIT_USER", "ABAPGIT_PAT"]:
        os.environ.pop(var, None)

    # Force reload settings
    import sapwebguimcp.models.config

    sapwebguimcp.models.config._settings = None

    from sapwebguimcp.models.config import SapWebGuiSettings

    # Create fresh settings without .env file
    settings = SapWebGuiSettings(_env_file=None)  # type: ignore[call-arg]

    # Check that abapGit fields exist with correct defaults
    assert hasattr(settings, "abapgit_user")
    assert hasattr(settings, "abapgit_pat")
    assert settings.abapgit_user is None
    assert settings.abapgit_pat is None


def test_settings_loads_abapgit_from_env() -> None:
    """Test that settings load abapGit values from environment."""
    import os

    # Set env vars
    os.environ["ABAPGIT_USER"] = "test-user"
    os.environ["ABAPGIT_PAT"] = "ghp_test_token"

    # Force reload settings
    import sapwebguimcp.models.config

    sapwebguimcp.models.config._settings = None

    from sapwebguimcp.models.config import SapWebGuiSettings

    settings = SapWebGuiSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.abapgit_user == "test-user"
    assert settings.abapgit_pat == "ghp_test_token"

    # Cleanup
    del os.environ["ABAPGIT_USER"]
    del os.environ["ABAPGIT_PAT"]
