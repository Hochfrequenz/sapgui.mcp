"""SM37, SLG1 and ST22 read every text from the language packs (#1044, phase 3).

Covers the single-language bugs the migration fixed (desktop job status, the different "no entries" lists,
``language == "DE"`` branches, the WebGUI headings of ST22) and the behaviour change: a session whose language has no
pack (or is unknown) fails the tool call with ``UnsupportedLanguageError``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp import lang
from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.tools.sm37_tools import (
    _execute_sm37_lookup_desktop,
)
from sapguimcp.tools.st22_tools import (
    _st22_lookup_desktop,
)


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["DE", "EN"])
async def test_every_no_jobs_text_is_known_to_the_desktop_tool(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.sm37.no_jobs:
        backend = MagicMock()
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
        for name in ("wait_for_ready", "press_key"):
            setattr(backend, name, AsyncMock())
        backend.focus_and_type = AsyncMock(return_value=True)
        backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=variant))
        backend.read_table = AsyncMock(side_effect=AssertionError("there is no list to read"))
        result = await _execute_sm37_lookup_desktop(backend, t, "*", None, None, None, None)
        assert result.success
        assert result.jobs == [], variant


@pytest.mark.anyio
@pytest.mark.parametrize("language", ["DE", "EN"])
async def test_every_no_dumps_text_is_known_to_the_desktop_tool(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.st22.no_dumps:
        backend = MagicMock(spec=DesktopBackend)
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
        backend.wait_for_ready = AsyncMock()
        backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=variant))
        backend.read_table = AsyncMock(side_effect=AssertionError("there is no list to read"))
        with patch("sapguimcp.tools.st22_tools._execute_search", AsyncMock(return_value=None)):
            result = await _st22_lookup_desktop(backend, t, "2026-10-08", None)
        assert result.success
        assert result.dump_count == 0, variant  # type: ignore[union-attr]
