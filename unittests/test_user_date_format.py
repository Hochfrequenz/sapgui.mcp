"""The user's date format is derived from the date a selection screen pre-fills (#1043)."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from sapguimcp.user_date_format import derive_date_format, resolve_user_date_format


@pytest.mark.parametrize(
    ("shown", "expected"),
    [
        ("07.10.2026", "%d.%m.%Y"),
        ("10/07/2026", "%m/%d/%Y"),
        ("10-07-2026", "%m-%d-%Y"),
        ("2026.10.07", "%Y.%m.%d"),
        ("2026/10/07", "%Y/%m/%d"),
        ("2026-10-07", "%Y-%m-%d"),
        (" 07.10.2026 ", "%d.%m.%Y"),
    ],
)
def test_the_format_is_read_off_the_shape_of_the_date(shown: str, expected: str) -> None:
    assert derive_date_format(shown) == expected


@pytest.mark.parametrize(
    "shown",
    [None, "", "  ", "00.00.0000", "31.02.2026", "07.10.26", "garbage", "1448/05/10", "0008.10.07", "13/25/2026"],
)
def test_an_empty_invalid_or_non_gregorian_date_gives_no_format(shown: str | None) -> None:
    """Includes impossible dates and the year counts of SAP's Japanese and Islamic formats."""
    assert derive_date_format(shown) is None


def test_any_date_works_not_only_today() -> None:
    """The shape decides, so a pre-filled date from another day or time zone still gives the format."""
    assert derive_date_format("01.01.2020") == "%d.%m.%Y"
    assert derive_date_format("12/31/2025") == "%m/%d/%Y"


@pytest.mark.parametrize(
    ("shown", "expected"),
    [
        ("11.11.2026", "%d.%m.%Y"),
        ("11/11/2026", "%m/%d/%Y"),
        ("11-11-2026", "%m-%d-%Y"),
        ("2026.11.11", "%Y.%m.%d"),
        ("2026/11/11", "%Y/%m/%d"),
        ("2026-11-11", "%Y-%m-%d"),
    ],
)
def test_a_day_equal_to_the_month_is_resolved_by_the_shape(shown: str, expected: str) -> None:
    assert derive_date_format(shown) == expected


def _backend(shown: str | None, cached: str | None = None) -> Any:
    store: dict[str, str] = {}
    if cached:
        store["f"] = cached
    return SimpleNamespace(
        cached_date_format=lambda: store.get("f"),
        cache_date_format=lambda f: store.__setitem__("f", f),
        read_field_text=AsyncMock(return_value=shown),
    )


@pytest.mark.anyio
async def test_the_derived_format_is_cached_per_session() -> None:
    backend = _backend("2026-10-07")
    assert await resolve_user_date_format(backend, ("F",), "%d.%m.%Y") == "%Y-%m-%d"
    assert await resolve_user_date_format(backend, ("F",), "%d.%m.%Y") == "%Y-%m-%d"
    backend.read_field_text.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("shown", [None, "garbage", "1448/05/10"])
async def test_the_logon_language_default_is_the_fallback_and_is_logged(
    shown: str | None, caplog: pytest.LogCaptureFixture
) -> None:
    backend = _backend(shown)
    with caplog.at_level(logging.WARNING):
        assert await resolve_user_date_format(backend, ("F",), "%m/%d/%Y") == "%m/%d/%Y"
    assert "falling back" in caplog.text
    assert backend.cached_date_format() is None  # a fallback is not cached


@pytest.mark.anyio
async def test_a_field_that_cannot_be_read_falls_back() -> None:
    backend = _backend(None)
    backend.read_field_text = AsyncMock(side_effect=RuntimeError("boom"))
    assert await resolve_user_date_format(backend, ("F",), "%d.%m.%Y") == "%d.%m.%Y"


@pytest.mark.anyio
async def test_sm37_types_the_dates_in_the_format_of_the_user() -> None:
    from unittest.mock import MagicMock  # noqa: PLC0415

    from sapguimcp import lang  # noqa: PLC0415
    from sapguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop  # noqa: PLC0415

    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    for name in ("wait_for_ready", "press_key", "set_checkbox", "fill_field"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message="Kein Job entspricht"))
    backend.cached_date_format = lambda: None
    backend.cache_date_format = lambda _f: None
    backend.read_field_text = AsyncMock(return_value="2026-10-07")
    await _execute_sm37_lookup_desktop(backend, lang.view_for("DE"), "*", None, None, "2026-10-01", "2026-10-08")
    typed = {c.args[0]: c.args[1] for c in backend.focus_and_type.await_args_list}
    assert typed["BTCH2170-FROM_DATE"] == "2026-10-01"
    assert typed["BTCH2170-TO_DATE"] == "2026-10-08"
