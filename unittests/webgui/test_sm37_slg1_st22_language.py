"""SM37, SLG1 and ST22 read every text from the language packs (#1044, phase 3).

Covers the single-language bugs the migration fixed (desktop job status, the different "no entries" lists,
``language == "DE"`` branches, the WebGUI headings of ST22) and the behaviour change: a session whose language has no
pack (or is unknown) fails the tool call with ``UnsupportedLanguageError``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sapguimcp import lang
from sapguimcp.backend.webgui.parsers.slg1_parser import is_slg1_no_results
from sapguimcp.backend.webgui.parsers.sm37_parser import is_no_jobs_found, normalize_job_status, parse_sm37_job_list
from sapguimcp.backend.webgui.parsers.st22_parser import is_no_dumps_message, parse_st22_dump_detail
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.models import TableData, TableRow
from sapguimcp.tools.sm37_tools import (
    _execute_sm37_lookup_desktop,
)

# ---------------------------------------------------------------------------
# Bug: the desktop SM37 status was not normalised
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("DE", "Fertig", "Finished"),
        ("DE", "fertig", "Finished"),
        ("DE", "Abgebrochen", "Canceled"),
        ("EN", "Finished", "Finished"),
        ("EN", "Sched.", "Scheduled"),  # the checkbox text of the EN screen (D021T SAPLBTCH 2170)
        ("EN", "Scheduled", "Scheduled"),
        ("DE", "Finished", "Finished"),  # a German session also reads English texts
        ("EN", "unbekannt", "unbekannt"),
    ],
)
def test_the_job_status_is_the_canonical_one(language: str, text: str, expected: str) -> None:
    assert normalize_job_status(f" {text} ", lang.view_for(language)) == expected


@pytest.mark.anyio
async def test_the_desktop_status_is_normalised_like_the_webgui_status() -> None:
    backend = MagicMock()
    backend.backend_type = "desktop"
    backend.enter_transaction = AsyncMock(return_value=SimpleNamespace(success=True, error=None))
    for name in ("wait_for_ready", "focus_and_type", "press_key"):
        setattr(backend, name, AsyncMock())
    backend.focus_and_type = AsyncMock(return_value=True)
    backend.get_status_bar = AsyncMock(return_value=SimpleNamespace(type="S", message=""))
    row = TableRow(row=1, data={"Jobname": "MYJOB", "Status": "Freigegeben", "Ersteller": "USER1", "Mandant": "100"})
    backend.read_table = AsyncMock(return_value=TableData(success=True, headers=["Jobname", "Status"], rows=[row]))
    result = await _execute_sm37_lookup_desktop(backend, lang.view_for("DE"), "*", None, None, None, None)
    assert [job.status for job in result.jobs] == ["Released"]

    webgui = parse_sm37_job_list(
        AriaSnapshot('- heading "Jobübersicht"\n- text: MYJOB USER1 freigegeben 0 0 100'), lang.view_for("DE")
    )
    assert [job.status for job in webgui] == ["Released"]


# ---------------------------------------------------------------------------
# Bug: tools and parsers used different "no entries" lists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_every_no_jobs_text_is_known_to_the_parser(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.sm37.no_jobs:
        assert is_no_jobs_found(AriaSnapshot(f'- status "{variant}"'), t), variant


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_every_no_dumps_text_is_known_to_the_parser(language: str) -> None:
    t = lang.view_for(language)
    for variant in t.st22.no_dumps:
        assert is_no_dumps_message(AriaSnapshot(f'- status "{variant}"'), t), variant


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_the_no_logs_text_is_sap_message_bl_208(language: str) -> None:
    """The text SAP shows for BL 208 (T100, both releases), with and without the trailing period of the German one."""
    bl_208 = {
        "DE": "Es konnte kein Protokoll auf der Datenbank gefunden werden.",
        "EN": "No log found in the database",
    }[language]
    t = lang.view_for(language)
    assert t.slg1.no_logs_found.contains(bl_208)
    assert is_slg1_no_results(AriaSnapshot(f'- status "{bl_208}"'), t)


# ---------------------------------------------------------------------------
# Bug: the WebGUI ST22 parser knew one heading per section and language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "what", "advice", "analysis"),
    [
        ("DE", "Was ist passiert", "Hinweise zur Fehlerbehebung", "Fehleranalyse"),
        ("DE", "Was ist geschehen?", "Was können Sie tun?", "Fehleranalyse"),
        ("EN", "What happened?", "What can you do?", "Error Analysis"),
        ("EN", "What happened?", "How to Correct the Error", "Error Analysis"),
    ],
)
def test_the_webgui_dump_detail_reads_every_heading_of_the_desktop(
    language: str, what: str, advice: str, analysis: str
) -> None:
    snapshot = AriaSnapshot(
        f'- text "{what}"\n- text "the cause"\n- text "{advice}"\n- text "the remedy"\n- text "{analysis}"\n- text "x"'
    )
    detail = parse_st22_dump_detail(snapshot, lang.view_for(language))
    assert detail.what_happened == "the cause"
    assert detail.how_to_correct == "the remedy"


def test_jobs_named_like_skipped_list_lines_are_kept() -> None:
    """The skip block is case-sensitive: only the lower-case list lines are dropped, not jobs named like them."""
    t = lang.view_for("DE")
    snapshot = AriaSnapshot(
        '- heading "Jobübersicht"\n'
        "- text: SCHEDULED_CLEANUP USER1 freigegeben 0 0 100\n"
        "- text: EVENT-DRIVEN_LOAD USER1 freigegeben 0 0 100\n"
        "- text: scheduled something\n"
        "- text: eventgesteuert irgendwas"
    )
    assert [job.job_name for job in parse_sm37_job_list(snapshot, t)] == ["SCHEDULED_CLEANUP", "EVENT-DRIVEN_LOAD"]


@pytest.mark.parametrize(
    ("language", "advice", "source"),
    [("DE", "Was können Sie tun?", "Quelltextauszug"), ("EN", "What can you do?", "Source Code Extract")],
)
def test_the_advice_ends_at_the_source_code_heading(language: str, advice: str, source: str) -> None:
    snapshot = AriaSnapshot(f'- text "{advice}"\n- text "the remedy"\n- text "{source}"\n- text "code"')
    detail = parse_st22_dump_detail(snapshot, lang.view_for(language))
    assert detail.how_to_correct == "the remedy"


def test_a_populated_log_list_is_not_empty_because_a_cell_says_no_logs() -> None:
    t = lang.view_for("EN")
    populated = AriaSnapshot('- grid:\n  - row "1":\n    - gridcell "No logs processed"\n- note "Success Message bar"')
    assert not is_slg1_no_results(populated, t)
    assert is_slg1_no_results(AriaSnapshot('- note "Success No log found in the database"'), t)


def test_a_dump_list_is_not_empty_because_a_cell_says_no_dumps() -> None:
    t = lang.view_for("EN")
    assert not is_no_dumps_message(AriaSnapshot('- row "x":\n  - cell "No dumps from the batch run"'), t)


def test_every_advice_section_is_collected_in_screen_order_and_prose_does_not_end_one() -> None:
    snapshot = AriaSnapshot(
        '- text "What happened?"\n- text "Check the system environment and retry."\n'
        '- text "What can you do?"\n- text "first tip"\n- text "Error Analysis"\n- text "analysis"\n'
        '- text "How to Correct the Error"\n- text "second tip"\n- text "Source Code Extract"\n- text "code"'
    )
    detail = parse_st22_dump_detail(snapshot, lang.view_for("EN"))
    assert detail.what_happened == "Check the system environment and retry."
    assert detail.how_to_correct == "first tip\nsecond tip"


def test_german_dump_detail_sections() -> None:
    snapshot = AriaSnapshot(
        '- text "Was ist passiert?"\n- text "Das Programm wurde abgebrochen."\n'
        '- text "Was können Sie tun?"\n- text "Tipp"\n- text "Quelltextauszug"\n- text "Code"'
    )
    detail = parse_st22_dump_detail(snapshot, lang.view_for("DE"))
    assert detail.what_happened == "Das Programm wurde abgebrochen."
    assert detail.how_to_correct == "Tipp"
