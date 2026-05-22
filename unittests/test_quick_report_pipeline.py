"""Unit tests for sap_quick_report pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from pydantic import Field

from sapguimcp.models import (
    KeyboardResult,
    ScreenText,
    StatusBarInfo,
    TableData,
    TableRow,
    TransactionResult,
)
from sapguimcp.models.quick_report_models import (
    QuickReportResult,
    ScreenClassification,
)
from sapguimcp.models.screen_state import ScreenStateDiff
from sapguimcp.tools.quick_report_tools import _execute_quick_report


def _make_backend(
    *,
    tx_success: bool = True,
    tx_error: str | None = None,
    status_type: str = "S",
    status_message: str = "5 Einträge gelesen",
    snapshot: str = "- document 'SAP'\n  - grid 'ALV Grid'",
    screen_title: str = "Report Output",
    table_headers: list[str] | None = None,
    table_rows: list[dict[str, str]] | None = None,
) -> AsyncMock:
    """Create a mock backend with configurable responses."""
    backend = AsyncMock()

    # enter_transaction
    if tx_success:
        backend.enter_transaction = AsyncMock(return_value=TransactionResult(tcode="VA05"))
    else:
        backend.enter_transaction = AsyncMock(
            return_value=TransactionResult.failure(error=tx_error or "TX not found", tcode="ZZZZZ")
        )

    # click_button — simulate Ausführen button found and clicked
    backend.click_button = AsyncMock(return_value=None)

    # press_key — fallback if click_button fails
    backend.press_key = AsyncMock(return_value=KeyboardResult(key="F8", page_title=screen_title))

    # wait / wait_for_ready / wait_for_sap_ready
    backend.wait = AsyncMock()
    backend.wait_for_ready = AsyncMock()
    backend.wait_for_sap_ready = AsyncMock()

    # get_status_bar
    backend.get_status_bar = AsyncMock(return_value=StatusBarInfo(type=status_type, message=status_message))

    # get_snapshot
    backend.get_snapshot = AsyncMock(return_value=snapshot)

    # get_screen_text
    backend.get_screen_text = AsyncMock(return_value=ScreenText(title=screen_title))

    # get_page_title
    backend.get_page_title = AsyncMock(return_value=screen_title)

    # read_table
    headers = table_headers or ["Col1", "Col2"]
    rows = [TableRow(row=i + 1, data=row_data) for i, row_data in enumerate(table_rows or [{"Col1": "a", "Col2": "b"}])]
    backend.read_table = AsyncMock(
        return_value=TableData(
            headers=headers,
            rows=rows,
            total_rows=len(rows),
            start_row=1,
            end_row=len(rows),
        )
    )

    return backend


@pytest.mark.anyio
class TestQuickReportPipeline:
    """Tests for _execute_quick_report pipeline."""

    async def test_happy_path_table(self) -> None:
        """TX → fill → F8 → TABLE with rows."""
        backend = _make_backend()
        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(
                backend,
                tcode="VA05",
                fields={"Auftraggeber": "*"},
                max_rows=30,
            )
        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE
        assert result.table is not None
        assert len(result.table.rows) == 1

    async def test_desktop_backend_rejected(self) -> None:
        """Desktop backend → immediate failure."""
        backend = _make_backend()
        backend.backend_type = "desktop"
        result = await _execute_quick_report(backend, tcode="VA05")
        assert result.success is False
        assert "WebGUI" in result.error

    async def test_max_rows_zero_rejected(self) -> None:
        """max_rows=0 → immediate failure."""
        backend = _make_backend()
        result = await _execute_quick_report(backend, tcode="VA05", max_rows=0)
        assert result.success is False
        assert "max_rows" in result.error

    async def test_tx_not_found(self) -> None:
        """Transaction not found → failure."""
        backend = _make_backend(tx_success=False, tx_error="Transaction ZZZZZ does not exist")
        result = await _execute_quick_report(backend, tcode="ZZZZZ")
        assert result.success is False
        assert "ZZZZZ" in result.error or "does not exist" in result.error

    async def test_empty_result(self) -> None:
        """No data found → EMPTY."""
        backend = _make_backend(
            status_type="I",
            status_message="Keine Daten gefunden",
            snapshot="- document 'SAP'",
        )
        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(backend, tcode="ME2M")
        assert result.success is True
        assert result.screen_type == ScreenClassification.EMPTY
        assert result.table is None

    async def test_error_status_bar(self) -> None:
        """Status bar type E after F8 → ERROR with success=True."""
        backend = _make_backend(
            status_type="E",
            status_message="Werk XXXX existiert nicht",
            snapshot="- document 'SAP'",
        )
        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(backend, tcode="ME2M")
        assert result.success is True
        assert result.screen_type == ScreenClassification.ERROR
        assert result.status_bar_type == "E"

    async def test_unknown_screen(self) -> None:
        """No grid, no error → UNKNOWN with screen_text."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Variantenauswahl'",
            screen_title="Variantenauswahl",
        )
        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(backend, tcode="ZCUSTOM01")
        assert result.success is True
        assert result.screen_type == ScreenClassification.UNKNOWN
        assert result.screen_text is not None
        assert result.screen_text.title == "Variantenauswahl"

    async def test_field_not_found_continues(self) -> None:
        """Field not found → warning, but F8 still executed."""
        backend = _make_backend()
        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff(warnings=["Label 'FakeField' not found on screen"])
            result = await _execute_quick_report(
                backend,
                tcode="VA05",
                fields={"FakeField": "x"},
            )
        assert result.success is True
        assert "FakeField" in result.warnings[0]
        # F8 was executed (via click_button or press_key)
        assert backend.click_button.called or backend.press_key.called

    async def test_pipeline_call_order(self) -> None:
        """Verify pipeline calls in correct order."""
        backend = _make_backend()
        call_log: list[str] = []

        async def track_enter_tx(tcode: str) -> TransactionResult:
            call_log.append("enter_transaction")
            return TransactionResult(tcode=tcode)

        async def track_click_button(label: str) -> None:
            call_log.append(f"click_button({label})")

        async def track_press_key(key: str) -> KeyboardResult:
            call_log.append(f"press_key({key})")
            return KeyboardResult(key=key)

        async def track_wait() -> None:
            call_log.append("wait_for_ready")

        backend.enter_transaction = track_enter_tx
        backend.click_button = track_click_button
        backend.press_key = track_press_key
        backend.wait_for_ready = track_wait

        async def track_ensure_screen_state(backend, target):
            call_log.append("ensure_screen_state")
            return ScreenStateDiff()

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", side_effect=track_ensure_screen_state):
            await _execute_quick_report(backend, tcode="VA05", fields={"X": "Y"})

        assert call_log[0] == "enter_transaction"
        # F8 executed via click_button (primary) or press_key (fallback)
        assert any("click_button" in c for c in call_log) or any("press_key(F8)" in c for c in call_log)
        assert "wait_for_ready" in call_log

    async def test_wait_for_sap_ready_called_before_f8(self) -> None:
        """Pipeline must call wait_for_sap_ready between enter_transaction and F8 execution."""
        backend = _make_backend()
        call_log: list[str] = []

        async def track_enter_tx(tcode: str) -> TransactionResult:
            call_log.append("enter_transaction")
            return TransactionResult(tcode=tcode)

        async def track_wait_ready() -> None:
            call_log.append("wait_for_ready")

        async def track_wait_sap_ready(timeout_ms: int = 5000) -> None:
            call_log.append("wait_for_sap_ready")

        async def track_click_button(label: str) -> None:
            call_log.append("execute_f8")

        async def track_press_key(key: str) -> KeyboardResult:
            call_log.append("execute_f8")
            return KeyboardResult(key=key)

        backend.enter_transaction = track_enter_tx
        backend.wait_for_ready = track_wait_ready
        backend.wait_for_sap_ready = track_wait_sap_ready
        backend.click_button = track_click_button
        backend.press_key = track_press_key

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            await _execute_quick_report(backend, tcode="VA05", fields={"X": "Y"})

        # wait_for_sap_ready must appear AFTER enter_transaction and BEFORE F8 execution
        idx_sap_ready = call_log.index("wait_for_sap_ready")
        idx_enter = call_log.index("enter_transaction")
        idx_f8 = call_log.index("execute_f8")
        assert idx_enter < idx_sap_ready < idx_f8


