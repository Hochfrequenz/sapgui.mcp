"""Tests for the branch echo check of ``sap_abapgit_pull``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.abapgit_models import AbapGitActionResult
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools import abapgit_tools
from sapguimcp.tools.abapgit_tools import _abapgit_pull_via_api

REF = "refs/heads/feature/x"


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
    backend.get_status_bar = AsyncMock(return_value=status)
    backend.press_key = AsyncMock()
    backend.wait = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.check_popup = AsyncMock(return_value=None)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


def _ok(message: str = "Pull successful: branch=refs/heads/feature/x repo=R") -> StatusBarInfo:
    return StatusBarInfo(type="S", message=message)


async def _pull(
    backend: Any, lines: list[str] | Exception | None, branch: str | None = "feature/x"
) -> AbapGitActionResult:
    if isinstance(lines, Exception):
        patcher = patch.object(abapgit_tools, "_read_list_lines", side_effect=lines)
    else:
        patcher = patch.object(abapgit_tools, "_read_list_lines", return_value=lines or [])
    with patcher:
        return await _abapgit_pull_via_api(backend, "R", "TRK1", None, None, branch)


@pytest.mark.anyio
async def test_matching_echo_is_a_success_with_the_branch() -> None:
    result = await _pull(_backend(_ok()), [f"BRANCH~{REF}"])
    assert result.success
    assert result.branch == REF


@pytest.mark.anyio
async def test_missing_echo_from_an_outdated_report_is_a_failure() -> None:
    result = await _pull(_backend(_ok("Pull successful: R")), [])
    assert not result.success
    assert "did not confirm" in (result.error or "")
    assert "may have run" in (result.error or "")
    assert result.branch is None


@pytest.mark.anyio
async def test_different_echo_names_both_refs() -> None:
    result = await _pull(_backend(_ok()), ["BRANCH~refs/heads/main"])
    assert not result.success
    assert "refs/heads/main" in (result.error or "")
    assert REF in (result.error or "")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "lines",
    [
        [f"BRANCH~{REF}", f"BRANCH~{REF}"],
        ["BRANCH~refs/tags/x"],
        [f"BRANCH~{REF} trailing"],
        [],
    ],
)
async def test_unusable_echo_is_not_confirmed(lines: list[str]) -> None:
    result = await _pull(_backend(_ok()), lines)
    assert not result.success
    assert "did not confirm" in (result.error or "")


@pytest.mark.anyio
async def test_truncated_status_bar_does_not_matter_when_the_list_line_is_right() -> None:
    status = _ok("Pull successful: branch=refs/heads/feature/")
    assert (await _pull(_backend(status), [f"BRANCH~{REF}"])).success
    assert not (await _pull(_backend(status), [])).success


@pytest.mark.anyio
async def test_a_failing_screen_read_is_reported_as_unconfirmed_not_as_an_unrelated_error() -> None:
    result = await _pull(_backend(_ok("Pull successful: R")), RuntimeError("selection screen has no scrollbar"))
    assert not result.success
    assert "did not confirm" in (result.error or "")
    assert "scrollbar" not in (result.error or "")


@pytest.mark.anyio
async def test_failed_branch_restore_warns_that_the_repo_may_be_on_the_new_branch() -> None:
    status = StatusBarInfo(type="E", message="Branch restore failed: was refs/heads/main; Transport required")
    result = await _pull(_backend(status), [])
    assert not result.success
    assert (result.error or "").startswith("WARNING: the repository may have been left on branch feature/x")
    assert "Branch restore failed: was refs/heads/main" in (result.error or "")


@pytest.mark.anyio
async def test_failed_pin_restore_asks_to_check_the_original_pin() -> None:
    status = StatusBarInfo(type="E", message="Pin restore failed: was refs/heads/main; Transport required")
    result = await _pull(_backend(status), [])
    assert not result.success
    error = result.error or ""
    assert "previous branch was restored" in error
    assert "pin" in error
    assert "left on branch" not in error
    assert "Pin restore failed: was refs/heads/main" in error


@pytest.mark.anyio
async def test_unknown_branch_says_the_selection_is_unchanged() -> None:
    status = StatusBarInfo(type="E", message="Branch not found: x (selected branch unchanged)")
    backend = _backend(status)
    # the selection screen shows no message before F8
    backend.get_status_bar = AsyncMock(side_effect=[StatusBarInfo(type="none", message=""), status, status])
    result = await _pull(backend, [])
    assert not result.success
    assert "Branch not found: x" in (result.error or "")
    assert "selected branch is unchanged" in (result.error or "")


@pytest.mark.anyio
async def test_pull_without_branch_never_reads_the_echo() -> None:
    with patch.object(abapgit_tools, "_read_branch_echo", new=AsyncMock()) as echo:
        result = await _abapgit_pull_via_api(_backend(_ok("Pull successful: R")), "R", "TRK1", None, None)
    assert result.success
    assert result.branch is None
    echo.assert_not_awaited()


def test_result_schema_and_roundtrip_carry_the_branch() -> None:
    schema = AbapGitActionResult.model_json_schema()
    assert "branch" in schema["properties"]
    result = AbapGitActionResult.success_result("pull", "R", "ok")
    result.branch = REF
    assert AbapGitActionResult.model_validate(result.model_dump(mode="json")).branch == REF


@pytest.mark.anyio
async def test_read_problems_make_the_echo_unconfirmed() -> None:
    def read_with_problem(_session: Any, problems: list[str] | None = None) -> list[str]:
        assert problems is not None
        problems.append("slices of line 1 do not overlap consistently")
        return [f"BRANCH~{REF}"]

    with patch.object(abapgit_tools, "_read_list_lines", side_effect=read_with_problem):
        result = await _abapgit_pull_via_api(_backend(_ok()), "R", "TRK1", None, None, "feature/x")
    assert not result.success
    assert "did not confirm" in (result.error or "")
    assert "no readable `BRANCH~` line" in (result.error or "")


@pytest.mark.anyio
async def test_truncated_echo_line_is_not_confirmed_and_not_a_mismatch() -> None:
    result = await _pull(_backend(_ok()), ["BRANCH~refs/heads/feature/"])
    assert not result.success
    assert "did not confirm" in (result.error or "")
