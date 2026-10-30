"""Unit tests for the abapGit repo-registration skip helpers used by the desktop integration tests."""

from __future__ import annotations

import pytest

from sapguimcp.models.abapgit_models import AbapGitListResult, AbapGitRepoInfo
from unittests.desktop import conftest as desktop_conftest
from unittests.desktop.conftest import repo_registered, require_repo_registered

REPO = "Z_PUBLIC_ABAPGIT_TEST_REPOSITORY"


def _info(name: str) -> AbapGitRepoInfo:
    return AbapGitRepoInfo(name=name, url="https://github.com/x/y", package="ZPKG", branch="refs/heads/main")


class _FakeBackend:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def press_key(self, key: str) -> None:
        self.keys.append(key)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    desktop_conftest._REPO_LIST_CACHE.clear()


def _patch_list(monkeypatch: pytest.MonkeyPatch, result: AbapGitListResult) -> list[int]:
    calls: list[int] = []

    async def fake(_backend: object) -> AbapGitListResult:
        calls.append(1)
        return result

    monkeypatch.setattr(desktop_conftest, "_abapgit_list_repos", fake)
    return calls


def test_repo_registered_present() -> None:
    assert repo_registered([_info("OTHER"), _info(REPO)], REPO)


def test_repo_registered_absent() -> None:
    assert not repo_registered([_info("OTHER")], REPO)


def test_repo_registered_empty_list() -> None:
    assert not repo_registered([], REPO)


@pytest.mark.parametrize("variant", [REPO.lower(), f" {REPO}", f"{REPO} "])
def test_repo_registered_is_exact_match(variant: str) -> None:
    """Matching is exact: abapGit names are upper-case, no normalisation."""
    assert not repo_registered([_info(variant)], REPO)


@pytest.mark.anyio
async def test_require_skips_when_absent_in_non_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_list(monkeypatch, AbapGitListResult(success=True, repos=[_info("OTHER")]))
    backend = _FakeBackend()
    with pytest.raises(pytest.skip.Exception) as exc:
        await require_repo_registered(backend, REPO)
    assert REPO in str(exc.value)
    assert "docs/SAP_TEST_PREREQUISITES.md" in str(exc.value)
    assert backend.keys == ["F3"] * 5  # went home before skipping


@pytest.mark.anyio
async def test_require_returns_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_list(monkeypatch, AbapGitListResult(success=True, repos=[_info(REPO)]))
    await require_repo_registered(_FakeBackend(), REPO)


@pytest.mark.anyio
async def test_require_does_not_skip_on_list_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_list(monkeypatch, AbapGitListResult(success=False, error="boom"))
    await require_repo_registered(_FakeBackend(), REPO)
    await require_repo_registered(_FakeBackend(), REPO)
    assert len(calls) == 2  # failures are not cached


@pytest.mark.anyio
async def test_require_does_not_skip_on_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_list(monkeypatch, AbapGitListResult(success=True, repos=[]))
    await require_repo_registered(_FakeBackend(), REPO)
    await require_repo_registered(_FakeBackend(), REPO)
    assert len(calls) == 2  # empty results are not cached


@pytest.mark.anyio
async def test_require_caches_successful_list(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_list(monkeypatch, AbapGitListResult(success=True, repos=[_info(REPO)]))
    await require_repo_registered(_FakeBackend(), REPO)
    await require_repo_registered(_FakeBackend(), REPO)
    assert len(calls) == 1
