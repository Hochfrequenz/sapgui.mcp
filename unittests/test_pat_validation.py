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

    # NOTE: This test calls the real GitHub API (https://api.github.com).
    # It requires internet access and is subject to GitHub rate limits (60/hour for
    # unauthenticated requests). Consider skipping in isolated CI environments.
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
        respx.get("http://localhost:9222/json/version").mock(return_value=Response(200, json={"Browser": "Chrome/120"}))
        respx.get("https://api.github.com/user").mock(return_value=Response(200, json={"login": "hf-kklein"}))
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
        respx.get("http://localhost:9222/json/version").mock(return_value=Response(200, json={"Browser": "Chrome/120"}))
        respx.get("https://api.github.com/user").mock(return_value=Response(401, json={"message": "Bad credentials"}))
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
        respx.get("http://localhost:9222/json/version").mock(return_value=Response(200, json={"Browser": "Chrome/120"}))
        monkeypatch.setenv("ABAPGIT_PAT", "")
        monkeypatch.setenv("GITHUB_PAT", "")
        from sapwebguimcp.models import config as config_mod

        monkeypatch.setattr(config_mod, "_settings", None)

        with caplog.at_level(logging.INFO):
            async with app_lifespan(None):  # type: ignore[arg-type]
                pass
        assert "GitHub PAT" not in caplog.text


class TestAnalyzePullResultFallback:
    """Tests for the _analyze_pull_result silent success fix."""

    @pytest.mark.anyio
    async def test_empty_status_returns_failure(self) -> None:
        """Empty status bar should return failure, not success."""
        from unittest.mock import AsyncMock, patch

        from sapwebguimcp.tools.abapgit_tools import _analyze_pull_result

        mock_status = type("Status", (), {"message": "", "type": "none"})()
        mock_page = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        with (
            patch(
                "sapwebguimcp.tools.abapgit_tools.sap_read_status_bar_impl",
                new_callable=AsyncMock,
                return_value=mock_status,
            ),
            patch(
                "sapwebguimcp.tools.abapgit_tools._check_screen_for_errors",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await _analyze_pull_result(mock_page, "TEST_REPO")

        assert result.success is False
        assert result.error is not None
        assert "unknown" in result.error.lower() or "empty" in result.error.lower()


class TestRunPullAndCheckErrors:
    """Tests for _run_pull_and_check_errors networkidle wait behavior."""

    @pytest.mark.anyio
    async def test_uses_networkidle_instead_of_hardcoded_waits(self) -> None:
        """After F8, should wait for networkidle instead of hardcoded timeouts."""
        from unittest.mock import AsyncMock, call, patch

        from sapwebguimcp.tools.abapgit_tools import _run_pull_and_check_errors

        mock_page = AsyncMock()
        mock_page.keyboard.press = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        with patch(
            "sapwebguimcp.tools.abapgit_tools._handle_popup_error",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await _run_pull_and_check_errors(mock_page, "TEST_REPO")

        # Should press F8 to execute the report
        mock_page.keyboard.press.assert_any_call("F8")

        # Should wait for networkidle (not hardcoded timeouts)
        mock_page.wait_for_load_state.assert_called_once_with("networkidle", timeout=120_000)

        # Should NOT press Enter (stale, risks re-executing report)
        enter_calls = [c for c in mock_page.keyboard.press.call_args_list if c == call("Enter")]
        assert enter_calls == [], f"Expected no Enter press, got {enter_calls}"
