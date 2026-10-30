"""Tests for pulling by repository key with ``sap_abapgit_pull(key=...)``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.abapgit_models import AbapGitActionResult
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools import abapgit_tools
from sapguimcp.tools.abapgit_tools import (
    PullParams,
    _abapgit_pull_via_api,
    _validate_and_prepare_params,
    _validate_key,
)

KEY = "000000000012"
LABEL = f"key {KEY}"


@pytest.fixture(autouse=True)
def _no_settings_credentials():
    with patch.object(
        abapgit_tools, "get_settings", return_value=SimpleNamespace(abapgit_pat=None, github_pat=None, github_user=None)
    ):
        yield


def _backend(status: StatusBarInfo) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    # the first read (right after the OK-code) is the transaction check; the report answers after F8
    backend.get_status_bar = AsyncMock(side_effect=[StatusBarInfo(type="none", message=""), status, status, status])
    backend.press_key = AsyncMock()
    backend.wait = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.check_popup = AsyncMock(return_value=None)
    backend.require_session = MagicMock(return_value=MagicMock())
    return backend


def _sent(backend: Any) -> str:
    return str(backend.enter_transaction.call_args.args[0])


async def _pull(status: StatusBarInfo, **kwargs: Any) -> tuple[AbapGitActionResult, Any]:
    backend = _backend(status)
    kw: dict[str, Any] = {"repo": None, "trkorr": "TRK1", "username": None, "pat": None, "key": KEY}
    kw.update(kwargs)
    return await _abapgit_pull_via_api(backend, **kw), backend


# --- validation -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["1", "12", "000000000012", "123456789012"])
def test_valid_keys_are_accepted(key: str) -> None:
    assert _validate_key(key) is None


@pytest.mark.parametrize(
    "key",
    [
        "",
        " 12",
        "12 ",
        "12\n",
        "1234567890123",
        "abc",
        "12a",
        "-1",
        "1;P_REPO=X",
        "1=2",
        "١٢",  # Arabic-Indic digits
        "1.0",
    ],
)
def test_invalid_keys_never_produce_a_command(key: str) -> None:
    error = _validate_key(key)
    assert error is not None
    assert error.startswith("Invalid key:")
    result = _validate_and_prepare_params(None, "TRK1", None, None, None, key)
    assert isinstance(result, AbapGitActionResult)
    assert not result.success
    assert result.repo_name == "key"


def test_invalid_key_is_cut_at_forty_characters() -> None:
    error = _validate_key("x" * 100)
    assert error is not None
    assert "x" * 40 in error
    assert "x" * 41 not in error


# --- OK-code --------------------------------------------------------------------------------------------------------


def test_key_is_padded_and_sent_without_p_repo() -> None:
    result = _validate_and_prepare_params(None, None, None, None, None, "12")
    assert isinstance(result, PullParams)
    assert result.tcode_with_params == "/nZ_ABAPGIT_PULL_MCP P_KEY=000000000012;"
    assert result.key == KEY
    assert result.label == LABEL


def test_key_command_with_all_parts() -> None:
    result = _validate_and_prepare_params(None, "TRK1", "user", "tok", "feature/x", "12")
    assert isinstance(result, PullParams)
    assert result.tcode_with_params == (
        "/nZ_ABAPGIT_PULL_MCP P_KEY=000000000012; P_BRANCH=feature/x; P_TRKORR=TRK1; P_USER=user; P_TOKEN=tok;"
    )
    assert "P_REPO" not in result.tcode_with_params


# --- exclusivity and labels -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("repo", "key", "message", "label"),
    [
        ("R", "12", "Give only one of repo or key", "R"),
        ("", "12", "Give only one of repo or key", ""),
        (None, None, "Give exactly one of repo or key", "(none)"),
        ("https://user:pw@host/x", "12", "Give only one of repo or key", "<redacted>"),
        ("", None, "Invalid repository", ""),
        (None, "", "Invalid key", "key"),
    ],
)
def test_selector_rules_fail_before_any_command(repo: str | None, key: str | None, message: str, label: str) -> None:
    result = _validate_and_prepare_params(repo, None, None, None, None, key)
    assert isinstance(result, AbapGitActionResult)
    assert not result.success
    assert message in (result.error or "")
    assert result.repo_name == label


def test_valid_key_with_invalid_branch_or_trkorr_keeps_the_key_label() -> None:
    for kwargs in ({"branch": "a b"}, {"trkorr": "A;B"}):
        result = _validate_and_prepare_params(None, kwargs.get("trkorr"), None, None, kwargs.get("branch"), "12")
        assert isinstance(result, AbapGitActionResult)
        assert result.repo_name == LABEL


@pytest.mark.anyio
async def test_neither_selector_does_not_touch_sap_or_raise() -> None:
    backend = _backend(StatusBarInfo(type="S", message="x"))
    result = await _abapgit_pull_via_api(backend, None, None, None, None)
    assert not result.success
    assert result.repo_name == "(none)"
    backend.enter_transaction.assert_not_called()


@pytest.mark.anyio
async def test_get_backend_error_branch_with_key_does_not_raise() -> None:
    mcp = abapgit_tools.FastMCP("t")
    abapgit_tools.register_abapgit_tools(mcp)
    tool = await mcp.get_tool("sap_abapgit_pull")
    assert tool is not None
    with patch.object(abapgit_tools, "get_backend", AsyncMock(side_effect=ValueError("nope"))):
        result = await tool.fn(key="12")
        neither = await tool.fn()
    assert (result.success, result.repo_name) == (False, LABEL)
    assert (neither.success, neither.repo_name) == (False, "(none)")


@pytest.mark.anyio
async def test_exception_during_a_key_pull_is_returned_with_the_label() -> None:
    backend = _backend(StatusBarInfo(type="S", message="x"))
    backend.enter_transaction = AsyncMock(side_effect=RuntimeError("boom"))
    result = await _abapgit_pull_via_api(backend, None, None, None, None, key="12")
    assert (result.success, result.repo_name, result.error) == (False, LABEL, "boom")


# --- results --------------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_success_reports_the_repository_name_and_sends_only_p_key() -> None:
    result, backend = await _pull(StatusBarInfo(type="S", message="Pull successful: MY_REPO"))
    assert result.success
    assert result.repo_name == "MY_REPO"
    assert result.message == "Pull successful: MY_REPO"
    assert "P_KEY=000000000012" in _sent(backend)
    assert "P_REPO=" not in _sent(backend)


@pytest.mark.anyio
async def test_pull_by_name_never_changes_repo_name() -> None:
    result, _ = await _pull(StatusBarInfo(type="S", message="Pull successful: OTHER"), repo="MINE", key=None)
    assert (result.success, result.repo_name) == (True, "MINE")


@pytest.mark.parametrize(
    "message",
    [
        "Pull successful: branch=refs/heads/very/long/br",  # cut before repo=
        "Pull successful: " + "N" * 50,  # a name cut at 50 characters
        "Pull successful: " + "N" * 45,
        "Pull completed. Status: something",
        "Pull successful: A B",
    ],
)
@pytest.mark.anyio
async def test_untrusted_status_keeps_the_key_label(message: str) -> None:
    result, _ = await _pull(StatusBarInfo(type="S", message=message), branch=None)
    assert result.success
    assert result.repo_name == LABEL


@pytest.mark.anyio
async def test_branch_status_names_the_repository() -> None:
    message = "Pull successful: branch=refs/heads/feature/x repo=MY_REPO"
    backend = _backend(StatusBarInfo(type="S", message=message))
    with patch.object(abapgit_tools, "_read_branch_echo", AsyncMock(return_value="refs/heads/feature/x")):
        result = await _abapgit_pull_via_api(backend, None, "TRK1", None, None, branch="feature/x", key=KEY)
    assert result.success
    assert result.repo_name == "MY_REPO"
    assert result.branch == "refs/heads/feature/x"
    assert "P_KEY=000000000012; P_BRANCH=feature/x" in _sent(backend)


@pytest.mark.anyio
async def test_old_report_is_reported_as_too_old_for_a_key_pull_only() -> None:
    status = StatusBarInfo(type="E", message="P_REPO is required for PULL action")
    result, _ = await _pull(status)
    assert not result.success
    assert result.repo_name == LABEL
    assert "does not support pulling by key" in (result.error or "")
    assert "Nothing was pulled" in (result.error or "")
    by_name, _ = await _pull(status, repo="R", key=None)
    assert by_name.error == "P_REPO is required for PULL action"


@pytest.mark.anyio
async def test_new_report_message_is_not_taken_for_an_old_report() -> None:
    status = StatusBarInfo(type="E", message="P_REPO or P_KEY is required for PULL action")
    result, _ = await _pull(status)
    assert result.error == "P_REPO or P_KEY is required for PULL action"


@pytest.mark.anyio
async def test_unknown_key_gets_a_hint() -> None:
    status = StatusBarInfo(type="E", message="Repository not found: key 999999999999 (online only)")
    result, _ = await _pull(status, key="999999999999")
    assert not result.success
    assert (result.error or "").startswith("Repository not found: key 999999999999 (online only)")
    assert "offline repository" in (result.error or "")


@pytest.mark.parametrize(
    "message", ["Invalid P_KEY: 12ab (digits only, max 12)", "Use either P_REPO or P_KEY, not both"]
)
@pytest.mark.anyio
async def test_other_report_messages_pass_through(message: str) -> None:
    result, _ = await _pull(StatusBarInfo(type="E", message=message))
    assert result.error == message


@pytest.mark.anyio
async def test_transport_guidance_names_key_for_a_key_pull_and_repo_otherwise() -> None:
    status = StatusBarInfo(type="E", message="Transport required: provide P_TRKORR")
    result, _ = await _pull(status, trkorr=None)
    assert "sap_abapgit_pull(key=..., trkorr=" in (result.error or "")
    assert "repo=" not in (result.error or "")
    by_name, _ = await _pull(status, repo="R", key=None, trkorr=None)
    assert "sap_abapgit_pull(repo=..., trkorr=" in (by_name.error or "")
