"""Tests for reading the complete abapGit repository list: paging, stitching of long lines, TOTAL check (#947)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.sap_results import StatusBarInfo
from sapguimcp.tools.abapgit_tools import (
    _abapgit_list_displayed,
    _abapgit_list_repos,
    _read_list_lines,
    parse_repo_list_output,
    parse_repo_list_total,
)

_WIDTH = 125  # characters a label shows (the window's horizontal page)
_VISIBLE = 36  # list lines on screen (the window's vertical page)


class _Scrollbar:
    def __init__(self, maximum: int, page_size: int) -> None:
        self.maximum = maximum
        self.page_size = page_size
        self._position = 0

    @property
    def position(self) -> int:
        return self._position

    @position.setter
    def position(self, value: int) -> None:
        self._position = max(0, min(int(value), self.maximum))  # SAP clamps to the scrollbar's range


class _FakeListScreen:
    """The ``usr`` area of a classic list: fixed header on rows 0 and 1, then the lines from the scroll position.

    ``data_rows`` is how many lines the window really shows; the scrollbar's ``page_size`` is ``page_size`` (they are
    equal on SAP GUI, a difference is the stress case). ``horizontal_maximum`` and ``scrollbars`` are configurable.
    """

    def __init__(
        self,
        lines: list[str],
        *,
        data_rows: int = _VISIBLE,
        page_size: int = _VISIBLE,
        horizontal_maximum: int = 898,
        scrollbars: bool = True,
    ) -> None:
        self.lines = lines
        self.data_rows = data_rows
        if scrollbars:
            self._vertical = _Scrollbar(maximum=max(len(lines) - data_rows, 0), page_size=page_size)
            self._horizontal = _Scrollbar(maximum=horizontal_maximum, page_size=_WIDTH)
        self.scrollbars = scrollbars

    @property
    def vertical_scrollbar(self) -> _Scrollbar:
        if not self.scrollbars:
            raise AttributeError("no vertical scrollbar")
        return self._vertical

    @property
    def horizontal_scrollbar(self) -> _Scrollbar:
        if not self.scrollbars:
            raise AttributeError("no horizontal scrollbar")
        return self._horizontal

    def dump_tree(self) -> list[Any]:
        elements = [
            SimpleNamespace(id="wnd[0]/usr/lbl[0,0]", text="abapGit Pull via API"),
            SimpleNamespace(id="wnd[0]/usr/lbl[118,0]", text="      1"),
        ]
        top = self._vertical.position if self.scrollbars else 0
        left = self._horizontal.position if self.scrollbars else 0
        for row in range(2, 2 + self.data_rows):
            index = top + row - 2
            if index >= len(self.lines):
                break
            visible = self.lines[index][left : left + _WIDTH]
            if visible:  # SAP shows no label for an empty slice
                elements.append(SimpleNamespace(id=f"wnd[0]/usr/lbl[0,{row}]", text=visible))
        return elements


def _session(screen: _FakeListScreen) -> Any:
    return SimpleNamespace(find_by_id=lambda element_id, **_k: screen if element_id == "wnd[0]/usr" else None)


def _line(i: int, extra: int = 0) -> str:
    """A repository line of the report's format, optionally padded to be longer than the window."""
    url = "https://github.com/Org/Repo" + str(i) + "x" * extra
    return f"Repo{i}~{url}~Z_PKG_{i}~refs/heads/main~20260102030405.1234567~USER{i}~"


# --- _read_list_lines ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("count", [1, 10, 35, 36, 37, 100, 275])
def test_every_line_of_a_list_longer_than_the_window_is_read_in_order(count: int) -> None:
    lines = ["TOTAL~" + str(count - 1) + "~~~~~", *(_line(i) for i in range(count - 1))]
    assert _read_list_lines(_session(_FakeListScreen(lines))) == lines


@pytest.mark.parametrize("extra", [50, 100, 150, 400])
def test_lines_longer_than_the_window_are_stitched_from_overlapping_slices(extra: int) -> None:
    lines = [_line(i, extra) for i in range(50)]
    assert any(len(line) > _WIDTH for line in lines)
    assert _read_list_lines(_session(_FakeListScreen(lines))) == lines


