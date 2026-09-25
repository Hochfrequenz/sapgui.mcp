"""Unit tests for SE16 filter warning propagation."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from sapguimcp.models import ScreenInfo, StatusBarInfo, TableData, TableRow, TransactionResult
from sapguimcp.models.se16_models import SE16Result, SE16Row
from sapguimcp.tools.se16_tools import _execute_se16_query_desktop


def _make_desktop_backend() -> AsyncMock:
    backend = AsyncMock()
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=TransactionResult(tcode="SE16N"))
    backend.wait_for_ready = AsyncMock()
    backend.wait = AsyncMock()
    backend.get_screen_info = AsyncMock(
        return_value=ScreenInfo(
            title="SE16N",
            url="sap://session",
            transaction="SE16N",
            program="SAPLSE16N",
        )
    )
    backend.focus_and_type = AsyncMock(side_effect=[True, True])
    backend.press_key = AsyncMock()
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type="S", message=""))
    backend.read_table = AsyncMock(
        return_value=TableData(
            headers=["TCODE"],
            rows=[TableRow(row=1, data={"TCODE": "SE16"})],
            total_rows=1,
        )
    )
    backend.get_page_title = AsyncMock(return_value="SE16N: Display of Entries Found")
    return backend


class TestSE16ResultFilterWarnings:
    """Tests for the SE16 filter_warnings payload."""

    def test_defaults_to_empty_list(self) -> None:
        result = SE16Result(
            table="TSTC",
            total_hits=1,
            returned_rows=1,
            truncated=False,
            columns=["TCODE"],
            rows=[SE16Row(data={"TCODE": "SE16"})],
            retrieved_at=datetime.now(UTC),
        )

        assert result.filter_warnings == []

    def test_json_roundtrip(self) -> None:
        original = SE16Result(
            table="TSTC",
            total_hits=1,
            returned_rows=1,
            truncated=False,
            columns=["TCODE"],
            rows=[SE16Row(data={"TCODE": "SE16"})],
            filter_warnings=["Field 'ZZZFAKE' not found in SE16N selection criteria"],
            retrieved_at=datetime.now(UTC),
        )

        restored = SE16Result.model_validate_json(original.model_dump_json())

        assert restored.filter_warnings == original.filter_warnings


@pytest.mark.anyio
async def test_execute_se16_query_desktop_returns_filter_warnings() -> None:
    backend = _make_desktop_backend()
    warnings = [
        "Field 'ZZZFAKE' not found in SE16N selection criteria",
        "Field 'MANDT' could not be applied because the selection criteria table control was not found",
    ]

    with patch("sapguimcp.tools.se16_tools._fill_se16n_filters_desktop", new=AsyncMock(return_value=warnings)):
        result = await _execute_se16_query_desktop(
            backend,
            table="TSTC",
            filters={"ZZZFAKE": "X", "MANDT": "100"},
            max_hits=10,
            now=datetime.now(UTC),
        )

    assert result.success is True
    assert result.filter_warnings == warnings
    assert result.returned_rows == 1
    assert result.rows[0].data["TCODE"] == "SE16"
    assert backend.press_key.await_args_list[0].args == ("Enter",)
    assert backend.press_key.await_args_list[-1].args == ("F8",)
