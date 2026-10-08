"""SLG1 on the desktop backend: an empty grid without a 'no logs' status is a failure, not an empty result."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.models import TableData
from sapguimcp.tools.slg1_tools import _slg1_lookup_desktop


def _backend(status_message: str, table: TableData) -> Any:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.fill_form = AsyncMock(return_value=SimpleNamespace(not_found=[]))
    for name in ("wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=status_message))
    backend.read_table = AsyncMock(return_value=table)
    return backend


async def _lookup(backend: Any) -> Any:
    config = MagicMock()
    config.get_default.return_value = SimpleNamespace(language="EN")
    with patch("sapguimcp.tools.slg1_tools.get_sap_config", return_value=config):
        return await _slg1_lookup_desktop(backend, "OBJ")


@pytest.mark.anyio
async def test_an_empty_grid_without_a_no_logs_status_is_a_failure() -> None:
    result = await _lookup(_backend("", TableData(success=True, headers=["Message"], rows=[])))
    assert not result.success
    assert result.logs == []


@pytest.mark.anyio
async def test_the_no_logs_status_is_still_an_empty_result() -> None:
    backend = _backend("No application log found", TableData(success=True))
    result = await _lookup(backend)
    assert result.success
    assert result.logs == []
    backend.read_table.assert_not_called()