def test_lines_of_very_different_length_are_stitched_independently() -> None:
    lines = [_line(i, extra=(i * 37) % 400) for i in range(80)]
    assert _read_list_lines(_session(_FakeListScreen(lines))) == lines


def test_a_line_that_ends_exactly_at_a_slice_boundary_is_complete() -> None:
    exact = "x" * _WIDTH  # fills the window to the last character
    boundary = "y" * (_WIDTH + 100 - 25)  # ends where the second slice would start extending it
    lines = [exact, boundary, "short"]
    assert _read_list_lines(_session(_FakeListScreen(lines))) == lines


def test_an_empty_list_reads_as_no_lines() -> None:
    assert _read_list_lines(_session(_FakeListScreen([]))) == []


def test_both_scrollbars_are_reset_afterwards() -> None:
    screen = _FakeListScreen([_line(i, 200) for i in range(100)])
    _read_list_lines(_session(screen))
    assert (screen.vertical_scrollbar.position, screen.horizontal_scrollbar.position) == (0, 0)


def test_both_scrollbars_are_reset_when_reading_fails_midway() -> None:
    screen = _FakeListScreen([_line(i, 200) for i in range(100)])
    original = screen.dump_tree
    calls = {"n": 0}

    def _failing_dump() -> list[Any]:
        calls["n"] += 1
        if calls["n"] == 5:
            raise OSError("COM error")
        return original()

    screen.dump_tree = _failing_dump  # type: ignore[method-assign]
    with pytest.raises(OSError, match="COM error"):
        _read_list_lines(_session(screen))
    assert (screen.vertical_scrollbar.position, screen.horizontal_scrollbar.position) == (0, 0)


def test_inconsistent_overlap_between_slices_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    screen = _FakeListScreen([_line(0, 200)])
    original = screen.dump_tree

    def _tampered_dump() -> list[Any]:
        elements = original()
        if screen.horizontal_scrollbar.position > 0:  # the second slice no longer matches the first
            for element in elements:
                if "lbl[0,2]" in element.id:
                    element.text = "#" * len(element.text)
        return elements

    screen.dump_tree = _tampered_dump  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        _read_list_lines(_session(screen))
    assert "do not overlap consistently" in caplog.text


# --- parsing --------------------------------------------------------------------------------------------------------


def test_total_header_is_parsed() -> None:
    assert parse_repo_list_total("TOTAL~274~~~~~\nA~https://x/y~P~refs/heads/main~~~") == 274
    assert parse_repo_list_total("TOTAL~0~~~~~") == 0


def test_total_is_none_without_the_header_and_ignores_repos_whose_name_starts_with_total() -> None:
    assert parse_repo_list_total("A~https://x/y~P~refs/heads/main~~~") is None
    assert parse_repo_list_total("TOTALITY~https://x/y~P~refs/heads/main~~~") is None


def test_offline_repository_without_name_or_url_is_listed_under_its_package() -> None:
    repos = parse_repo_list_output("~~/ABC/PKG~~20250620122057.1489810~SOMEONE~X")
    assert len(repos) == 1
    assert (repos[0].name, repos[0].url, repos[0].package, repos[0].is_offline) == ("/ABC/PKG", "", "/ABC/PKG", True)


def test_offline_repository_keeps_its_own_name() -> None:
    repos = parse_repo_list_output("My repo~~PKG~~~~X")
    assert [(r.name, r.is_offline) for r in repos] == [("My repo", True)]


def test_online_row_without_url_is_still_skipped_and_an_offline_row_without_anything_too() -> None:
    assert parse_repo_list_output("Name~~PKG~refs/heads/main~~~") == []
    assert parse_repo_list_output("~~~~~~X") == []


# --- _abapgit_list_repos --------------------------------------------------------------------------------------------


def _backend(*, status: StatusBarInfo | None = None) -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.get_status_bar = AsyncMock(return_value=status or StatusBarInfo(type="S", message=""))
    backend.press_key = AsyncMock()
    backend.wait = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_condition = AsyncMock(return_value=True)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


