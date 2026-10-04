"""Tests for placing SE16N filters by field name on the Web GUI backend (#924).

SE16N does not offer every SE11 field as a selection field. Placing a filter by its SE11 position
therefore put the value into the row of a different field (or none) without any error.

The JS tests run ``read_se16n_selection_rows.js`` against a synthetic grid. Its structure is copied
from what a live SAP Web GUI rendered (captured while developing #924): a split table in which the
label column and the other columns sit in different ``<tr>`` elements, every cell carries an
``lsdata`` SID such as ``.../ctxtGS_SELFIELDS-LOW[2,0]`` (column, row), the From-Value control is a
``role="textbox"`` span, the technical name is the ``FIELDNAME`` cell (column 6), and the grid is padded
with empty rows. The live evidence is in ``unittests/webgui/testdata/se16_exploration``. The tests need a
Chromium that Playwright can launch (set ``PLAYWRIGHT_CHROMIUM_EXECUTABLE`` to use a specific build)
and are skipped otherwise; CI does not install browsers, so CI skips them.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import async_playwright

import sapguimcp
from sapguimcp.backend.webgui.backend import WebGuiBackend
from sapguimcp.tools import se16_tools
from sapguimcp.tools.se16_tools import (
    _fill_se16n_filters_webgui,
    _filter_fill_failure,
    _FilterFillResult,
    _GridRow,
    _parse_grid_rows,
    _plan_se16n_filters,
)

pytestmark = pytest.mark.anyio

JS_DIR = Path(sapguimcp.__file__).parent / "backend" / "webgui" / "js"
READ_ROWS_JS = JS_DIR / "read_se16n_selection_rows.js"


def _row(index: int, name: str | None, *, fillable: bool = True, label: str = "x") -> _GridRow:
    return _GridRow(
        row_index=index,
        label=label,
        field_name=name,
        fillable=fillable,
        element_id=f"low{index}" if fillable else None,
        selector=f"#low{index}" if fillable else None,
    )


class TestPlanByTechnicalName:
    """Every row shows its technical name: filters are matched by name, never by position."""

    def test_filter_goes_into_the_row_that_carries_its_name_when_se16n_left_a_field_out(self) -> None:
        # SE11 order is A, B, C. SE16N leaves B out, so C is row 1 and not row 2.
        rows = [_row(0, "A"), _row(1, "C")]
        plan = _plan_se16n_filters(rows, {"C": "x"}, {"A": 0, "B": 1, "C": 2}, "T")
        assert [(name, value, row.row_index) for name, value, row in plan.targets] == [("C", "x", 1)]
        assert plan.result.unapplied_fields == []
        assert plan.result.other_errors == []

    def test_field_that_se16n_does_not_offer_is_unapplied_not_misplaced(self) -> None:
        rows = [_row(0, "A"), _row(1, "C")]
        plan = _plan_se16n_filters(rows, {"B": "x"}, {"A": 0, "B": 1, "C": 2}, "T")
        assert plan.targets == []
        assert plan.result.unapplied_fields == ["B"]
        assert plan.result.offered_fields == ["A", "C"]

    def test_a_shown_row_without_an_input_is_not_offered(self) -> None:
        # SE16N shows the client field but gives it no input.
        rows = [_row(0, "MANDT", fillable=False), _row(1, "MATNR")]
        plan = _plan_se16n_filters(rows, {"MANDT": "100"}, None, "T")
        assert plan.targets == []
        assert plan.result.unapplied_fields == ["MANDT"]
        assert plan.result.offered_fields == ["MATNR"]

    def test_match_is_case_insensitive_and_reports_the_requested_spelling(self) -> None:
        plan = _plan_se16n_filters([_row(0, "TCODE")], {"tcode": "SE16"}, None, "T")
        assert [(name, row.row_index) for name, _, row in plan.targets] == [("tcode", 0)]

    def test_se11_is_not_needed_when_names_are_readable(self) -> None:
        plan = _plan_se16n_filters([_row(0, "A")], {"A": "1"}, None, "T")
        assert len(plan.targets) == 1
        assert plan.result.other_errors == []

    def test_empty_grid_is_an_error(self) -> None:
        plan = _plan_se16n_filters([], {"A": "1"}, {"A": 0}, "T")
        assert plan.targets == []
        assert plan.result.other_errors == ["SE16N selection criteria grid has no rows"]


class TestPartlyRenderedGrid:
    """The Web GUI renders only the first rows of the grid; the failure must not claim a field is not offered."""

    def test_hint_when_se11_lists_more_fields_than_the_grid_shows(self) -> None:
        rows = [_row(0, "A"), _row(1, "B")]
        plan = _plan_se16n_filters(rows, {"Z": "x"}, {"A": 0, "B": 1, "Z": 2}, "T")
        assert plan.result.unapplied_fields == ["Z"]
        assert plan.result.hint is not None
        assert "renders only the first rows of the grid (2 here)" in plan.result.hint
        assert "a field further down table T cannot be reached" in plan.result.hint

    def test_hint_when_the_grid_has_no_free_row_left_even_without_se11(self) -> None:
        plan = _plan_se16n_filters([_row(0, "A")], {"Z": "x"}, None, "T", possibly_truncated=True)
        assert plan.result.hint is not None

    def test_no_hint_when_the_counts_match(self) -> None:
        plan = _plan_se16n_filters([_row(0, "A")], {"Z": "x"}, {"A": 0}, "T")
        assert plan.result.hint is None

    def test_the_hint_is_part_of_the_failure_message_without_unapplied_fields_too(self) -> None:
        # Names unreadable and the row count differs from SE11: only other_errors, but the hint still explains.
        rows = [_row(0, None)]
        plan = _plan_se16n_filters(rows, {"Z": "x"}, {"A": 0, "Z": 1}, "T")
        assert plan.result.unapplied_fields == []
        error = _filter_fill_failure(plan.result, "T", datetime.now(UTC)).error or ""
        assert error.startswith("Could not apply filters: SE16N offers 1 selection rows")
        assert "renders only the first rows of the grid" in error

    def test_the_hint_is_part_of_the_failure_message(self) -> None:
        rows = [_row(0, "A")]
        plan = _plan_se16n_filters(rows, {"Z": "x"}, {"A": 0, "Z": 1}, "T")
        error = _filter_fill_failure(plan.result, "T", datetime.now(UTC)).error or ""
        assert "'Z' not available as SE16N selection criteria for table T" in error
        assert "renders only the first rows of the grid" in error


class TestPlanWithoutTechnicalNames:
    """Names are not in the DOM: SE11 positions are used only when the row count provably fits."""

    def test_se11_positions_are_used_when_the_row_count_matches(self) -> None:
        rows = [_row(0, None), _row(1, None), _row(2, None)]
        plan = _plan_se16n_filters(rows, {"C": "x"}, {"A": 0, "B": 1, "C": 2}, "T")
        assert [(name, row.row_index) for name, _, row in plan.targets] == [("C", 2)]
        assert plan.result.other_errors == []

    def test_a_missing_row_means_positions_cannot_be_trusted(self) -> None:
        rows = [_row(0, None), _row(1, None)]  # SE16N left one SE11 field out
        plan = _plan_se16n_filters(rows, {"C": "x"}, {"A": 0, "B": 1, "C": 2}, "T")
        assert plan.targets == []
        expected = (
            "SE16N offers 2 selection rows for table T but SE11 lists 3 fields; "
            "row positions may not match field names, so no filter was applied"
        )
        assert plan.result.other_errors == [expected]

    def test_one_unreadable_name_is_enough_to_fall_back(self) -> None:
        rows = [_row(0, "A"), _row(1, None)]
        plan = _plan_se16n_filters(rows, {"A": "x"}, {"A": 0, "B": 1}, "T")
        assert [row.row_index for _, _, row in plan.targets] == [0]  # via SE11, count 2 == 2

    def test_without_se11_nothing_can_be_verified(self) -> None:
        plan = _plan_se16n_filters([_row(0, None)], {"A": "x"}, None, "T")
        assert plan.targets == []
        assert "cannot be verified" in plan.result.other_errors[0]

    def test_unfillable_rows_are_not_offered_in_the_fallback(self) -> None:
        rows = [_row(0, None, fillable=False), _row(1, None)]
        plan = _plan_se16n_filters(rows, {"ZZ": "x"}, {"A": 0, "B": 1}, "T")
        assert plan.result.unapplied_fields == ["ZZ"]
        assert plan.result.offered_fields == ["B"]

    def test_unknown_field_is_unapplied_and_se11_names_are_offered(self) -> None:
        rows = [_row(0, None), _row(1, None)]
        plan = _plan_se16n_filters(rows, {"ZZ": "x"}, {"A": 0, "B": 1}, "T")
        assert plan.result.unapplied_fields == ["ZZ"]
        assert plan.result.offered_fields == ["A", "B"]

    def test_a_row_without_an_input_is_unapplied(self) -> None:
        rows = [_row(0, None, fillable=False), _row(1, None)]
        plan = _plan_se16n_filters(rows, {"A": "x"}, {"A": 0, "B": 1}, "T")
        assert plan.targets == []
        assert plan.result.unapplied_fields == ["A"]


def _backend(grid: dict[str, Any], fill: Any = True) -> MagicMock:
    backend = MagicMock(spec=WebGuiBackend)
    backend.load_js.return_value = "(args) => ({})"
    backend.evaluate_javascript = AsyncMock(return_value=grid)
    backend.fill_element_by_locator = AsyncMock(return_value=fill)
    return backend


def _grid(*rows: tuple[int, str | None], padding: bool = True) -> dict[str, Any]:
    return {
        "success": True,
        "hasPaddingRows": padding,
        "rows": [
            {
                "rowIndex": index,
                "label": f"label {index}",
                "fieldName": name,
                "fillable": True,
                "elementId": f"low{index}",
                "selector": f"#low{index}",
            }
            for index, name in rows
        ],
    }


class TestFillWebGui:
    async def test_fills_the_input_of_the_row_matched_by_name(self) -> None:
        backend = _backend(_grid((0, "A"), (1, "C")))
        result = await _fill_se16n_filters_webgui(backend, "T", {"C": "x"}, {"A": 0, "B": 1, "C": 2})
        assert result.unapplied_fields == []
        assert result.other_errors == []
        backend.fill_element_by_locator.assert_awaited_once_with('[id="low1"]', "x")

    async def test_unavailable_field_fills_nothing(self) -> None:
        backend = _backend(_grid((0, "A"), (1, "C")))
        result = await _fill_se16n_filters_webgui(backend, "T", {"B": "x"}, {"A": 0, "B": 1, "C": 2})
        assert result.unapplied_fields == ["B"]
        backend.fill_element_by_locator.assert_not_awaited()

    async def test_a_grid_without_padding_rows_is_reported_as_possibly_truncated(self) -> None:
        backend = _backend(_grid((0, "A"), padding=False))
        result = await _fill_se16n_filters_webgui(backend, "T", {"Z": "x"}, None)
        assert result.unapplied_fields == ["Z"]
        assert result.hint is not None

    async def test_a_grid_with_padding_rows_has_no_truncation_hint(self) -> None:
        backend = _backend(_grid((0, "A")))
        result = await _fill_se16n_filters_webgui(backend, "T", {"Z": "x"}, None)
        assert result.hint is None

    async def test_grid_read_failure_is_reported(self) -> None:
        backend = _backend({"success": False, "error": "Selection criteria grid not found"})
        result = await _fill_se16n_filters_webgui(backend, "T", {"A": "x"}, None)
        assert result.other_errors == ["Selection criteria grid not found"]

    async def test_failed_fill_is_reported(self) -> None:
        backend = _backend(_grid((0, "A")), fill=False)
        result = await _fill_se16n_filters_webgui(backend, "T", {"A": "x"}, None)
        assert result.other_errors == ["Found the selection row for A but filling it failed"]

    async def test_fill_exception_is_reported_not_raised(self) -> None:
        # _fill_filter_by_locator swallows protocol errors and reports a failed fill.
        backend = _backend(_grid((0, "A")))
        backend.fill_element_by_locator.side_effect = RuntimeError("boom")
        result = await _fill_se16n_filters_webgui(backend, "T", {"A": "x"}, None)
        assert result.other_errors == ["Found the selection row for A but filling it failed"]

    def test_parse_grid_rows_normalises_names_and_drops_padding_rows(self) -> None:
        raw = [
            {"rowIndex": 3, "label": "L", "fieldName": "tcode", "fillable": True, "elementId": "i", "selector": "#i"},
            {"rowIndex": 4, "label": "", "fieldName": None, "fillable": False, "elementId": None, "selector": None},
        ]
        assert _parse_grid_rows(raw) == [
            _GridRow(row_index=3, label="L", field_name="TCODE", fillable=True, element_id="i", selector="#i")
        ]


class TestQueryStopsBeforeF8:
    """A filter that cannot be placed fails the query; nothing is run with a different filter (#924)."""

    async def test_unavailable_filter_returns_a_failure_and_never_presses_f8(self) -> None:
        backend = MagicMock(spec=WebGuiBackend)
        backend.backend_type = "webgui"
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True))
        backend.wait = AsyncMock()
        backend.press_key = AsyncMock()
        fill = _FilterFillResult(unapplied_fields=["B"], offered_fields=["A", "C"])
        with (
            patch.object(se16_tools, "_get_field_order_from_se11", AsyncMock(return_value={"A": 0, "B": 1, "C": 2})),
            patch.object(se16_tools, "_type_table_name_with_validation", AsyncMock(return_value=None)),
            patch.object(se16_tools, "_wait_for_grid_rows", AsyncMock(return_value=True)),
            patch.object(se16_tools, "_fill_se16n_filters_webgui", AsyncMock(return_value=fill)),
        ):
            result = await se16_tools._execute_se16_query(backend, "T", {"B": "x"}, 10)
        assert result.success is False
        assert "'B' not available as SE16N selection criteria" in (result.error or "")
        assert "Offered fields: A, C." in (result.error or "")
        backend.press_key.assert_not_awaited()

    def test_failure_text_matches_the_desktop_backend(self) -> None:
        fill = _FilterFillResult(unapplied_fields=["B"], offered_fields=["A", "C"])
        result = _filter_fill_failure(fill, "T", datetime.now(UTC))
        assert result.filter_warnings == ["Field 'B' not found in SE16N selection criteria"]


