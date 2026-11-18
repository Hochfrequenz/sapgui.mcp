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
from sapguimcp.lang import _register_for_tests
from sapguimcp.lang.schema import JobStatus
from sapguimcp.models import TableData, TableRow
from sapguimcp.models.slg1_models import SLG1LogEntry
from sapguimcp.tools.slg1_tools import _slg1_lookup_desktop
from sapguimcp.tools.sm37_tools import (
    _execute_sm37_lookup_desktop,
    normalize_job_status,
)
from sapguimcp.tools.st22_tools import (
    _st22_lookup_desktop,
)
from unittests.lang.synthetic_pack import CODE, MARK, synthetic_pack


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


@pytest.mark.anyio
async def test_slg1_fills_the_labels_of_the_synthetic_language_first() -> None:
    backend = MagicMock()
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    backend.fill_form = AsyncMock(
        side_effect=lambda fields: SimpleNamespace(
            not_found=[label for label in fields if not label.startswith(MARK)], errors=[]
        )
    )
    for name in ("wait_for_ready", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
    backend.read_table = AsyncMock(return_value=TableData(success=True, headers=[], rows=[]))
    backend.require_session = MagicMock()
    backend.com = MagicMock()
    entry = SLG1LogEntry(log_number="1", object="OBJ", date="07.10.2026", time="10:00:00")
    backend.com.run = AsyncMock(return_value=([entry], False))  # a log tree: the lookup ends there
    with _register_for_tests(synthetic_pack()), lang.use(CODE):
        t = lang.current("test")
        await _slg1_lookup_desktop(backend, t, "OBJ", "SUB", "EXT")
    labels = [next(iter(call.args[0])) for call in backend.fill_form.await_args_list]
    assert labels == [
        t.slg1.log_object.variants[0],
        t.slg1.log_subobject.variants[0],
        t.slg1.external_id.variants[0],
    ]
    assert all(label.startswith(MARK) for label in labels)  # not one German or English label was tried


@pytest.mark.anyio
async def test_the_status_column_title_comes_from_the_pack() -> None:
    t = lang.view_for("DE")
    assert t.sm37.col_status.first_key({"Status": "x"}) == "x"
    with _register_for_tests(synthetic_pack()), lang.use(CODE):
        tx = lang.current("test")
        assert tx.sm37.col_status.variants[0].startswith(MARK)
        backend = MagicMock()
        backend.backend_type = "desktop"
        backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
        for name in ("wait_for_ready", "press_key"):
            setattr(backend, name, AsyncMock())
        backend.focus_and_type = AsyncMock(return_value=True)
        backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
        title = tx.sm37.col_status.variants[0]
        row = TableRow(
            row=1, data={tx.sm37.job_name.variants[0]: "J", title: tx.sm37.status[JobStatus.FINISHED].variants[0]}
        )
        backend.read_table = AsyncMock(return_value=TableData(success=True, headers=[title], rows=[row]))
        result = await _execute_sm37_lookup_desktop(backend, tx, "*", None, None, None, None)
    assert [job.status for job in result.jobs] == ["Finished"]


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("DE", "Fertig", "Finished"),
        ("DE", "fertig", "Finished"),
        ("DE", "Abgebrochen", "Canceled"),
        ("EN", "Finished", "Finished"),
        ("EN", "Sched.", "Scheduled"),  # the checkbox text of the EN screen
        ("EN", "Scheduled", "Scheduled"),
        ("DE", "Finished", "Finished"),  # a German session also reads English texts
        ("EN", "unbekannt", "unbekannt"),
    ],
)
def test_the_job_status_is_the_canonical_one(language: str, text: str, expected: str) -> None:
    assert normalize_job_status(f" {text} ", lang.view_for(language)) == expected
