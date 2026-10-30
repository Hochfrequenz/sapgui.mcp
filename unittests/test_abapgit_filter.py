"""Tests for the client-side filters, the count fields, the compact shape and the repository key of the abapGit
list (#997). The raw read is faked; no SAP."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.abapgit_models import AbapGitListResult, AbapGitRepoInfo, AbapGitRepoSummary
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools.abapgit_tools import (
    _abapgit_list_repos,
    _apply_list_filters,
    _filter_repos,
    _glob_match,
    _parse_repo_lines,
    _validate_list_filters,
    register_abapgit_tools,
)

_LINES = [
    "my-app~https://github.com/org/my-app~Z_MYAPP~refs/heads/main~~~~100000000001",
    "My_Other~https://github.com/org/other.git~Z_OTHER~refs/heads/dev~~~~100000000002",
    "Z_OFFLINE~~Z_OFF~refs/heads/main~~~X~100000000003",
    "legacy~https://example.org/legacy~Z_LEGACY~refs/heads/main~~~",  # 7 fields: report without key
]


def _repos() -> list[AbapGitRepoInfo]:
    return _parse_repo_lines("\n".join(_LINES))[0]


def _names(repos: list[Any]) -> list[str]:
    return [r.name for r in repos]


# --- key parsing ----------------------------------------------------------------------------------------------------


def test_key_is_parsed_from_the_eighth_field_and_none_when_absent() -> None:
    repos = _repos()
    assert [r.key for r in repos] == ["100000000001", "100000000002", "100000000003", None]


def test_empty_eighth_field_is_none() -> None:
    repo = _parse_repo_lines("a~https://x/y~P~refs/heads/main~~~~  ")[0][0]
    assert repo.key is None


# --- _filter_repos --------------------------------------------------------------------------------------------------


def test_no_filter_keeps_everything() -> None:
    assert len(_filter_repos(_repos())) == 4


def test_substring_is_case_insensitive() -> None:
    assert _names(_filter_repos(_repos(), name="MY")) == ["my-app", "My_Other"]


def test_glob_matches_the_whole_string() -> None:
    assert _names(_filter_repos(_repos(), package="z_my*")) == ["my-app"]
    assert _names(_filter_repos(_repos(), package="*app")) == ["my-app"]
    assert _filter_repos(_repos(), package="MYAPP*") == []  # a glob is anchored: no leading Z_
    assert _names(_filter_repos(_repos(), name="legac?")) == ["legacy"]


def test_each_filter_alone() -> None:
    assert _names(_filter_repos(_repos(), url="github.com")) == ["my-app", "My_Other"]
    assert _names(_filter_repos(_repos(), package="Z_LEGACY")) == ["legacy"]
    assert _names(_filter_repos(_repos(), key="100000000002")) == ["My_Other"]


def test_filters_are_anded() -> None:
    assert _names(_filter_repos(_repos(), name="my", url="other")) == ["My_Other"]
    assert _filter_repos(_repos(), name="my-app", package="Z_OTHER") == []


def test_url_filter_never_matches_an_offline_repository() -> None:
    assert "Z_OFFLINE" not in _names(_filter_repos(_repos(), url="*"))
    assert "Z_OFFLINE" in _names(_filter_repos(_repos(), name="*"))


def test_key_filter_is_exact_not_a_substring_and_skips_repos_without_key() -> None:
    assert _filter_repos(_repos(), key="1000000000") == []
    assert _filter_repos(_repos(), key="legacy") == []


def test_brackets_and_regex_metacharacters_are_literal() -> None:
    assert _filter_repos(_repos(), name="[a-z]*") == []
    assert _filter_repos(_repos(), name="my.app") == []  # "." is not a wildcard
    assert _names(_filter_repos(_repos(), name="my?app")) == ["my-app"]
    assert _filter_repos(_repos(), name="(") == []


def test_repeated_stars_do_not_backtrack_catastrophically() -> None:
    repo = AbapGitRepoInfo(name="a" * 5000 + "b", url="https://x/y", package="P", branch="b")
    assert _filter_repos([repo], name="*a*a*a*a*a*a*a*a*c") == []
    assert _filter_repos([repo], name="*****a*****b") == [repo]


# --- validation -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"package": "   "},
        {"url": ""},
        {"key": ""},
        {"name": "x" * 201},
        {"key": "ABCDEFGHIJKLM"},  # 13 characters
        {"key": "AB-1"},
        {"key": "AB CD"},
    ],
)
def test_invalid_filters_are_rejected(kwargs: dict[str, str]) -> None:
    kw: dict[str, str | None] = {"name": None, "package": None, "url": None, "key": None, **kwargs}
    assert _validate_list_filters(**kw) is not None  # type: ignore[arg-type]


def test_key_is_stripped_like_the_other_filters() -> None:
    assert _validate_list_filters(None, None, None, " 100000000002\n") is None
    assert _names(_filter_repos(_repos(), key=" 100000000002\n")) == ["My_Other"]


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("?a", "ba", True),
        ("?a", "a", False),
        ("?a", "", False),
        ("*?", "", False),
        ("*?", "x", True),
        ("*", "", True),
        ("**", "", True),
        ("?", "", False),
        ("a*", "", False),
        ("", "", True),
        ("*a?c", "xxabc", True),
        ("*a?c", "xxac", False),
    ],
)
def test_glob_match_edge_cases(pattern: str, text: str, expected: bool) -> None:
    assert _glob_match(pattern, text) is expected


def test_valid_filters_are_accepted() -> None:
    assert _validate_list_filters("a*", "Z_X?", "github", "0123456789AB") is None
    assert _validate_list_filters(None, None, None, None) is None


# --- _abapgit_list_repos + _apply_list_filters (raw read faked) -------------------------------------------------------


def _backend() -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    backend.press_key = AsyncMock()
    backend.wait = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


async def _read(lines: list[str]) -> AbapGitListResult:
    with patch("sapguimcp.tools.abapgit_tools._read_list_lines", return_value=lines):
        return await _abapgit_list_repos(_backend())


@pytest.mark.anyio
async def test_unfiltered_result_has_counts_and_all_repositories() -> None:
    result = _apply_list_filters(await _read(["TOTAL~4~~~~~", *_LINES]))
    assert result.success
    assert result.total_count == 4
    assert result.matched_count == 4
    assert result.message is None
    assert all(isinstance(r, AbapGitRepoInfo) for r in result.repos)


@pytest.mark.anyio
async def test_filtered_result_states_matched_and_total() -> None:
    result = _apply_list_filters(await _read(["TOTAL~4~~~~~", *_LINES]), package="Z_MYAPP")
    assert (result.total_count, result.matched_count) == (4, 1)
    assert _names(result.repos) == ["my-app"]


@pytest.mark.anyio
async def test_no_match_is_a_success_with_a_hint() -> None:
    result = _apply_list_filters(await _read(["TOTAL~4~~~~~", *_LINES]), name="nothing-like-this")
    assert result.success
    assert (result.total_count, result.matched_count) == (4, 0)
    assert result.repos == []
    assert result.message == "0 of 4 repositories match the filters"


@pytest.mark.anyio
async def test_total_counts_unlistable_online_repositories_too() -> None:
    lines = ["TOTAL~3~~~~~", _LINES[0], "broken~~Z_P~refs/heads/main~~~", _LINES[1]]
    result = _apply_list_filters(await _read(lines), name="my-app")
    assert (result.total_count, result.matched_count) == (3, 1)


@pytest.mark.anyio
async def test_total_without_header_is_the_number_of_listed_repositories() -> None:
    result = _apply_list_filters(await _read(list(_LINES)), name="my")
    assert (result.total_count, result.matched_count) == (4, 2)


@pytest.mark.anyio
async def test_a_short_read_stays_a_failure_whatever_the_filter() -> None:
    raw = await _read(["TOTAL~10~~~~~", *_LINES])
    assert not raw.success
    result = _apply_list_filters(raw, name="nothing-like-this")
    assert not result.success
    assert result.error is not None
    assert "10" in result.error


@pytest.mark.anyio
async def test_compact_returns_only_name_package_and_key() -> None:
    result = _apply_list_filters(await _read(["TOTAL~4~~~~~", *_LINES]), name="my", compact=True)
    assert all(isinstance(r, AbapGitRepoSummary) for r in result.repos)
    assert [r.model_dump() for r in result.repos] == [
        {"name": "my-app", "package": "Z_MYAPP", "key": "100000000001"},
        {"name": "My_Other", "package": "Z_OTHER", "key": "100000000002"},
    ]
    assert (result.total_count, result.matched_count) == (4, 2)


@pytest.mark.anyio
async def test_both_shapes_survive_a_json_round_trip_with_the_right_model() -> None:
    full = _apply_list_filters(await _read(["TOTAL~4~~~~~", *_LINES]))
    compact = _apply_list_filters(await _read(["TOTAL~4~~~~~", *_LINES]), compact=True)
    parsed_full = AbapGitListResult.model_validate_json(full.model_dump_json())
    parsed_compact = AbapGitListResult.model_validate_json(compact.model_dump_json())
    assert all(isinstance(r, AbapGitRepoInfo) for r in parsed_full.repos)
    assert all(isinstance(r, AbapGitRepoSummary) for r in parsed_compact.repos)


@pytest.mark.anyio
async def test_the_registered_tool_validates_filters_and_applies_them() -> None:
    mcp = FastMCP("t")
    register_abapgit_tools(mcp)
    tool = await mcp.get_tool("sap_abapgit_list_repos")
    assert tool is not None
    properties = tool.parameters["properties"]
    assert {"name", "package", "url", "key", "compact"} <= set(properties)
    bad = await tool.fn(name="")
    assert not bad.success
    assert bad.error is not None
    assert "name" in bad.error
    raw = await _read(["TOTAL~4~~~~~", *_LINES])
    with (
        patch("sapguimcp.tools.abapgit_tools.get_backend", AsyncMock(return_value=object())),
        patch("sapguimcp.tools.abapgit_tools._abapgit_list_repos", AsyncMock(return_value=raw)),
    ):
        result = await tool.fn(package="Z_OTHER", compact=True)
    assert result.success
    assert [r.name for r in result.repos] == ["My_Other"]