# ---------------------------------------------------------------------------
# read_se16n_selection_rows.js on a synthetic grid with the structure seen on a live system
# ---------------------------------------------------------------------------

_SID = "wnd[0]/usr/subTAB_SUB:SAPLSE16N:0121/tblSAPLSE16NSELFIELDS_TC"


def _lsdata(prefix: str, column: str, col: int, row: int) -> str:
    return '{"x":0,"7":{"SID":"' + f"{_SID}/{prefix}GS_SELFIELDS-{column}[{col},{row}]" + '","Type":"SAPTABLECSCELL"}}'


def _cell(prefix: str, column: str, col: int, row: int, *, text: str = "", control: str | None = None) -> str:
    """A table cell as the Web GUI renders it: a gridcell <td> wrapping a control <span>."""
    ls = _lsdata(prefix, column, col, row)
    inner = control if control is not None else f"<span lsdata='{ls}'>{text}</span>"
    return f"<td role=\"gridcell\" lsdata='{ls}'>{inner}</td>"


def _grid_html(
    rows: list[tuple[str, str | None, bool]],
    *,
    padding: int = 0,
    textbox_with_input: bool = False,
    with_ids: bool = True,
) -> str:
    """Rows are (label, technical name or None if not in the DOM, has an input); left and right are separate <tr>."""
    left = ""
    right = ""
    for row in range(len(rows) + padding):
        label, technical, has_input = rows[row] if row < len(rows) else ("", None, False)
        left += f'<tr role="row">{_cell("txt", "SCRTEXT_M", 0, row, text=label)}</tr>'
        low_ls = _lsdata("ctxt", "LOW", 2, row)
        if has_input:
            input_id = f' id="in{row}"' if with_ids else ""
            inner_input = f"<input{input_id}>" if textbox_with_input else ""
            textbox_id = f' id="low{row}"' if with_ids else ""
            control = f"<span role=\"textbox\"{textbox_id} lsdata='{low_ls}'>{inner_input}</span>"
            low = _cell("ctxt", "LOW", 2, row, control=control)
        else:
            low = _cell("ctxt", "LOW", 2, row, control="")
        name = _cell("txt", "FIELDNAME", 6, row, text=technical) if technical is not None else ""
        right += f"<tr>{low}{name}</tr>"
    header = "".join(
        f'<th role="columnheader">{name}</th>'
        for name in ["Feldname", "Option", "Von-Wert", "Bis-Wert", "Mehr", "Ausgabe", "Technischer Name"]
    )
    return f'<div role="grid"><table><tbody><tr role="row">{header}</tr>{left}{right}</tbody></table></div>'


