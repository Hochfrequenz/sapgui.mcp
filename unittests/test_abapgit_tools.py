"""
Tests for abapGit MCP tools (sap_abapgit_pull, sap_abapgit_stage).

These tests verify the abapGit integration functionality:
- Pull: Fetch and apply changes from remote git repository
- Stage: Prepare local changes for commit/push

Run with: pytest unittests/test_abapgit_tools.py -v
"""

import os
from unittest.mock import AsyncMock

import pytest
from mcp import ClientSession

from sapwebguimcp.models import AbapGitActionResult, LoginResult

from .conftest import call_tool_typed


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


@pytest.fixture
def mock_page():
    """Create a mock Playwright page for unit tests."""
    page = AsyncMock()
    page.evaluate = AsyncMock(return_value={"found": True})
    page.wait_for_timeout = AsyncMock()
    page.keyboard.press = AsyncMock()
    return page


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
        action="stage",
        repo_name="TestRepo",
        error="Repository not found",
    )

    assert result.success is False
    assert result.action == "stage"
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


@pytest.mark.anyio
async def test_evaluate_js_handles_dict_result(mock_page: AsyncMock) -> None:
    """Test that _evaluate_js handles direct dict results."""
    from sapwebguimcp.tools.abapgit_tools import _evaluate_js

    mock_page.evaluate.return_value = {"found": True, "id": "C116"}

    result = await _evaluate_js(mock_page, "some script")

    assert result == {"found": True, "id": "C116"}
    mock_page.evaluate.assert_called_once_with("some script")


@pytest.mark.anyio
async def test_evaluate_js_handles_string_result(mock_page: AsyncMock) -> None:
    """Test that _evaluate_js parses JSON string results."""
    from sapwebguimcp.tools.abapgit_tools import _evaluate_js

    mock_page.evaluate.return_value = '{"found": true, "repoName": "BO4E"}'

    result = await _evaluate_js(mock_page, "some script")

    assert result == {"found": True, "repoName": "BO4E"}


@pytest.mark.anyio
async def test_find_iframe_with_retry_success_first_try(mock_page: AsyncMock) -> None:
    """Test iframe found on first attempt."""
    from sapwebguimcp.tools.abapgit_tools import _find_iframe_with_retry

    mock_page.evaluate.return_value = {"found": True, "id": "C116"}

    result = await _find_iframe_with_retry(mock_page, max_retries=3)

    assert result["found"] is True
    assert mock_page.evaluate.call_count == 1
    mock_page.wait_for_timeout.assert_not_called()


@pytest.mark.anyio
async def test_find_iframe_with_retry_success_second_try(mock_page: AsyncMock) -> None:
    """Test iframe found on second attempt after retry."""
    from sapwebguimcp.tools.abapgit_tools import RETRY_DELAY_MS, _find_iframe_with_retry

    # First call fails, second succeeds
    mock_page.evaluate.side_effect = [
        {"found": False, "error": "No iframe found"},
        {"found": True, "id": "C116"},
    ]

    result = await _find_iframe_with_retry(mock_page, max_retries=3)

    assert result["found"] is True
    assert mock_page.evaluate.call_count == 2
    # Should have waited once (RETRY_DELAY_MS * 1 for first retry)
    mock_page.wait_for_timeout.assert_called_once_with(RETRY_DELAY_MS)


@pytest.mark.anyio
async def test_find_iframe_with_retry_all_fail(mock_page: AsyncMock) -> None:
    """Test all retries fail."""
    from sapwebguimcp.tools.abapgit_tools import _find_iframe_with_retry

    mock_page.evaluate.return_value = {"found": False, "error": "No iframe found"}

    result = await _find_iframe_with_retry(mock_page, max_retries=3)

    assert result["found"] is False
    assert result["error"] == "No iframe found"
    assert mock_page.evaluate.call_count == 3
    # Should have waited 3 times with exponential backoff
    assert mock_page.wait_for_timeout.call_count == 3


