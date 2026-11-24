"""sap_quick_report on the desktop backend, with a scripted fake backend (no SAP needed)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp import utils
from sapguimcp.models import ScreenText, TableData, TableRow
from sapguimcp.models.base import PopupInfo
from sapguimcp.models.quick_report_models import ScreenClassification
from sapguimcp.models.sap_results import FillFormResult, StatusBarInfo
from sapguimcp.tools.quick_report_tools import _execute_quick_report

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Screen:
    """One state of the SAP screen: what the backend reports while this screen is shown."""

    program: str = "SAPMSSY0"
    dynpro: str = "0120"
    status: tuple[str, str] = ("none", "")
    popup: PopupInfo | None = None
    table: TableData | None = None
    lines: list[str] = field(default_factory=list)


_SELECTION = _Screen(program="RSREPORT", dynpro="1000")
_POPUP = PopupInfo(title="Dialog", message="Choose")


def _table(rows: int, headers: tuple[str, ...] = ("A", "B")) -> TableData:
    return TableData(
        headers=list(headers),
        rows=[TableRow(row=i, data=dict.fromkeys(headers, str(i))) for i in range(1, rows + 1)],
        total_rows=rows,
    )


def _result_screen(rows: int = 1) -> _Screen:
    return _Screen(program="SAPLSLVC", dynpro="0500", table=_table(rows))


def _backend(*screens: _Screen) -> Any:
    """A backend that shows ``screens[0]`` after the transaction was entered; every key press moves one screen on."""
    backend = MagicMock()
    state = SimpleNamespace(index=0)

    def current() -> _Screen:
        return screens[min(state.index, len(screens) - 1)]

    async def press_key(_key: str) -> None:
        state.index += 1

    async def status() -> StatusBarInfo:
        kind, message = current().status
        return StatusBarInfo(type=kind, message=message)  # type: ignore[arg-type]

    async def screen_info() -> Any:
        return SimpleNamespace(program=current().program, dynpro=current().dynpro)

    async def read_table(**_: Any) -> TableData:
        return current().table or TableData()

    async def com_run(_func: Any, **_: Any) -> list[str]:
        return current().lines

    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.press_key = AsyncMock(side_effect=press_key)
    backend.get_status_bar = AsyncMock(side_effect=status)
    backend.get_screen_info = AsyncMock(side_effect=screen_info)
    backend.check_popup = AsyncMock(side_effect=lambda: current().popup)
    backend.read_table = AsyncMock(side_effect=read_table)
    backend.get_page_title = AsyncMock(return_value="Title")
    backend.get_screen_text = AsyncMock(return_value=ScreenText(title="Title"))
    backend.wait_for_ready = AsyncMock()
    backend.fill_form = AsyncMock(return_value=FillFormResult())
    backend.set_checkbox = AsyncMock()
    backend.set_radio_button = AsyncMock()
    backend.com.run = AsyncMock(side_effect=com_run)
    backend.require_session = MagicMock()
    return backend


async def _run(backend: Any, **kwargs: Any) -> Any:
    return await _execute_quick_report(backend, tcode="ZREP", **kwargs)


def _pressed(backend: Any) -> list[str]:
    return [call.args[0] for call in backend.press_key.await_args_list]


@pytest.mark.anyio
async def test_an_alv_result_is_returned_as_a_table() -> None:
    backend = _backend(_SELECTION, _result_screen(3))
    result = await _run(backend, max_rows=10)
    assert result.success
    assert result.screen_type == ScreenClassification.TABLE
    assert result.table is not None
    assert [r.data["A"] for r in result.table.rows] == ["1", "2", "3"]
    assert result.page_title == "Title"
    assert _pressed(backend) == ["F8"]
    assert backend.read_table.await_args.kwargs == {"max_rows": 10}
    backend.enter_transaction.assert_awaited_once_with("ZREP")


@pytest.mark.anyio
async def test_a_grid_without_rows_is_empty() -> None:
    result = await _run(_backend(_SELECTION, _result_screen(0)))
    assert result.screen_type == ScreenClassification.EMPTY
    assert result.table is None


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["S", "I"])
async def test_a_message_on_the_selection_screen_means_no_data(kind: str) -> None:
    backend = _backend(_SELECTION, _Screen(program="RSREPORT", dynpro="1000", status=(kind, "whatever it says")))
    result = await _run(backend)
    assert result.screen_type == ScreenClassification.EMPTY
    assert result.status_bar_message == "whatever it says"
    assert result.status_bar_type == kind
    assert result.screen_text is None


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["E", "W"])
async def test_an_error_or_warning_is_an_error_with_the_screen_text(kind: str) -> None:
    backend = _backend(_SELECTION, _Screen(program="RSREPORT", dynpro="1000", status=(kind, "refused")))
    result = await _run(backend)
    assert result.success
    assert result.screen_type == ScreenClassification.ERROR
    assert result.status_bar_message == "refused"
    assert result.screen_text is not None


@pytest.mark.anyio
async def test_an_error_wins_over_a_table_on_screen() -> None:
    backend = _backend(_SELECTION, _Screen(dynpro="0500", status=("E", "broken"), table=_table(2)))
    result = await _run(backend)
    assert result.screen_type == ScreenClassification.ERROR
    assert result.table is None


@pytest.mark.anyio
async def test_a_warning_next_to_a_result_still_returns_the_result() -> None:
    backend = _backend(_SELECTION, _Screen(dynpro="0500", status=("W", "partial"), table=_table(1)))
    result = await _run(backend)
    assert result.screen_type == ScreenClassification.TABLE
    assert result.status_bar_type == "W"


@pytest.mark.anyio
async def test_staying_on_the_selection_screen_without_a_message_is_an_error() -> None:
    result = await _run(_backend(_SELECTION, _Screen(program="RSREPORT", dynpro="1000")))
    assert result.screen_type == ScreenClassification.ERROR
    assert result.screen_text is not None


@pytest.mark.anyio
async def test_a_classic_list_is_returned_as_lines() -> None:
    backend = _backend(_SELECTION, _Screen(program="RSREPORT", dynpro="1001", lines=["head", "row 1"]))
    result = await _run(backend, max_rows=5)
    assert result.screen_type == ScreenClassification.LIST
    assert result.list_lines == ["head", "row 1"]
    assert result.table is None


@pytest.mark.anyio
async def test_an_unrecognised_screen_is_unknown_with_the_screen_text() -> None:
    result = await _run(_backend(_SELECTION, _Screen(program="SAPLXYZ", dynpro="0100")))
    assert result.screen_type == ScreenClassification.UNKNOWN
    assert result.screen_text is not None


@pytest.mark.anyio
async def test_post_f8_keys_dismiss_a_popup() -> None:
    backend = _backend(_SELECTION, _Screen(program="SAPLSPO1", dynpro="0100", popup=_POPUP), _result_screen())
    result = await _run(backend, post_f8_keys=["Enter"])
    assert result.screen_type == ScreenClassification.TABLE
    assert _pressed(backend) == ["F8", "Enter"]


@pytest.mark.anyio
async def test_a_popup_without_post_f8_keys_is_reported_with_the_popup() -> None:
    result = await _run(_backend(_SELECTION, _Screen(program="SAPLSPO1", dynpro="0100", popup=_POPUP)))
    assert result.screen_type == ScreenClassification.UNKNOWN
    assert result.popup == _POPUP


@pytest.mark.anyio
async def test_post_f8_keys_are_limited_to_three() -> None:
    backend = _backend(_SELECTION, _Screen(program="SAPLSPO1", dynpro="0100", popup=_POPUP))
    result = await _run(backend, post_f8_keys=["Enter"] * 5)
    assert _pressed(backend) == ["F8", "Enter", "Enter", "Enter"]
    assert any("post_f8_keys" in w for w in result.warnings)


@pytest.mark.anyio
async def test_post_f8_keys_are_not_pressed_once_the_result_is_there() -> None:
    backend = _backend(_SELECTION, _result_screen())
    await _run(backend, post_f8_keys=["Enter"])
    assert _pressed(backend) == ["F8"]


@pytest.mark.anyio
async def test_the_selection_is_filled_before_f8() -> None:
    backend = _backend(_SELECTION, _result_screen())
    order: list[str] = []

    async def fill_form(_fields: dict[str, str]) -> FillFormResult:
        order.append("fields")
        return FillFormResult()

    backend.fill_form.side_effect = fill_form
    backend.set_checkbox.side_effect = lambda label, checked: order.append(f"chk {label}={checked}")
    backend.set_radio_button.side_effect = lambda label: order.append(f"rad {label}")
    backend.press_key.side_effect = order.append
    result = await _run(
        backend, fields={"Name": "X*"}, checkboxes={"Flag": True, "Other": False}, radios={"Choice": True}
    )
    assert order == ["fields", "chk Flag=True", "chk Other=False", "rad Choice", "F8"]
    backend.fill_form.assert_awaited_once_with({"Name": "X*"})
    assert result.success


@pytest.mark.anyio
async def test_a_radio_button_set_to_false_is_a_warning() -> None:
    backend = _backend(_SELECTION, _result_screen())
    result = await _run(backend, radios={"Choice": False})
    backend.set_radio_button.assert_not_awaited()
    assert any("Choice" in w for w in result.warnings)


@pytest.mark.anyio
async def test_a_field_that_is_not_found_fails_before_f8() -> None:
    backend = _backend(_SELECTION, _result_screen())
    backend.fill_form.return_value = FillFormResult(success=False, error="Fields not found: Nope", not_found=["Nope"])
    result = await _run(backend, fields={"Nope": "1"})
    assert not result.success
    assert "Nope" in (result.error or "")
    backend.press_key.assert_not_awaited()


@pytest.mark.anyio
async def test_a_checkbox_that_is_not_found_fails_before_f8() -> None:
    backend = _backend(_SELECTION, _result_screen())
    backend.set_checkbox.side_effect = ValueError("Checkbox not found: Flag")
    result = await _run(backend, checkboxes={"Flag": True})
    assert not result.success
    assert "Flag" in (result.error or "")
    backend.press_key.assert_not_awaited()


@pytest.mark.anyio
async def test_a_transaction_that_does_not_open_fails() -> None:
    backend = _backend(_SELECTION)
    backend.enter_transaction.return_value = SimpleNamespace(success=False, error="COM broke")
    result = await _run(backend)
    assert not result.success
    assert "COM broke" in (result.error or "")
    backend.press_key.assert_not_awaited()


@pytest.mark.anyio
async def test_an_error_in_the_status_bar_after_entering_the_transaction_fails() -> None:
    backend = _backend(_Screen(program="SAPLSMTR_NAVIGATION", status=("E", "Transaction ZREP does not exist")))
    result = await _run(backend, fields={"Name": "X"})
    assert not result.success
    assert "does not exist" in (result.error or "")
    backend.fill_form.assert_not_awaited()
    backend.press_key.assert_not_awaited()


@pytest.mark.anyio
async def test_max_rows_below_one_is_rejected() -> None:
    result = await _run(_backend(_SELECTION), max_rows=0)
    assert not result.success
    assert "max_rows" in (result.error or "")


@pytest.mark.anyio
async def test_a_com_error_becomes_a_failure_result() -> None:
    backend = _backend(_SELECTION)
    backend.press_key.side_effect = RuntimeError("COM gone")
    result = await _run(backend)
    assert not result.success
    assert "COM gone" in (result.error or "")


@pytest.mark.anyio
async def test_the_result_is_written_to_the_output_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(utils, "_default_output_base_dir", lambda: tmp_path)
    result = await _run(_backend(_SELECTION, _result_screen(2)), output_file="out.json")
    written = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert written["screen_type"] == "table"
    assert len(written["table"]["rows"]) == 2
    assert result.screen_type == ScreenClassification.TABLE


@pytest.mark.anyio
async def test_an_output_file_outside_the_sandbox_fails_before_the_report_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(utils, "_default_output_base_dir", lambda: tmp_path)
    backend = _backend(_SELECTION, _result_screen())
    result = await _run(backend, output_file="../outside.json")
    assert not result.success
    assert "output_file" in (result.error or "")
    backend.enter_transaction.assert_not_awaited()