async def _run_read_rows(html: str) -> dict[str, Any]:
    async with async_playwright() as playwright:
        try:
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
            browser = await playwright.chromium.launch(executable_path=executable)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            pytest.skip(f"Chromium cannot be launched here: {str(exc).splitlines()[0]}")
        try:
            page = await browser.new_page()
            await page.set_content(html)
            result: dict[str, Any] = await page.evaluate(READ_ROWS_JS.read_text(encoding="utf-8"), {})
            # How many elements each returned selector addresses (must be exactly one to be fillable).
            result["selectorMatches"] = {
                row["rowIndex"]: await page.locator(row["selector"]).count()
                for row in result.get("rows", [])
                if row["selector"]
            }
            return result
        finally:
            await browser.close()


def _summary(result: dict[str, Any]) -> list[tuple[int, str, str | None, bool, str | None]]:
    return [(r["rowIndex"], r["label"], r["fieldName"], r["fillable"], r["elementId"]) for r in result["rows"]]


class TestReadSelectionRowsJs:
    async def test_pairs_label_name_and_input_by_the_row_number_in_their_sid(self) -> None:
        result = await _run_read_rows(_grid_html([("Transaktionscode", "TCODE", True), ("Programm", "PGMNA", True)]))
        assert result["success"] is True
        assert _summary(result) == [
            (0, "Transaktionscode", "TCODE", True, "low0"),
            (1, "Programm", "PGMNA", True, "low1"),
        ]

    async def test_a_field_se16n_leaves_out_does_not_shift_the_names(self) -> None:
        # Only A and C are offered: C is row 1 and is reported as such.
        result = await _run_read_rows(_grid_html([("Field A", "A", True), ("Field C", "C", True)]))
        assert [(r["rowIndex"], r["fieldName"]) for r in result["rows"]] == [(0, "A"), (1, "C")]

    async def test_a_shown_row_without_an_input_is_not_fillable(self) -> None:
        result = await _run_read_rows(_grid_html([("Mandant", "MANDT", False), ("Material", "MATNR", True)]))
        assert _summary(result) == [
            (0, "Mandant", "MANDT", False, None),
            (1, "Material", "MATNR", True, "low1"),
        ]

    async def test_padding_rows_are_reported_empty(self) -> None:
        result = await _run_read_rows(_grid_html([("Tcode", "TCODE", True)], padding=2))
        assert result["renderedRows"] == 3
        assert result["hasPaddingRows"] is True
        assert _summary(result)[1:] == [(1, "", None, False, None), (2, "", None, False, None)]

    async def test_a_grid_filled_with_fields_has_no_padding_rows(self) -> None:
        result = await _run_read_rows(_grid_html([("Tcode", "TCODE", True), ("Prog", "PGMNA", True)]))
        assert result["hasPaddingRows"] is False

    async def test_name_is_null_when_the_technical_cell_is_not_rendered(self) -> None:
        result = await _run_read_rows(_grid_html([("Tcode", "TCODE", True), ("Prog", None, True)]))
        assert [r["fieldName"] for r in result["rows"]] == ["TCODE", None]

    async def test_the_input_inside_the_textbox_is_preferred(self) -> None:
        result = await _run_read_rows(_grid_html([("Tcode", "TCODE", True)], textbox_with_input=True))
        row = result["rows"][0]
        assert (row["elementId"], row["elementType"], row["selector"]) == ("in0", "input", '[id="in0"]')

    @pytest.mark.parametrize("textbox_with_input", [False, True])
    async def test_selectors_address_exactly_one_element_with_and_without_ids(self, textbox_with_input: bool) -> None:
        rows = [("Tcode", "TCODE", True), ("Prog", "PGMNA", True)]
        for with_ids in (True, False):
            result = await _run_read_rows(_grid_html(rows, textbox_with_input=textbox_with_input, with_ids=with_ids))
            assert result["selectorMatches"] == {0: 1, 1: 1}, (with_ids, result["rows"])

    async def test_namespaced_and_lowercase_names_are_normalised(self) -> None:
        result = await _run_read_rows(_grid_html([("Ns", "/abc/field", True)]))
        assert result["rows"][0]["fieldName"] == "/ABC/FIELD"

    async def test_grid_is_found_by_its_cells_when_no_header_text_matches(self) -> None:
        html = _grid_html([("x", "TCODE", True)])
        for known in ("Feldname", "Von-Wert", "Technischer Name"):
            html = html.replace(known, "col")
        result = await _run_read_rows(html)
        assert result["success"] is True
        assert [(r["rowIndex"], r["fieldName"]) for r in result["rows"]] == [(0, "TCODE")]

    async def test_no_selection_grid_is_reported(self) -> None:
        result = await _run_read_rows("<div>nothing here</div>")
        assert result["success"] is False
        assert "not found" in result["error"]

    async def test_result_is_json_serialisable(self) -> None:
        result = await _run_read_rows(_grid_html([("Tcode", "TCODE", True)]))
        json.dumps(result)


