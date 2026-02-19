"""Tests for GitHub Personal Access Token (PAT) validation."""

import pytest
import respx
from httpx import ConnectError, Response

from sapwebguimcp.tools.abapgit_tools import validate_github_pat


class TestValidateGithubPat:
    """Tests for the validate_github_pat function."""

    @respx.mock
    @pytest.mark.anyio
    async def test_valid_pat(self) -> None:
        """Returns (True, login) when the PAT is valid and GitHub responds with 200."""
        respx.get("https://api.github.com/user").mock(return_value=Response(200, json={"login": "test-user"}))
        result = await validate_github_pat("ghp_valid_token_123")
        assert result == (True, "test-user")

    @respx.mock
    @pytest.mark.anyio
    async def test_expired_pat(self) -> None:
        """Returns (False, ...) with 'Bad credentials' when the PAT is expired (401)."""
        respx.get("https://api.github.com/user").mock(return_value=Response(401, json={"message": "Bad credentials"}))
        ok, msg = await validate_github_pat("ghp_expired_token_456")
        assert ok is False
        assert "Bad credentials" in msg

    @respx.mock
    @pytest.mark.anyio
    async def test_forbidden_pat(self) -> None:
        """Returns (False, ...) with 'Forbidden' when the PAT lacks permissions (403)."""
        respx.get("https://api.github.com/user").mock(return_value=Response(403, json={"message": "Forbidden"}))
        ok, msg = await validate_github_pat("ghp_forbidden_token_789")
        assert ok is False
        assert "Forbidden" in msg

    @respx.mock
    @pytest.mark.anyio
    async def test_network_error(self) -> None:
        """Returns (False, ...) mentioning 'unreachable' when a network error occurs."""
        respx.get("https://api.github.com/user").mock(side_effect=ConnectError("Connection refused"))
        ok, msg = await validate_github_pat("ghp_any_token_000")
        assert ok is False
        assert "unreachable" in msg.lower()
