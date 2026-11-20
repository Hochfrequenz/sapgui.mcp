"""ST22 dump detail on the desktop: short text, termination point and call stack kinds as an S/4HANA dump shows them
(#1156). The lines follow a German dump detail screen, with neutral names."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sapguimcp import lang
from sapguimcp.models.st22_models import ST22Dump
from sapguimcp.tools.classic_list_helpers import read_classic_list_lines
from sapguimcp.tools.st22_tools import _parse_desktop_detail_lines

_T = lang.view_for("DE")

_DUMP = ST22Dump(
    index=0,
    date="2026-10-08",
    time="10:00:00",
    program="ZCL_DEMO======================CP",
    error_type="OBJECTS_OBJREF_NOT_ASSIGNED",
    short_text="",
    user="USER1",
)

_LINES = [
    "Kategorie ABAP Programmierfehler",
    "Laufzeitfehler OBJECTS_OBJREF_NOT_ASSIGNED",
    "Ausnahme CX_SY_REF_IS_INITIAL",
    "ABAP: Programm ZCL_DEMO======================CP",
    "Anwendungskomponente Nicht zugeordnet",
    "Datum und Zeit 08.10.2026 10:00:00 (CET)",
    "Kurztext",
    "Zugriff über 'NULL' Objektreferenz nicht möglich.",
    "Was ist passiert?",
    "Fehler im ABAP-Anwendungsprogramm.",
    'Das laufende ABAP-Programm "ZCL_DEMO======================CP" mußte',
    "abgebrochen werden.",
    "Was können Sie tun?",
    "Notieren Sie bitte, welche Aktionen und Eingaben zu dem Fehler geführt",
    "haben.",
    "Fehleranalyse",
    'Es ist eine Ausnahme der Klasse "CX_SY_REF_IS_INITIAL" aufgetreten.',
    "Hinweise zur Fehlerbehebung",
    '"ZCL_DEMO======================CP" bzw. ZCL_DEMO======================CM00C',
    "Systemumgebung",
    "SAP-Release..... 816",
    "Informationen zur Abbruchstelle",
    "Der Abbruch trat im ABAP-Programm bzw. Include",
    '"ZCL_DEMO======================CP"',
    'auf, und zwar in "ZIF_DEMO~DISPLAY". Das Hauptprogramm war "ZDEMO_MAIN1".',
    "Im Quelltext befindet sich die Abbruchstelle in Zeile 36",
    'des Includes "ZCL_DEMO======================CM00C".',
    'Die Prozedur befindet sich im Programm "ZCL_DEMO======================CP", ihr',
    "Quelltext",
    'beginnt in Zeile 1 des Includes "ZCL_DEMO======================CM00C".',
    "Aktive Aufrufe/Ereignisse",
    "Nr. Art Programm Include",
    "Name",
    "4 METHOD ZCL_DEMO======================CP ZCL_DEMO======================CM",
    "ZCL_DEMO=>ZIF_DEMO~DISPLAY",
    "3 FORM ZDEMO_MAIN1 ZDEMO_MAIN1",
    "FRM_PREPARE",
    "2 MODULE (PBO) ZDEMO_MAIN1 ZDEMO_MAIN1",
    "PBO_0100",
    "1 EVENT ZDEMO_MAIN1 ZDEMO_MAIN1",
    "START-OF-SELECTION",
]


def test_the_short_text_comes_from_its_section_of_the_detail() -> None:
    detail = _parse_desktop_detail_lines(_LINES, _DUMP, _T)
    assert detail.short_text == "Zugriff über 'NULL' Objektreferenz nicht möglich."


def test_the_short_text_of_the_list_is_kept_without_the_section() -> None:
    lines = [line for line in _LINES if line not in ("Kurztext", "Zugriff über 'NULL' Objektreferenz nicht möglich.")]
    dump = _DUMP.model_copy(update={"short_text": "from the list"})
    assert _parse_desktop_detail_lines(lines, dump, _T).short_text == "from the list"


def test_the_include_cut_off_in_the_call_stack_and_the_line_come_from_the_termination_text() -> None:
    detail = _parse_desktop_detail_lines(_LINES, _DUMP, _T)
    assert detail.include == "ZCL_DEMO======================CM00C"
    assert detail.line == 36
    assert detail.program == "ZCL_DEMO======================CP"


def test_a_line_shown_in_the_call_stack_wins() -> None:
    lines = [
        "4 METHOD ZCL_DEMO======================CP ZCL_DEMO======================CM00C 40"
        if line.startswith("4 METHOD")
        else line
        for line in _LINES
    ]
    detail = _parse_desktop_detail_lines(lines, _DUMP, _T)
    assert (detail.include, detail.line) == ("ZCL_DEMO======================CM00C", 40)


def test_without_a_matching_termination_text_the_call_stack_values_are_kept() -> None:
    lines = [line for line in _LINES if "Zeile" not in line]
    detail = _parse_desktop_detail_lines(lines, _DUMP, _T)
    assert (detail.include, detail.line) == ("ZCL_DEMO======================CM", None)


def test_a_call_stack_kind_with_a_qualifier_is_an_entry() -> None:
    detail = _parse_desktop_detail_lines(_LINES, _DUMP, _T)
    assert detail.call_stack == [
        "4 METHOD ZCL_DEMO======================CP ZCL_DEMO======================CM ZCL_DEMO=>ZIF_DEMO~DISPLAY",
        "3 FORM ZDEMO_MAIN1 ZDEMO_MAIN1 FRM_PREPARE",
        "2 MODULE (PBO) ZDEMO_MAIN1 ZDEMO_MAIN1 PBO_0100",
        "1 EVENT ZDEMO_MAIN1 ZDEMO_MAIN1 START-OF-SELECTION",
    ]


def test_how_to_correct_holds_both_advice_sections() -> None:
    detail = _parse_desktop_detail_lines(_LINES, _DUMP, _T)
    assert detail.how_to_correct == (
        "Notieren Sie bitte, welche Aktionen und Eingaben zu dem Fehler geführt\nhaben.\n"
        '"ZCL_DEMO======================CP" bzw. ZCL_DEMO======================CM00C'
    )


def _report_dump_lines(stack_line: str) -> list[str]:
    """A report dump: the call stack names the include in full, the header and other sections carry numbers."""
    return [
        "Datum und Zeit 08.10.2026 10:00:00 (CET)",
        "Was ist passiert?",
        'Das laufende ABAP-Programm "ZDEMO_MAIN1" mußte abgebrochen werden.',
        "Systemumgebung",
        "SAP-Release..... 816",
        "Informationen zur Abbruchstelle",
        'Der Abbruch trat im ABAP-Programm bzw. Include "ZDEMO_MAIN1" auf.',
        "Im Quelltext befindet sich die Abbruchstelle in Zeile 12",
        'des Includes "ZDEMO_MAIN1".',
        "Aktive Aufrufe/Ereignisse",
        stack_line,
        "START-OF-SELECTION",
    ]


def test_numbers_outside_the_termination_section_are_not_taken_for_the_line() -> None:
    """The seconds of the header and the release of the system environment precede quoted program names (#1156)."""
    detail = _parse_desktop_detail_lines(_report_dump_lines("1 EVENT ZDEMO_MAIN1 ZDEMO_MAIN1"), _DUMP, _T)
    assert (detail.include, detail.line) == ("ZDEMO_MAIN1", 12)


def test_english_termination_text() -> None:
    lines = [
        "Information on Where Terminated",
        'The termination occurred in the ABAP program or include "ZCL_X=========CP", in "RUN".',
        'In the source code you have the termination point in line 36 of the (Include) program "ZCL_X=========CM00C".',
        "Active Calls/Events",
        "1 METHOD ZCL_X=========CP ZCL_X=========CM",
        "ZCL_X=>RUN",
    ]
    detail = _parse_desktop_detail_lines(lines, _DUMP, lang.view_for("EN"))
    assert (detail.include, detail.line) == ("ZCL_X=========CM00C", 36)


class _Scrollbar:
    def __init__(self, maximum: int, page_size: int) -> None:
        self.maximum = maximum
        self.page_size = page_size
        self.position = 0


class _Usr:
    """A dump detail window: the header box (rows 0-5) stays, the text scrolls in rows 7 to 7 + page size - 1."""

    _USR = "/app/con[0]/ses[0]/wnd[0]/usr"

    def __init__(self, header: list[str], text: list[str], page_size: int) -> None:
        self._header = header
        self._text = text
        self.vertical_scrollbar = _Scrollbar(max(len(text) - page_size, 0), page_size)

    def dump_tree(self) -> list[Any]:
        position = self.vertical_scrollbar.position
        elements = [SimpleNamespace(id=f"{self._USR}/lbl[0,{row}]", text=line) for row, line in enumerate(self._header)]
        for row in range(self.vertical_scrollbar.page_size):
            if position + row < len(self._text):
                text = self._text[position + row]
                elements.append(SimpleNamespace(id=f"{self._USR}/lbl[5,{7 + row}]", text=text))
        return elements


def test_the_header_box_does_not_end_up_in_the_sections_of_a_long_dump() -> None:
    """Read with the classic list reader as on screen, then parsed: the header box is read once (#1156)."""
    header, text = _LINES[:6], _LINES[6:]
    usr = _Usr(header, text, page_size=10)
    lines = read_classic_list_lines(SimpleNamespace(find_by_id=lambda _id, **_: usr), 1000)
    assert lines == _LINES
    detail = _parse_desktop_detail_lines(lines, _DUMP, _T)
    assert "Kategorie" not in detail.how_to_correct
    assert "Datum und Zeit" not in detail.what_happened
