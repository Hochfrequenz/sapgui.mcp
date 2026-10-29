"""Tests for the OK-code parameter validation of ``sap_abapgit_pull``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from sapguimcp.tools import abapgit_tools
from sapguimcp.tools.abapgit_tools import PullParams, _validate_and_prepare_params, _validate_repo_selector


def _settings(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {"abapgit_pat": None, "github_pat": None, "github_user": None}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture(autouse=True)
def _no_settings_credentials():
    with patch.object(abapgit_tools, "get_settings", return_value=_settings()):
        yield


ACCEPTED = [
    "MY-PROJECT-ABAP",
    "Z_REPO",
    "/ABC/CL_EXAMPLE",
    "my.repo",
    "https://github.com/org/MY-PROJECT-ABAP",
    "https://github.com/org/MY-PROJECT-ABAP.git",
    "https://git.example.com:8443/org/repo.git",
    "https://github.com/org/repo/",
]

REJECTED = [
    "A;B",
    "A=B",
    "A B",
    "A\tB",
    "ABC\n",
    "A\r\nB",
    "http://github.com/org/repo",
    "https://user:pw@github.com/org/repo",
    "https://github.com/org/repo?x=1",
    "https://github.com/org/repo#frag",
    "https://github.com/org/repo%20x",
    "https://github.com/org/../repo",
    "../REPO",
    "-REPO",
    "",
    "REPO; DROP TABLE;",
    "A" * 256,
]


class TestRepoSelector:
    @pytest.mark.parametrize("repo", ACCEPTED)
    def test_accepts(self, repo: str) -> None:
        assert _validate_repo_selector(repo) is None

    @pytest.mark.parametrize("repo", REJECTED)
    def test_rejects(self, repo: str) -> None:
        assert _validate_repo_selector(repo) is not None

    def test_accepts_maximum_length(self) -> None:
        assert _validate_repo_selector("A" * 255) is None


class TestPrepareParams:
    @pytest.mark.parametrize("repo", ACCEPTED)
    def test_accepted_repo_yields_exactly_one_p_repo(self, repo: str) -> None:
        result = _validate_and_prepare_params(repo, None, None, None)
        assert isinstance(result, PullParams)
        parts = result.tcode_with_params.split(" ", 1)[1].rstrip(";").split("; ")
        assert parts == [f"P_REPO={repo}"]

    @pytest.mark.parametrize("repo", REJECTED)
    def test_rejected_repo_fails(self, repo: str) -> None:
        result = _validate_and_prepare_params(repo, None, None, None)
        assert not isinstance(result, PullParams)
        assert result.success is False
        assert result.error is not None
        assert result.error.startswith("Invalid repository:")

    def test_error_text(self) -> None:
        result = _validate_and_prepare_params("A;B", None, None, None)
        assert not isinstance(result, PullParams)
        assert result.error == (
            "Invalid repository: 'A;B'. "
            "Use the abapGit name (letters, digits, `_` `-` `.` `/`) or an https:// Git URL. "
            "`;`, `=`, spaces and line breaks are not allowed."
        )

    def test_overlong_repo_gets_length_message_and_is_not_echoed_in_full(self) -> None:
        result = _validate_and_prepare_params("A" * 300, None, None, None)
        assert not isinstance(result, PullParams)
        assert "300 characters" in (result.error or "")
        assert "letters, digits" not in (result.error or "")
        assert "A" * 100 not in (result.error or "")
        assert len(result.repo_name or "") <= 80

    def test_value_with_at_sign_is_not_echoed(self) -> None:
        repo = "https://user:pw@github.com/org/repo"
        result = _validate_and_prepare_params(repo, None, None, None)
        assert not isinstance(result, PullParams)
        assert "@" not in (result.error or "")
        assert "@" not in (result.repo_name or "")
        assert "<redacted>" in (result.error or "")

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"trkorr": "ABCK900001\n"},
            {"username": "some-user\n"},
            {"pat": "ghp_abc\n"},
            {"trkorr": "ABC;K9"},
        ],
    )
    def test_trailing_newline_or_separator_in_parameters_is_rejected(self, kwargs: dict[str, str]) -> None:
        args: dict[str, str | None] = {"trkorr": None, "username": None, "pat": None}
        args.update(kwargs)
        result = _validate_and_prepare_params("REPO", **args)  # type: ignore[arg-type]
        assert not isinstance(result, PullParams)
        assert result.success is False

    @pytest.mark.parametrize(
        "settings_kwargs",
        [
            {"abapgit_pat": "ghp_abc\n"},
            {"github_pat": "ghp_abc;P_REPO=OTHER"},
            {"abapgit_pat": "ghp_abc", "github_user": "user\n"},
            {"abapgit_pat": "ghp_abc", "github_user": "user;x"},
        ],
    )
    def test_settings_values_are_validated_and_not_echoed(self, settings_kwargs: dict[str, str]) -> None:
        with patch.object(abapgit_tools, "get_settings", return_value=_settings(**settings_kwargs)):
            result = _validate_and_prepare_params("REPO", None, None, None)
        assert not isinstance(result, PullParams)
        assert result.success is False
        for value in settings_kwargs.values():
            assert value not in (result.error or "")

    def test_valid_settings_credentials_still_work(self) -> None:
        with patch.object(
            abapgit_tools, "get_settings", return_value=_settings(abapgit_pat="ghp_abc", github_user="some-user")
        ):
            result = _validate_and_prepare_params("REPO", None, None, None)
        assert isinstance(result, PullParams)
        assert "P_USER=some-user" in result.tcode_with_params
        assert "P_TOKEN=ghp_abc" in result.tcode_with_params

    def test_overlong_okcode_fails_client_side(self) -> None:
        repo = "https://github.com/org/" + "a" * 200
        result = _validate_and_prepare_params(repo, "ABCK900001", "some-user", "ghp_" + "a" * 200)
        assert not isinstance(result, PullParams)
        assert result.success is False
        assert "too long" in (result.error or "").lower()