async def _list(backend: Any, lines: list[str]) -> Any:
    with patch("sapguimcp.tools.abapgit_tools._read_list_lines", return_value=lines):
        return await _abapgit_list_repos(backend)


@pytest.mark.anyio
async def test_list_returns_all_repositories_when_the_total_matches() -> None:
    lines = ["TOTAL~3~~~~~", *(_line(i) for i in range(3))]
    result = await _list(_backend(), lines)
    assert result.success
    assert [r.name for r in result.repos] == ["Repo0", "Repo1", "Repo2"]


@pytest.mark.anyio
async def test_list_fails_loudly_when_fewer_repositories_were_read_than_the_report_lists() -> None:
    lines = ["TOTAL~274~~~~~", *(_line(i) for i in range(40))]
    result = await _list(_backend(), lines)
    assert not result.success
    assert result.error is not None
    assert "274" in result.error
    assert "40" in result.error


@pytest.mark.anyio
async def test_list_without_total_header_is_accepted() -> None:
    result = await _list(_backend(), [_line(i) for i in range(5)])
    assert result.success
    assert len(result.repos) == 5


@pytest.mark.anyio
async def test_list_reports_the_status_bar_error_when_the_report_failed_and_nothing_was_listed() -> None:
    backend = _backend(status=StatusBarInfo(type="E", message="Invalid P_ACTION: XYZ. Use PULL or LIST."))
    result = await _list(backend, [])
    assert not result.success
    assert result.error is not None
    assert "Invalid P_ACTION" in result.error


@pytest.mark.anyio
async def test_list_with_zero_repositories_and_no_error_is_a_success() -> None:
    result = await _list(_backend(), ["TOTAL~0~~~~~"])
    assert result.success
    assert result.repos == []


@pytest.mark.anyio
async def test_desktop_list_waits_for_the_list_instead_of_a_fixed_time() -> None:
    backend = _backend()
    await _list(backend, ["TOTAL~0~~~~~"])
    backend.wait.assert_not_awaited()
    backend.wait_for_ready.assert_awaited()
    assert backend.wait_for_condition.await_args.kwargs == {"timeout_ms": 5000}
    assert backend.wait_for_condition.await_args.args[0].__name__ == "_abapgit_list_displayed"


# --- robustness of the reader ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("horizontal_maximum", [898, 850, 777, 130, 52, 1])
def test_the_last_horizontal_position_is_visited_whatever_the_scrollbar_maximum(horizontal_maximum: int) -> None:
    # the longest line is 177 characters, so SAP would report a maximum of 177 - 125 = 52 for it; other maxima
    # must work as well, in particular ones that are not a multiple of the 100 character step and ones below it
    lines = [_line(i, extra=90) for i in range(40)]
    assert max(len(line) for line in lines) > _WIDTH
    screen = _FakeListScreen(
        lines, horizontal_maximum=max(horizontal_maximum, max(len(line) for line in lines) - _WIDTH)
    )
    assert _read_list_lines(_session(screen)) == lines


def test_a_line_reaching_the_last_position_of_the_horizontal_scrollbar_is_complete() -> None:
    long_line = "x" * 1000
    screen = _FakeListScreen([long_line, "short"], horizontal_maximum=len(long_line) - _WIDTH)
    assert _read_list_lines(_session(screen)) == [long_line, "short"]


@pytest.mark.parametrize("data_rows", [36, 35, 34])
def test_pages_overlap_so_that_a_window_showing_fewer_lines_than_its_page_size_loses_nothing(data_rows: int) -> None:
    lines = ["TOTAL~199~~~~~", *(_line(i) for i in range(199))]
    screen = _FakeListScreen(lines, data_rows=data_rows, page_size=36)
    assert _read_list_lines(_session(screen)) == lines


def test_a_list_without_scrollbars_is_read_as_one_page() -> None:
    lines = [_line(i) for i in range(10)]
    screen = _FakeListScreen(lines, scrollbars=False)
    assert _read_list_lines(_session(screen)) == lines