class TestFillElementByLocator:
    """SE16N grid cells are custom role=textbox controls: Playwright's fill() rejects them."""

    @staticmethod
    def _backend(fill_error: Exception | None, role: str | None = "textbox") -> tuple[WebGuiBackend, MagicMock]:
        element = MagicMock()
        element.count = AsyncMock(return_value=1)
        element.get_attribute = AsyncMock(return_value=role)
        element.click = AsyncMock()
        element.fill = AsyncMock(side_effect=fill_error)
        element.press_sequentially = AsyncMock()
        page = MagicMock()
        page.locator.return_value = element
        page.wait_for_timeout = AsyncMock()
        page.keyboard.press = AsyncMock()
        backend = object.__new__(WebGuiBackend)
        backend._page = page  # pylint: disable=protected-access
        return backend, page

    async def test_a_control_that_cannot_be_filled_is_cleared_with_the_keyboard(self) -> None:
        backend, page = self._backend(RuntimeError("Element is not an <input>"))
        assert await backend.fill_element_by_locator("#x", "SE16") is True
        assert [call.args[0] for call in page.keyboard.press.await_args_list] == ["Control+A", "Backspace", "Tab"]
        page.locator.return_value.press_sequentially.assert_awaited_once_with("SE16", delay=30)

    async def test_a_failing_fill_on_anything_but_a_custom_textbox_sends_no_keys(self) -> None:
        # e.g. a detached or broken <input>: Ctrl+A/Backspace would hit whatever else has focus.
        backend, page = self._backend(RuntimeError("Timeout"), role=None)
        assert await backend.fill_element_by_locator("#x", "SE16") is False
        page.keyboard.press.assert_not_awaited()
        page.locator.return_value.press_sequentially.assert_not_awaited()

    async def test_an_input_is_still_cleared_with_fill(self) -> None:
        backend, page = self._backend(None)
        assert await backend.fill_element_by_locator("#x", "SE16") is True
        assert [call.args[0] for call in page.keyboard.press.await_args_list] == ["Tab"]
        page.locator.return_value.fill.assert_awaited_once_with("")
