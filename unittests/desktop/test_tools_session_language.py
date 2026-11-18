"""SLG1, SM37 and ST22 take the logon language of the session, not that of the default system (#1044)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp import lang
from sapguimcp.models import TableData
from sapguimcp.tools.slg1_tools import _slg1_lookup_desktop
from sapguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop
from sapguimcp.tools.st22_tools import _execute_search


@pytest.mark.anyio
@pytest.mark.parametrize(("language", "expected"), [("DE", "10.11.2026"), ("EN", "11/10/2026")])
async def test_st22_formats_the_date_in_the_session_language(language: str, expected: str) -> None:
    backend = MagicMock()
    backend.press_key = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.fill_field = AsyncMock()
    with (
        patch("sapguimcp.tools.st22_tools._try_quick_button", AsyncMock(return_value=False)),
        patch("sapguimcp.tools.st22_tools._clear_user_field", AsyncMock()),
    ):
        await _execute_search(backend, lang.view_for(language), "2026-11-10")
    assert backend.fill_field.await_args.args[1] == expected


@pytest.mark.anyio
@pytest.mark.parametrize(("language", "expected"), [("DE", "10.11.2026"), ("EN", "11/10/2026")])
async def test_sm37_formats_the_date_in_the_session_language(language: str, expected: str) -> None:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    for name in ("wait_for_ready", "press_key", "set_checkbox", "fill_field"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    no_jobs = lang.view_for(language).sm37.no_jobs.variants[0]
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=no_jobs))
    await _execute_sm37_lookup_desktop(backend, lang.view_for(language), "*", None, None, "2026-11-10", None)
    typed = {call.args[0]: call.args[1] for call in backend.focus_and_type.await_args_list}
    assert typed["BTCH2170-FROM_DATE"] == expected


@pytest.mark.anyio
@pytest.mark.parametrize(("language", "expected"), [("DE", "10.11.2026"), ("EN", "11/10/2026")])
async def test_slg1_formats_the_date_in_the_session_language(language: str, expected: str) -> None:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.fill_form = AsyncMock(return_value=SimpleNamespace(not_found=[], errors=[]))
    backend.focus_and_type = AsyncMock(return_value=True)
    for name in ("wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
    backend.read_table = AsyncMock(return_value=TableData(success=True, headers=[], rows=[]))
    backend.require_session = MagicMock()
    backend.com = MagicMock()
    backend.com.run = AsyncMock(return_value=([], False))
    await _slg1_lookup_desktop(backend, lang.view_for(language), "OBJ", None, None, "2026-11-10", None)
    typed = [call.args[1] for call in backend.focus_and_type.await_args_list]
    assert expected in typed


@pytest.mark.anyio
async def test_the_language_pack_beats_the_default_systems_language() -> None:
    """The default system is DE, the pack handed down is EN: the pack wins (#1044)."""
    config = MagicMock()
    config.get_default.return_value.language = "DE"
    backend = MagicMock()
    backend.press_key = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.fill_field = AsyncMock()
    with (
        patch("sapguimcp.models.config.get_sap_config", return_value=config),
        patch("sapguimcp.tools.st22_tools._try_quick_button", AsyncMock(return_value=False)),
        patch("sapguimcp.tools.st22_tools._clear_user_field", AsyncMock()),
    ):
        await _execute_search(backend, lang.view_for("EN"), "2026-11-10")
    assert backend.fill_field.await_args.args[1] == "11/10/2026"
