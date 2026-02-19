"""Tests for GitHub Personal Access Token (PAT) validation."""

import logging

import pytest
import respx
from httpx import ConnectError, Response

from sapwebguimcp.server import app_lifespan
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


class TestValidateGithubPatReal:
    """Integration tests hitting real GitHub API."""

    @pytest.mark.anyio
    async def test_expired_pat_real(self) -> None:
        """Prove that GitHub returns 401 for a known expired token.

        This token was revoked on 2026-02-19.
        It is safe to hardcode because it is already public and inactive.
        """
        expired_pat = "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"
        valid, msg = await validate_github_pat(expired_pat)
        assert valid is False
        assert "Bad credentials" in msg


class TestStartupPatValidation:
    """Tests for PAT validation during server startup."""

    @respx.mock
    @pytest.mark.anyio
    async def test_startup_logs_valid_pat(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Startup logs [OK] when PAT is valid."""
        respx.get("http://localhost:9222/json/version").mock(
            return_value=Response(200, json={"Browser": "Chrome/120"})
        )
        respx.get("https://api.github.com/user").mock(
            return_value=Response(200, json={"login": "hf-kklein"})
        )
        monkeypatch.setenv("ABAPGIT_PAT", "ghp_fake_valid_token")
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
        respx.get("http://localhost:9222/json/version").mock(
            return_value=Response(200, json={"Browser": "Chrome/120"})
        )
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
        monkeypatch.setenv("ABAPGIT_PAT", "")
        monkeypatch.setenv("GITHUB_PAT", "")
        from sapwebguimcp.models import config as config_mod
        monkeypatch.setattr(config_mod, "_settings", None)

        with caplog.at_level(logging.INFO):
            async with app_lifespan(None):  # type: ignore[arg-type]
                pass
        assert "GitHub PAT" not in caplog.text