@pytest.mark.anyio
class TestF8Retry:
    """Tests for the F8 retry loop (swallowed keystrokes)."""

    async def test_f8_retried_on_swallowed_keystroke(self) -> None:
        """F8 swallowed (ERROR, no status message) → retry → TABLE on 3rd attempt."""
        f8_count = {"n": 0}

        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- main 'SM37':\n  - textbox 'Jobname'",
        )

        async def counting_click_button(label: str) -> None:
            f8_count["n"] += 1

        async def evolving_snapshot() -> str:
            if f8_count["n"] < 3:
                # Still on selection screen (textbox → ERROR)
                return "- main 'SM37':\n  - textbox 'Jobname'"
            return "- document 'SAP'\n  - grid 'ALV Grid'"

        async def evolving_status_bar() -> StatusBarInfo:
            if f8_count["n"] < 3:
                return StatusBarInfo(type="none", message="")
            return StatusBarInfo(type="S", message="10 Einträge gelesen")

        backend.click_button = counting_click_button
        backend.get_snapshot = evolving_snapshot
        backend.get_status_bar = evolving_status_bar

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(backend, tcode="SM37")

        assert result.screen_type == ScreenClassification.TABLE
        assert f8_count["n"] == 3  # needed 3 attempts

    async def test_f8_retry_stops_on_real_error(self) -> None:
        """SAP error (status_bar type E) → no retry, return immediately."""
        f8_count = {"n": 0}

        backend = _make_backend(
            status_type="E",
            status_message="Werk XXXX existiert nicht",
        )

        async def counting_click_button(label: str) -> None:
            f8_count["n"] += 1

        backend.click_button = counting_click_button

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(backend, tcode="SM37")

        assert result.screen_type == ScreenClassification.ERROR
        assert f8_count["n"] == 1  # no retry on real error


