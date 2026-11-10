"""Unit tests for the per-session SAP language context variable (#1044, phase 1)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from sapguimcp.session_language import (
    current_language,
    normalize_language,
    session_sap_language,
    set_session_language,
    use_language,
)


def test_default_is_none() -> None:
    assert current_language() is None


def test_use_language_sets_and_restores() -> None:
    with use_language("DE"):
        assert current_language() == "DE"
        with use_language("EN"):
            assert current_language() == "EN"
        assert current_language() == "DE"
    assert current_language() is None


@pytest.mark.parametrize(("raw", "expected"), [("de", "DE"), (" En ", "EN"), ("", None), (None, None)])
def test_normalize_language(raw: str | None, expected: str | None) -> None:
    assert normalize_language(raw) == expected


def test_set_session_language_normalizes() -> None:
    with use_language(None):
        set_session_language("de")
        assert current_language() == "DE"


@pytest.mark.anyio
async def test_tasks_are_isolated() -> None:
    async def worker(code: str) -> str | None:
        set_session_language(code)
        await asyncio.sleep(0)
        return current_language()

    results = await asyncio.gather(worker("DE"), worker("EN"))
    assert results == ["DE", "EN"]
    assert current_language() is None


def test_session_sap_language_uses_context() -> None:
    with use_language("DE"):
        assert session_sap_language() == "DE"


def test_session_sap_language_falls_back_to_default_system() -> None:
    cfg = MagicMock()
    cfg.get_default.return_value.language = "DE"
    with use_language(None), patch("sapguimcp.models.config.get_sap_config", return_value=cfg):
        assert session_sap_language() == "DE"
