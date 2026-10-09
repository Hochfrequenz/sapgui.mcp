"""ST22 dump detail on the desktop: the detail screen is a classic list, parsed by its section headings."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.models.st22_models import ST22Dump
from sapguimcp.tools.st22_tools import (
    _ST22_DETAIL_MAX_LINES,
    _capture_desktop_detail,
    _parse_desktop_detail_lines,
)

_DUMP = ST22Dump(
    index=0,
    date="2026-10-08",
    time="10:00:00",
    program="ZPROG",
    error_type="SOME_ERROR",
    short_text="short text of the list entry",
    user="USER1",
)

_GERMAN = [
    "Kategorie ABAP Programmierfehler",
    "Laufzeitfehler SOME_ERROR",
    "Was ist passiert?",
    "Fehler im ABAP-Anwendungsprogramm.",
    "Das laufende Programm musste abgebrochen werden.",
    "Was können Sie tun?",
    "Notieren Sie bitte die Aktionen.",
    "Wenden Sie sich an den Administrator.",
    "Fehleranalyse",
    "Ein Wert konnte nicht kopiert werden.",
    "Systemumgebung",
    "SY-SUBRC 0",
    "Aktive Aufrufe/Ereignisse",
    "Nr. Art Programm Include Ze",
    "Name",
    "3 METHOD ZCL_TOP=============CP ZCL_TOP=============CM001 42",
    "ZCL_TOP=>RUN",
    "2 FUNCTION SAPLZFG LZFGU01",
    "Z_FUNCTION",
    "1 EVENT ZPROG ZPROG",
    "START-OF-SELECTION",
    "Inhalte der Systemfelder",
    "SY-DATUM 20261008",
]


def test_the_sections_are_taken_from_the_lines_under_their_headings() -> None:
    detail = _parse_desktop_detail_lines(_GERMAN, _DUMP)
    assert (
        detail.what_happened == "Fehler im ABAP-Anwendungsprogramm.\nDas laufende Programm musste abgebrochen werden."
    )
    assert detail.how_to_correct == "Notieren Sie bitte die Aktionen.\nWenden Sie sich an den Administrator."
    assert detail.error_type == "SOME_ERROR"
    assert detail.short_text == "short text of the list entry"
    assert "Fehleranalyse" in detail.raw_text


def test_the_call_stack_is_listed_topmost_first_with_the_name_of_the_next_line() -> None:
    detail = _parse_desktop_detail_lines(_GERMAN, _DUMP)
    assert detail.call_stack == [
        "3 METHOD ZCL_TOP=============CP ZCL_TOP=============CM001 42 ZCL_TOP=>RUN",
        "2 FUNCTION SAPLZFG LZFGU01 Z_FUNCTION",
        "1 EVENT ZPROG ZPROG START-OF-SELECTION",
    ]


def test_the_program_include_and_line_come_from_the_topmost_call_when_the_list_entry_has_none() -> None:
    detail = _parse_desktop_detail_lines(_GERMAN, _DUMP.model_copy(update={"program": "", "include": None}))
    assert (detail.program, detail.include, detail.line) == ("ZCL_TOP=============CP", "ZCL_TOP=============CM001", 42)
    # with a program in the list entry, that one is kept; the line still comes from the call stack
    detail = _parse_desktop_detail_lines(_GERMAN, _DUMP)
    assert (detail.program, detail.line) == ("ZPROG", 42)


def test_english_headings_and_a_screen_without_a_call_stack() -> None:
    lines = [
        "What happened?",
        "Error in the ABAP application program.",
        "What can you do?",
        "Note down which actions led to the error.",
        "Error analysis",
        "details",
    ]
    detail = _parse_desktop_detail_lines(lines, _DUMP)
    assert detail.what_happened == "Error in the ABAP application program."
    assert detail.how_to_correct == "Note down which actions led to the error."
    assert detail.call_stack == []
    assert (detail.program, detail.include, detail.line) == ("ZPROG", None, None)


def test_no_headings_and_no_lines_leave_the_sections_empty() -> None:
    detail = _parse_desktop_detail_lines(["just", "some text"], _DUMP)
    assert (detail.what_happened, detail.how_to_correct, detail.call_stack) == ("", "", [])
    assert _parse_desktop_detail_lines([], _DUMP).raw_text == ""


def test_the_call_stack_is_limited_to_twenty_entries() -> None:
    lines = ["Aktive Aufrufe/Ereignisse", *(f"{n} METHOD PROG INCL" for n in range(30, 0, -1))]
    assert len(_parse_desktop_detail_lines(lines, _DUMP).call_stack) == 20


def test_the_raw_text_is_cut_at_ten_kilobytes() -> None:
    assert len(_parse_desktop_detail_lines(["x" * 100] * 200, _DUMP).raw_text) == 10240


# --- capturing -----------------------------------------------------------------------------------------------------


def _backend() -> Any:
    backend = MagicMock(spec=DesktopBackend)
    backend.require_session = MagicMock(return_value=MagicMock())
    backend.com = MagicMock()
    backend.com.run = AsyncMock(side_effect=lambda job: job())
    return backend


@pytest.mark.anyio
async def test_the_detail_is_read_as_a_classic_list() -> None:
    backend = _backend()
    with patch("sapguimcp.tools.st22_tools.read_classic_list_lines", return_value=["line 1", "line 2"]) as reader:
        assert await _capture_desktop_detail(backend) == ["line 1", "line 2"]
    assert reader.call_args.args[1] == _ST22_DETAIL_MAX_LINES


@pytest.mark.anyio
async def test_without_a_list_the_labels_of_the_screen_are_the_detail() -> None:
    backend = _backend()
    backend.get_screen_text = AsyncMock(return_value=SimpleNamespace(labels=["label 1", "label 1", "label 2"]))
    with patch("sapguimcp.tools.st22_tools.read_classic_list_lines", return_value=[]):
        assert await _capture_desktop_detail(backend) == ["label 1", "label 1", "label 2"]
    backend.get_screen_text.assert_awaited_once_with(keep_duplicate_labels=True)


def test_the_call_stack_ends_at_the_next_section_and_variable_lines_are_no_entries() -> None:
    lines = [
        "Aktive Aufrufe/Ereignisse",
        "2 METHOD ZCL_A=CP ZCL_A=CM001",
        "ZCL_A=>RUN",
        "1 EVENT ZPROG ZPROG",
        "START-OF-SELECTION",
        "Ausgewählte Variablen",
        "5 lowercase kind here",  # a variable line shaped like an entry
        "7 TOKEN TOKEN TOKEN",
    ]
    assert _parse_desktop_detail_lines(lines, _DUMP).call_stack == [
        "2 METHOD ZCL_A=CP ZCL_A=CM001 ZCL_A=>RUN",
        "1 EVENT ZPROG ZPROG START-OF-SELECTION",
    ]


def test_the_line_is_only_used_when_the_include_is_the_one_of_the_topmost_call() -> None:
    other_include = _DUMP.model_copy(update={"include": "ZSOME_OTHER_INCLUDE"})
    assert _parse_desktop_detail_lines(_GERMAN, other_include).line is None
    same_include = _DUMP.model_copy(update={"include": "ZCL_TOP=============CM001"})
    assert _parse_desktop_detail_lines(_GERMAN, same_include).line == 42


@pytest.mark.anyio
async def test_a_warning_says_when_the_limit_was_hit_without_reaching_the_call_stack(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backend = _backend()
    lines = [f"line {n}" for n in range(_ST22_DETAIL_MAX_LINES)]
    with patch("sapguimcp.tools.st22_tools.read_classic_list_lines", return_value=lines):
        assert await _capture_desktop_detail(backend) == lines
    assert "without reaching the call stack" in caplog.text