def test_a_scrollbar_with_page_size_zero_does_not_break_the_read() -> None:
    lines = [_line(i) for i in range(10)]
    screen = _FakeListScreen(lines, page_size=0)
    assert _read_list_lines(_session(screen)) == lines


def test_a_missing_slice_of_a_long_line_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    screen = _FakeListScreen([_line(0, 200)])
    original = screen.dump_tree

    def _dump_without_data_after_first_slice() -> list[Any]:
        elements = original()
        if screen.horizontal_scrollbar.position > 0:
            return [e for e in elements if "lbl[0,2]" not in e.id]
        return elements

    screen.dump_tree = _dump_without_data_after_first_slice  # type: ignore[method-assign]
    with caplog.at_level(logging.WARNING):
        lines = _read_list_lines(_session(screen))
    assert "no slice at position" in caplog.text
    assert len(lines) == 1  # the first slice is kept


# --- the wait predicate -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "expected"),
    [
        (["TOTAL~0~~~~~"], True),
        ([_line(0)], True),
        ([], False),  # only the fixed header on screen
        (["Invalid P_ACTION: XYZ. Use PULL or LIST."], False),
    ],
)
def test_abapgit_list_displayed(lines: list[str], expected: bool) -> None:
    assert _abapgit_list_displayed(_session(_FakeListScreen(lines))) is expected


@pytest.mark.anyio
async def test_a_timed_out_wait_for_the_list_does_not_stop_the_read(caplog: pytest.LogCaptureFixture) -> None:
    backend = _backend()
    backend.wait_for_condition = AsyncMock(return_value=False)
    with caplog.at_level(logging.WARNING):
        result = await _list(backend, [_line(0)])
    assert "did not show" in caplog.text
    assert result.success
    assert len(result.repos) == 1


# --- the TOTAL check -------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_repositories_skipped_by_the_parser_count_towards_the_total() -> None:
    # one online repository has no URL: it cannot be listed, but the list is complete
    lines = ["TOTAL~3~~~~~", _line(0), "Odd~~Z_ODD~refs/heads/main~~~", _line(2)]
    result = await _list(_backend(), lines)
    assert result.success
    assert [r.name for r in result.repos] == ["Repo0", "Repo2"]


@pytest.mark.anyio
async def test_an_incomplete_list_returns_what_was_read_together_with_the_error() -> None:
    result = await _list(_backend(), ["TOTAL~50~~~~~", *(_line(i) for i in range(10))])
    assert not result.success
    assert len(result.repos) == 10
    assert result.error is not None
    assert "50" in result.error


@pytest.mark.anyio
async def test_two_repositories_with_the_same_name_are_both_kept() -> None:
    lines = ["TOTAL~2~~~~~", _line(1), _line(1).replace("Z_PKG_1", "Z_PKG_OTHER")]
    result = await _list(_backend(), lines)
    assert result.success
    assert [r.package for r in result.repos] == ["Z_PKG_1", "Z_PKG_OTHER"]


# --- unreliable reads are not reported as complete ----------------------------------------------------------------


def test_an_unusable_horizontal_scrollbar_is_reported_as_a_problem() -> None:
    problems: list[str] = []
    screen = _FakeListScreen([_line(0, 200)])
    screen.horizontal_scrollbar.page_size = 0
    _read_list_lines(_session(screen), problems)
    assert problems


@pytest.mark.anyio
async def test_a_list_that_could_not_be_stitched_is_a_failure() -> None:
    backend = _backend()
    screen = _FakeListScreen([_line(0, 200)])
    screen.horizontal_scrollbar.page_size = 0
    backend.com.run = AsyncMock(side_effect=lambda fn: fn())
    backend.require_session = MagicMock(return_value=_session(screen))
    result = await _abapgit_list_repos(backend)
    assert not result.success
    assert result.error is not None
    assert "cut or damaged" in result.error


def test_scp_style_ssh_urls_are_listed() -> None:
    repos = parse_repo_list_output("Odd~git@host:org/odd~Z_ODD~refs/heads/main~~~")
    assert [(r.name, r.url) for r in repos] == [("Odd", "git@host:org/odd")]