@pytest.mark.anyio
class TestPostF8Keys:
    """Tests for post_f8_keys parameter."""

    async def test_post_f8_keys_dismisses_popup(self) -> None:
        """post_f8_keys=["Enter"] dismisses popup, then TABLE."""
        call_count = {"classify": 0}

        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Variantenauswahl'",
        )

        # After Enter, change snapshot to have a grid
        original_get_snapshot = backend.get_snapshot

        async def evolving_snapshot() -> str:
            call_count["classify"] += 1
            if call_count["classify"] <= 1:
                # First classify (after F8): popup screen
                return "- document 'SAP'\n  - dialog 'Popup'"
            # After Enter: grid appears
            return "- document 'SAP'\n  - grid 'ALV Grid'"

        backend.get_snapshot = evolving_snapshot

        # After Enter, status bar changes
        original_get_sb = backend.get_status_bar
        sb_count = {"n": 0}

        async def evolving_status_bar() -> StatusBarInfo:
            sb_count["n"] += 1
            if sb_count["n"] <= 1:
                return StatusBarInfo(type="none", message="")
            return StatusBarInfo(type="S", message="5 Einträge")

        backend.get_status_bar = evolving_status_bar

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(
                backend,
                tcode="FBL1N",
                post_f8_keys=["Enter"],
            )

        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE

    async def test_post_f8_keys_max_3(self) -> None:
        """Only first 3 keys are executed, 4th produces warning."""
        backend = _make_backend()

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(
                backend,
                tcode="VA05",
                post_f8_keys=["Enter", "Enter", "Enter", "Enter"],
            )

        assert any("max" in w.lower() or "3" in w for w in result.warnings)

    async def test_post_f8_keys_empty_list(self) -> None:
        """post_f8_keys=[] behaves like None."""
        backend = _make_backend()

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(
                backend,
                tcode="VA05",
                post_f8_keys=[],
            )

        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE

    async def test_post_f8_keys_early_exit(self) -> None:
        """After first key resolves to TABLE, skip remaining keys."""
        backend = _make_backend(
            status_type="none",
            status_message="",
            snapshot="- document 'SAP'\n  - dialog 'Popup'",
        )
        press_key_calls: list[str] = []
        click_button_called = False
        classify_count = {"n": 0}

        async def tracking_click_button(label: str) -> None:
            nonlocal click_button_called
            click_button_called = True

        async def tracking_press_key(key: str) -> KeyboardResult:
            press_key_calls.append(key)
            return KeyboardResult(key=key)

        async def evolving_snapshot() -> str:
            classify_count["n"] += 1
            if classify_count["n"] <= 2:
                # After F8 + UNKNOWN re-classify: still popup
                return "- document 'SAP'\n  - dialog 'Popup'"
            # After Enter (post_f8_key): grid appears
            return "- document 'SAP'\n  - grid 'ALV Grid'"

        async def evolving_status_bar() -> StatusBarInfo:
            if classify_count["n"] <= 2:
                return StatusBarInfo(type="none", message="")
            return StatusBarInfo(type="S", message="5 Einträge")

        backend.click_button = tracking_click_button
        backend.press_key = tracking_press_key
        backend.get_snapshot = evolving_snapshot
        backend.get_status_bar = evolving_status_bar

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(
                backend,
                tcode="VA05",
                post_f8_keys=["Enter", "F5"],
            )

        assert result.screen_type == ScreenClassification.TABLE
        # F8 was executed (via click_button or press_key)
        assert click_button_called or "F8" in press_key_calls
        # Enter should be called via press_key, but F5 should be skipped
        assert "Enter" in press_key_calls
        assert "F5" not in press_key_calls

    async def test_output_file(self) -> None:
        """output_file writes JSON to disk."""
        backend = _make_backend()
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            output_path = f.name

        try:
            with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
                mock_ess.return_value = ScreenStateDiff()
                result = await _execute_quick_report(
                    backend,
                    tcode="VA05",
                    output_file=output_path,
                )

            assert result.success is True
            content = Path(output_path).read_text(encoding="utf-8")
            data = json.loads(content)
            assert data["tcode"] == "VA05"
        finally:
            Path(output_path).unlink(missing_ok=True)

    async def test_pipeline_exception_returns_failure(self) -> None:
        """Unexpected exception during pipeline → failure result, not unhandled crash."""
        backend = _make_backend()
        backend.enter_transaction = AsyncMock(side_effect=RuntimeError("Browser disconnected"))

        result = await _execute_quick_report(backend, tcode="VA05")

        assert result.success is False
        assert "Pipeline error" in result.error
        assert "Browser disconnected" in result.error

    async def test_read_table_exception_produces_warning(self) -> None:
        """read_table raises → TABLE with empty rows and warning."""
        backend = _make_backend()
        backend.read_table = AsyncMock(side_effect=RuntimeError("Parse error"))

        with patch("sapguimcp.tools.quick_report_tools.ensure_screen_state", new_callable=AsyncMock) as mock_ess:
            mock_ess.return_value = ScreenStateDiff()
            result = await _execute_quick_report(backend, tcode="VA05", fields={"X": "Y"})

        assert result.success is True
        assert result.screen_type == ScreenClassification.TABLE
        assert result.table is not None
        assert len(result.table.rows) == 0
        assert any("read_table failed" in w for w in result.warnings)
