"""SM37 on the desktop backend: a status bar saying that no job matches is an empty result, not a failure."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop


def _backend(status_message: str) -> Any:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    for name in ("wait_for_ready", "focus_and_type", "press_key", "set_checkbox", "fill_field"):
        setattr(backend, name, AsyncMock())
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=status_message))
    backend.read_table = AsyncMock(side_effect=AssertionError("there is no list to read"))
    return backend


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    [
        "Kein Job entspricht den Selektionsbedingungen",
        "No job matches the selection criteria",
        "Keine Jobs gefunden",
        "No jobs found",
    ],
)
async def test_a_status_bar_without_matching_jobs_is_an_empty_result(message: str) -> None:
    config = MagicMock()
    config.get_default.return_value = SimpleNamespace(language="DE")
    with patch("sapguimcp.tools.sm37_tools.get_sap_config", return_value=config):
        result = await _execute_sm37_lookup_desktop(_backend(message), "*", None, None, None, None)
    assert result.success
    assert result.jobs == []
    assert result.job_count == 0