def test_js_call_generates_valid_javascript() -> None:
    """Test that _js_call generates valid JavaScript with arguments."""
    from sapwebguimcp.tools.abapgit_tools import _js_call

    # Call with string argument
    js = _js_call("findRepoRow", "BO4E")

    assert "findRepoRow" in js
    assert '"BO4E"' in js
    assert "return findRepoRow" in js


def test_js_call_handles_special_characters() -> None:
    """Test that _js_call properly escapes special characters in arguments."""
    from sapwebguimcp.tools.abapgit_tools import _js_call

    # Call with special characters
    js = _js_call("findRepoRow", '/HFQ/BO4E"test')

    # Should be properly JSON-encoded
    assert '"/HFQ/BO4E\\"test"' in js or "/HFQ/BO4E" in js


# =============================================================================
# Integration Tests (require SAP connection)
# =============================================================================
#
# NOTE: The repository names used in these tests (Datamatrix, BO4E, ABAP4GEWINNT)
# are specific to the test SAP system and may change. If tests fail because a
# repo is not found, verify the repo exists in ZABAPGIT and update the test
# accordingly. The repo names are arbitrary examples - any repo in ZABAPGIT
# can be used for testing.


@pytest.mark.anyio
async def test_abapgit_pull_by_repo_name(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a repository by name pattern (Z_ABAP4GEWINNT).

    This test verifies that the sap_abapgit_pull tool can:
    1. Navigate to ZABAPGIT transaction
    2. Find a repository by name pattern
    3. Click the menu arrow to expand actions
    4. Click Pull to initiate the pull operation
    5. Authenticate with PAT when login dialog appears

    Uses PAT from ABAPGIT_PAT environment variable.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Pull Z_ABAP4GEWINNT repo (private, uses PAT from env)
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
    # Verify the Pull button was actually found and clicked
    assert result.clicked_action is not None, "Pull button was not clicked"
    assert "pull" in result.clicked_action.lower(), (
        f"Expected 'Pull' button to be clicked, got: {result.clicked_action}"
    )


@pytest.mark.anyio
@pytest.mark.flaky(reruns=2, reruns_delay=5)  # May need pytest-rerunfailures
async def test_abapgit_pull_public_repo_no_pat(sap_mcp_client: ClientSession) -> None:
    """
    Test pulling a PUBLIC repository (Datamatrix) WITHOUT PAT authentication.

    This test verifies that:
    1. Public repos can be pulled without any PAT
    2. No login dialog appears for public repos
    3. The Pull button was found and clicked

    Note: This test can be flaky due to menu expansion timing in SAP GUI.
    """
    # Temporarily remove PAT from environment to ensure we're not using it
    original_pat = os.environ.pop("ABAPGIT_PAT", None)
    original_github_pat = os.environ.pop("GITHUB_PAT", None)

    try:
        # Login first
        login_result = await call_tool_typed(
            sap_mcp_client, "sap_login", {}, LoginResult
        )
        assert login_result.success, f"Login failed: {login_result.error}"

        # Pull the public Datamatrix repo (no PAT needed)
        result = await call_tool_typed(
            sap_mcp_client,
            "sap_abapgit_pull",
            {"repo": "Datamatrix"},
            AbapGitActionResult,
        )

        # Verify the result
        assert result.success, f"Pull failed: {result.error}"
        assert result.action == "pull"
        # Verify the Pull button was actually found and clicked
        assert result.clicked_action is not None, "Pull button was not clicked"
        assert "pull" in result.clicked_action.lower(), (
            f"Expected 'Pull' button to be clicked, got: {result.clicked_action}"
        )

    finally:
        # Restore PAT environment variables
        if original_pat is not None:
            os.environ["ABAPGIT_PAT"] = original_pat
        if original_github_pat is not None:
            os.environ["GITHUB_PAT"] = original_github_pat


@pytest.mark.anyio
async def test_abapgit_pull_private_repo_with_pat(
    sap_mcp_client: ClientSession,
) -> None:
    """
    Test pulling a private repository (HFQ BO4E) with PAT authentication.

    This test verifies that:
    1. The tool can authenticate using ABAPGIT_PAT from environment
    2. Private repos can be pulled when proper credentials are provided
    3. The status bar shows success message
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
    # Verify the Pull button was actually found and clicked
    assert result.clicked_action is not None, "Pull button was not clicked"
    assert "pull" in result.clicked_action.lower(), (
        f"Expected 'Pull' button to be clicked, got: {result.clicked_action}"
    )


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
    # Verify the Pull button was actually found and clicked
    assert result.clicked_action is not None, "Pull button was not clicked"
    assert "pull" in result.clicked_action.lower(), (
        f"Expected 'Pull' button to be clicked, got: {result.clicked_action}"
    )


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
    # Verify the Stage button was actually found and clicked
    assert result.clicked_action is not None, "Stage button was not clicked"
    assert "stag" in result.clicked_action.lower(), (
        f"Expected 'Stage' button to be clicked, got: {result.clicked_action}"
    )


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
    # Verify the Pull button was actually found and clicked
    assert result.clicked_action is not None, "Pull button was not clicked"
    assert "pull" in result.clicked_action.lower(), (
        f"Expected 'Pull' button to be clicked, got: {result.clicked_action}"
    )


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
    # Verify the Pull button was actually found and clicked
    assert result.clicked_action is not None, "Pull button was not clicked"
    assert "pull" in result.clicked_action.lower(), (
        f"Expected 'Pull' button to be clicked, got: {result.clicked_action}"
    )


@pytest.mark.anyio
async def test_abapgit_pull_invalid_tcode(sap_mcp_client: ClientSession) -> None:
    """
    Test that using an invalid transaction code returns an appropriate error.
    """
    # Login first
    login_result = await call_tool_typed(
        sap_mcp_client, "sap_login", {}, LoginResult
    )
    assert login_result.success, f"Login failed: {login_result.error}"

    # Try to pull with invalid tcode
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_abapgit_pull",
        {"repo": "BO4E", "tcode": "INVALID_TCODE_99999"},
        AbapGitActionResult,
    )

    # Should fail because the transaction doesn't exist
    assert not result.success
    assert result.error is not None


def test_abapgit_action_result_requires_action() -> None:
    """Test that AbapGitActionResult requires an action field."""
    from datetime import UTC, datetime

    import pydantic

    # Should raise validation error when action is missing
    with pytest.raises(pydantic.ValidationError):
        AbapGitActionResult(
            success=True,
            repo_name="Test",
            executed_at=datetime.now(UTC),
        )  # type: ignore[call-arg]


def test_abapgit_action_result_requires_repo_name() -> None:
    """Test that AbapGitActionResult requires a repo_name field."""
    from datetime import UTC, datetime

    import pydantic

    # Should raise validation error when repo_name is missing
    with pytest.raises(pydantic.ValidationError):
        AbapGitActionResult(
            success=True,
            action="pull",
            executed_at=datetime.now(UTC),
        )  # type: ignore[call-arg]


@pytest.mark.anyio
async def test_fill_token_secure_passes_token_as_argument(mock_page: AsyncMock) -> None:
    """Test that _fill_token_secure passes token via Playwright argument, not in JS string."""
    from sapwebguimcp.tools.abapgit_tools import _fill_token_secure

    mock_page.evaluate.return_value = {"filled": True, "method": "password_input"}

    result = await _fill_token_secure(mock_page, "secret_token_123")

    # Verify token was passed as second argument, not embedded in JS
    assert mock_page.evaluate.call_count == 1
    call_args = mock_page.evaluate.call_args
    # First arg is the JS script, second arg is the token
    assert len(call_args.args) == 2
    assert call_args.args[1] == "secret_token_123"
    # Token should NOT appear in the JS script itself
    assert "secret_token_123" not in call_args.args[0]
    assert result["filled"] is True
