"""SM37 on the desktop backend: a status bar saying that no job matches is an empty result, not a failure."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.models import TableData
from sapguimcp.models.sap_results import TableRow
from sapguimcp.tools.sm37_tools import _execute_sm37_lookup_desktop, _fetch_job_log_desktop, _is_job_log_screen


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


@pytest.mark.anyio
async def test_a_status_bar_that_merely_starts_like_the_empty_message_is_not_an_empty_result() -> None:
    config = MagicMock()
    config.get_default.return_value = SimpleNamespace(language="DE")
    # The status is no "empty" message, so the lookup goes on to read the list (which the fake backend refuses).
    with (
        patch("sapguimcp.tools.sm37_tools.get_sap_config", return_value=config),
        pytest.raises(AssertionError, match="no list to read"),
    ):
        await _execute_sm37_lookup_desktop(_backend("Kein Job ausgewählt"), "*", None, None, None, None)


def _filter_backend(*, fillable: set[str]) -> Any:
    """A backend whose selection screen has only the fields in ``fillable`` (by technical name)."""
    backend = _backend("")
    backend.focus_and_type = AsyncMock(side_effect=lambda name, _value, **_: name in fillable)
    backend.fill_field = AsyncMock()
    backend.read_table = AsyncMock(side_effect=AssertionError("must not be reached"))
    return backend


async def _lookup(backend: Any, *args: Any) -> Any:
    config = MagicMock()
    config.get_default.return_value = SimpleNamespace(language="DE")
    with patch("sapguimcp.tools.sm37_tools.get_sap_config", return_value=config):
        return await _execute_sm37_lookup_desktop(backend, *args)


@pytest.mark.anyio
async def test_the_filters_are_filled_by_the_technical_field_names() -> None:
    fields = {"BTCH2170-JOBNAME", "BTCH2170-USERNAME", "BTCH2170-FROM_DATE", "BTCH2170-TO_DATE"}
    backend = _filter_backend(fillable=fields)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message="Kein Job entspricht"))
    result = await _lookup(backend, "MYJOB*", "SOMEONE", None, "2026-10-01", "2026-10-08")
    assert result.success
    typed = {call.args[0]: call.args[1] for call in backend.focus_and_type.await_args_list}
    assert typed == {
        "BTCH2170-JOBNAME": "MYJOB*",
        "BTCH2170-USERNAME": "SOMEONE",
        "BTCH2170-FROM_DATE": "01.10.2026",
        "BTCH2170-TO_DATE": "08.10.2026",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("args", "missing"),
    [
        (("MYJOB*", None, None, None, None), "job_name"),
        (("*", "SOMEONE", None, None, None), "username"),
        (("*", None, None, "2026-10-01", None), "from_date"),
        (("*", None, None, None, "2026-10-08"), "to_date"),
    ],
)
async def test_a_filter_that_cannot_be_filled_fails_the_lookup(args: tuple[Any, ...], missing: str) -> None:
    backend = _filter_backend(fillable=set())
    result = await _lookup(backend, *args)
    assert not result.success
    assert missing in str(result.error)
    backend.press_key.assert_not_awaited()  # the query was not run with the default selection


def _listing_backend(table: Any, session: Any) -> Any:
    """A desktop backend that gets past the selection screen and then reads ``table`` (or falls back to ``session``)."""
    backend = _backend("")
    backend.backend_type = "desktop"
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.read_table = AsyncMock(return_value=table)
    backend.require_session = MagicMock(return_value=session)
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


@pytest.mark.anyio
async def test_a_classic_job_list_is_read_when_there_is_no_alv_grid() -> None:
    """SAP ERP 6.0 shows the job overview as labels: the German column titles map onto the job fields."""
    usr_prefix = "/app/con[0]/ses[0]/wnd[0]/usr"

    def _label(column: int, row: int, text: str) -> Any:
        return SimpleNamespace(id=f"{usr_prefix}/lbl[{column},{row}]", text=text)

    elements = [
        _label(4, 10, "Jobname"),
        _label(51, 10, "Job-Erstelle"),
        _label(64, 10, "Status"),
        _label(80, 10, "Startdatum"),
        _label(91, 10, "Startzeit"),
        _label(101, 10, "Dauer(sec.)"),
        SimpleNamespace(id=f"{usr_prefix}/chk[1,12]", text=""),
        _label(4, 12, "MYJOB"),
        _label(51, 12, "USER1"),
        _label(64, 12, "fertig"),
        _label(80, 12, "08.10.2026"),
        _label(91, 12, "00:49:27"),
        _label(101, 12, "         1"),
    ]
    usr = SimpleNamespace(dump_tree=lambda: elements, vertical_scrollbar=None)
    session = SimpleNamespace(find_by_id=lambda _element_id, **_: usr)
    backend = _listing_backend(TableData(success=True, headers=[], rows=[]), session)
    result = await _lookup(backend, "*", None, None, None, None)
    assert result.success
    job = result.jobs[0]
    assert (job.job_name, job.status, job.user, job.start_time, job.duration) == (
        "MYJOB",
        "fertig",
        "USER1",
        "08.10.2026 00:49:27",
        "1",
    )


@pytest.mark.anyio
async def test_the_classic_reader_does_not_run_when_the_alv_grid_has_headers() -> None:
    table = TableData(success=True, headers=["Jobname", "Status"], rows=[])
    session = MagicMock()
    session.find_by_id.side_effect = AssertionError("the classic reader must not run")
    backend = _listing_backend(table, session)
    result = await _lookup(backend, "*", None, None, None, None)
    assert result.success
    assert result.jobs == []


def test_the_job_log_screen_of_sap_erp_6_0_is_recognised_by_its_title() -> None:
    assert _is_job_log_screen("Job-Log zu Job MYJOB / 12345678")
    assert _is_job_log_screen("Job log for job MYJOB / 12345678")
    assert _is_job_log_screen("Job Log Einträge")
    assert not _is_job_log_screen("Job-Übersicht")


@pytest.mark.anyio
async def test_the_job_log_is_fetched_from_a_classic_list_when_there_is_no_grid() -> None:
    backend = _listing_backend(TableData(success=True, headers=[], rows=[]), MagicMock())
    backend.click_table_cell = AsyncMock(side_effect=ValueError("No ALV grid found on screen"))
    backend.click_button = AsyncMock()
    backend.press_key = AsyncMock()
    backend.get_screen_text = AsyncMock(
        return_value=SimpleNamespace(title="Job-Log zu Job MYJOB / 1", main_content=["Beenden", "Bearbeiten"])
    )
    with (
        patch("sapguimcp.tools.sm37_tools.select_first_classic_list_entry", return_value=True),
        patch("sapguimcp.tools.sm37_tools.read_classic_list_lines", return_value=["08.10.2026 00:49:27 Job gestartet"]),
    ):
        log = await _fetch_job_log_desktop(backend, "DE")
    assert log is not None
    assert log.log_lines == ["08.10.2026 00:49:27 Job gestartet"]  # not the menu entries of the screen text
    backend.click_button.assert_awaited_once_with("Job-Log")


@pytest.mark.anyio
async def test_no_job_log_is_fetched_when_no_job_could_be_selected() -> None:
    backend = _listing_backend(TableData(success=True, headers=[], rows=[]), MagicMock())
    backend.click_table_cell = AsyncMock(side_effect=ValueError("No ALV grid found on screen"))
    backend.click_button = AsyncMock()
    with patch("sapguimcp.tools.sm37_tools.select_first_classic_list_entry", return_value=False):
        assert await _fetch_job_log_desktop(backend, "DE") is None
    backend.click_button.assert_not_awaited()  # Job-Log must not run without a selected job


@pytest.mark.anyio
async def test_the_classic_list_reader_is_not_used_for_a_log_screen_without_the_ecc_title() -> None:
    backend = _listing_backend(TableData(success=True, headers=[], rows=[]), MagicMock())
    backend.click_table_cell = AsyncMock(return_value=SimpleNamespace(success=True))
    backend.click_button = AsyncMock()
    backend.press_key = AsyncMock()
    backend.get_screen_text = AsyncMock(
        return_value=SimpleNamespace(title="Job Log Entries", main_content=["08.10.2026 00:49:27 Job started"])
    )
    with patch("sapguimcp.tools.sm37_tools.read_classic_list_lines", side_effect=AssertionError("must not run")):
        log = await _fetch_job_log_desktop(backend, "EN")
    assert log is not None
    assert log.log_lines == ["08.10.2026 00:49:27 Job started"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("table", "expected"),
    [
        (TableData(success=True, headers=["Jobname"], rows=[], total_rows=0), False),
        (TableData(success=True, headers=["Jobname"], rows=[TableRow(row=1, data={})], total_rows=1), False),
        # an ALV grid that holds more rows than were read
        (TableData(success=True, headers=["Jobname"], rows=[TableRow(row=1, data={})], total_rows=500), True),
        # a classic list that stopped at the limit
        (TableData(success=True, headers=["Jobname"], rows=[TableRow(row=1, data={})], truncated=True), True),
    ],
)
async def test_the_job_list_says_when_more_jobs_match_than_were_returned(table: TableData, *, expected: bool) -> None:
    backend = _listing_backend(table, MagicMock())
    result = await _lookup(backend, "*", None, None, None, None)
    assert result.success
    assert result.jobs_truncated is expected
