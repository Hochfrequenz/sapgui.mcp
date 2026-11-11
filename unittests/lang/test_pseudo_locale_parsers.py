"""Pseudo-locale parser harness (#1044, spec section 10): no parser depends on a DE or EN spelling.

Every captured ARIA fixture is parsed twice: as captured, under the session view of its language,
and rewritten into the pseudo language (``pseudo_fixtures``), under the unmerged pseudo pack. The
two results must be the same once the pseudo letters in echoed UI text are transliterated back.
A parser that still holds a literal of its own instead of a pack field finds nothing in the
rewritten fixture, so its result differs.

Comparison, decided per parser and the same for all of them: the *whole* structured result is
compared (pydantic dump, dataclass dict or plain value). Results echo UI text (SE16/SM30/SPRO
column titles and cell values, descriptions, messages), which the rewritten fixture holds in
pseudo spelling; :func:`pseudo_fixtures.restore` maps it back exactly, so no field has to be left
out of the comparison - except ``retrieved_at``, the time of the call.

Fixtures and their language: the ``_de`` / ``_en`` suffix of the file name; the few captures
without a suffix are listed in ``_UNSUFFIXED``. Nothing is skipped silently - ``_SKIPPED`` lists
every fixture that is left out, with the reason.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel

from sapguimcp import lang
from sapguimcp.backend.webgui.backend import _parse_toolbar_note
from sapguimcp.backend.webgui.parsers import (
    se09_parser,
    se16_parser,
    se24_parser,
    se37_parser,
    se93_parser,
    slg1_parser,
    sm30_parser,
    sm37_parser,
    spro_parser,
    st22_parser,
)
from sapguimcp.backend.webgui.parsers.screen_state_parser import parse_selection_screen_state
from sapguimcp.lang.schema import LanguagePack
from sapguimcp.models import SE37ParameterCategory
from sapguimcp.tools.se11_tools import _parse_se11_fields, _parse_se11_yaml

from . import pseudo_fixtures as pf

TESTDATA = Path(__file__).parent.parent / "webgui" / "testdata"

Probe = Callable[[str, LanguagePack, Path], Any]
"""``(snapshot, t, fixture path) -> result``; runs with the session language set."""


# =============================================================================
# What to call a fixture's object (the parsers take the requested name as an argument)
# =============================================================================

_NAME_IN_HEADING = re.compile(r'heading "[^"]*?(?<![\w/])([A-Z][A-Z0-9_/]*_[A-Z0-9_/]+)(?![\w/])')


def _object_name(snapshot: str, default: str = "ZZZ_NOT_THERE") -> str:
    """The technical name in the screen title, as the tool would have been asked for it."""
    match = _NAME_IN_HEADING.search(snapshot)
    return match.group(1) if match else default


def _from_file_name(path: Path, pattern: str, default: str) -> str:
    match = re.search(pattern, path.name)
    return match.group(1).upper() if match else default


# =============================================================================
# Probes per parser family
# =============================================================================


def _se37_parameters(snapshot: str, t: LanguagePack, _: Path) -> Any:
    return {
        category: se37_parser.parse_se37_parameters_snapshot(snapshot, category, t)
        for category in get_args(SE37ParameterCategory)
    }


def _se37_exceptions(snapshot: str, t: LanguagePack, path: Path) -> Any:
    """The exceptions parser only ever sees the Exceptions tab, so only those captures are probed."""
    if "_exceptions_" not in path.name:
        return None
    return se37_parser.parse_se37_exceptions_snapshot(snapshot, t)


def _se37_with_tabs(snapshot: str, t: LanguagePack, path: Path) -> Any:
    """The full lookup result: every parameter tab reads this capture, the exceptions tab its own."""
    tabs = se37_parser.SE37TabSnapshots(
        import_tab=snapshot,
        export_tab=snapshot,
        changing_tab=snapshot,
        tables_tab=snapshot,
        exceptions_tab=snapshot if "_exceptions_" in path.name else None,
    )
    return se37_parser.parse_se37_snapshot(snapshot, _object_name(snapshot), t, tabs)


def _se24_with_tabs(snapshot: str, t: LanguagePack, _: Path) -> Any:
    tabs = se24_parser.SE24TabSnapshots(methods_tab=snapshot, attributes_tab=snapshot, interfaces_tab=snapshot)
    return se24_parser.parse_se24_snapshot(snapshot, _object_name(snapshot), t, tabs)


def _sm30_view(path: Path) -> str:
    return _from_file_name(path, r"sm30_(v_\w+?)_display", "ZZZNOTEXIST99")


def _spro_query(path: Path) -> str:
    return _from_file_name(path, r"results_([a-z]+)_", "test").capitalize()


_PROBES: dict[str, dict[str, Probe]] = {
    "se11": {
        "table": lambda s, t, _: _parse_se11_yaml(s, "table", t),
        "structure": lambda s, t, _: _parse_se11_yaml(s, "structure", t),
        "fields": lambda s, t, _: _parse_se11_fields(s, t),
    },
    "se16": {
        "snapshot": lambda s, t, _: se16_parser.parse_se16_snapshot(s, t),
        "hit_count": lambda s, t, _: se16_parser.parse_se16_hit_count(s, t),
        "columns": lambda s, t, _: se16_parser.parse_se16_columns(s, t),
        "rows": lambda s, t, _: se16_parser.parse_se16_rows(s, t),
        "selection_screen": lambda s, _t, _: parse_selection_screen_state(s),
    },
    "se24": {
        "snapshot": lambda s, t, _: se24_parser.parse_se24_snapshot(s, _object_name(s), t),
        "snapshot_with_tabs": _se24_with_tabs,
        "methods": lambda s, t, _: se24_parser.parse_se24_methods_snapshot(s, t),
        "attributes": lambda s, t, _: se24_parser.parse_se24_attributes_snapshot(s, t),
    },
    "se37": {
        "snapshot": lambda s, t, _: se37_parser.parse_se37_snapshot(s, _object_name(s), t),
        "snapshot_with_tabs": _se37_with_tabs,
        "parameters": _se37_parameters,
        "exceptions": _se37_exceptions,
    },
    "se09": {
        "list": lambda s, t, _: se09_parser.parse_se09_transport_list(s, t),
    },
    "se93": {
        "snapshot": lambda s, t, p: se93_parser.parse_se93_snapshot(
            s, _from_file_name(p, r"se93_(\w+?)_details", "ZZZNOTEXIST99"), t
        ),
    },
    "sm30": {
        "view_type": lambda s, t, _: sm30_parser.detect_sm30_view_type(s, t),
        "columns": lambda s, t, _: sm30_parser.parse_sm30_columns(s, t),
        "rows": lambda s, t, _: sm30_parser.parse_sm30_rows(s, t),
        "snapshot": lambda s, t, p: sm30_parser.parse_sm30_snapshot(s, _sm30_view(p), t),
    },
    "spro": {
        "results": lambda s, t, p: spro_parser.parse_spro_search_results(s, _spro_query(p), t),
    },
    "sm37": {
        "no_jobs": lambda s, t, _: sm37_parser.is_no_jobs_found(s, t),
        "is_job_list": lambda s, t, _: sm37_parser.is_job_list_screen(s, t),
        "job_list": lambda s, t, _: sm37_parser.parse_sm37_job_list(s, t),
        "job_log": lambda s, t, _: sm37_parser.parse_sm37_job_log(s, "ZZZ_JOB", t),
    },
    "slg1": {
        "is_initial": lambda s, t, _: slg1_parser.is_slg1_initial_screen(s, t),
        "is_log_list": lambda s, t, _: slg1_parser.is_slg1_log_list_screen(s, t),
        "no_results": lambda s, t, _: slg1_parser.is_slg1_no_results(s, t),
        "log_list": lambda s, t, _: slg1_parser.parse_slg1_log_list(s, t),
    },
    "st22": {
        "initial": lambda s, t, _: st22_parser.parse_st22_initial_screen(s, t),
        "no_dumps": lambda s, t, _: st22_parser.is_no_dumps_message(s, t),
        "dump_list": lambda s, t, _: st22_parser.parse_st22_dump_list(s, t),
        "dump_detail": lambda s, t, _: st22_parser.parse_st22_dump_detail(s, t),
    },
    # The message-bar note of every captured screen (check / activate / save results of the editors).
    "toolbar_note": {
        "note": lambda s, _t, _: _parse_toolbar_note(s),
    },
}

_DIRECTORIES: dict[str, tuple[str, ...]] = {
    "se11": ("yaml_snapshots",),
    "se16": ("se16_exploration",),
    "se24": ("se24_exploration", "se24_edit_exploration"),
    "se37": ("se37_exploration", "se37_edit_exploration"),
    "se09": ("se09_exploration",),
    "se93": ("se93_exploration",),
    "sm30": ("sm30_exploration",),
    "spro": ("spro_exploration",),
    "sm37": ("sm37_exploration",),
    "slg1": ("slg1_exploration",),
    "st22": ("st22_exploration",),
    "toolbar_note": (
        "se24_edit_exploration",
        "se37_edit_exploration",
        "se38_edit_exploration",
        "abapgit_exploration",
        "sm30_exploration",
        "se24_exploration",
        "se37_exploration",
        "se93_exploration",
    ),
}

_UNSUFFIXED: dict[str, str] = dict.fromkeys(
    (
        "se16n_5000_debug.yaml",
        "se16n_after_copy.yaml",
        "se16n_after_select_all.yaml",
        "se16n_export_menu.yaml",
        "se16n_initial.yaml",
        "se16n_norows_page69.yaml",
        "se16n_pagination_initial.yaml",
        "se16n_pagination_strategy1.yaml",
        "se16n_pagination_strategy2.yaml",
        "se16n_pagination_strategy3.yaml",
        "se16n_pagination_strategy4.yaml",
        "se16n_t000_results.yaml",
        "se16n_tstc_last_page.yaml",
    ),
    "EN",
)
"""Language of the captures whose file name has no ``_de`` / ``_en`` suffix (all English SE16N screens)."""

_SKIPPED: dict[str, str] = {}
"""Fixtures left out of the harness, by file name, with the reason."""


_ST22_LIST_DE = """- grid:
  - row "Datum Uhrzeit Benutzer Laufzeitfehler Abgebrochenes Programm Kurztext":
    - columnheader "Datum"
    - columnheader "Uhrzeit"
    - columnheader "Benutzer"
    - columnheader "Laufzeitfehler"
    - columnheader "Abgebrochenes Programm"
    - columnheader "Kurztext"
  - row "11.11.2026 14:32:15 TESTUSER RABAX_STATE ZTEST_PROGRAM Ausnahmebedingung ausgelöst":
    - gridcell "11.11.2026"
    - gridcell "14:32:15"
    - gridcell "TESTUSER"
    - gridcell "RABAX_STATE"
    - gridcell "ZTEST_PROGRAM"
    - gridcell "Ausnahmebedingung ausgelöst"
  - row "11.11.2026 15:00:00 USER2 MESSAGE_TYPE_X ZPROG2 Der aktuelle Anwendungsprogramm hat einen Fehler erkannt":
    - gridcell "11.11.2026"
    - gridcell "15:00:00"
    - gridcell "USER2"
    - gridcell "MESSAGE_TYPE_X"
    - gridcell "ZPROG2"
    - gridcell "Der aktuelle Anwendungsprogramm hat einen Fehler erkannt"
"""

_ST22_LIST_EN = """- grid:
  - row "Date Time User Runtime Errors Terminated Program Short Text":
    - columnheader "Date"
    - columnheader "Time"
    - columnheader "User"
    - columnheader "Runtime Errors"
    - columnheader "Terminated Program"
    - columnheader "Short Text"
  - row "11.11.2026 14:32:15 TESTUSER RABAX_STATE ZTEST_PROGRAM Exception condition triggered":
    - gridcell "11.11.2026"
    - gridcell "14:32:15"
    - gridcell "TESTUSER"
    - gridcell "RABAX_STATE"
    - gridcell "ZTEST_PROGRAM"
    - gridcell "Exception condition triggered"
"""

_ST22_DETAIL_DE = """- document:
  - text: "ABAP Laufzeitfehler"
  - text: "Laufzeitfehler: RABAX_STATE"
  - text: "Kurztext"
  - text: "Ausnahmebedingung ausgelöst"
  - text: "Was ist geschehen?"
  - text: "Das laufende Programm wurde abgebrochen."
  - text: "Was können Sie tun?"
  - text: "Wenden Sie sich an Ihren Systemverwalter."
  - text: "Fehleranalyse"
  - text: "Ein Fehler trat in Zeile 42 von ZTEST_PROGRAM auf."
  - text: "Informationen zur Abbruchstelle"
  - text: "Programm: ZTEST_PROGRAM"
  - text: "Zeile im Quelltext: 42"
  - text: "Quelltextauszug"
  - text: "Quelltext des Programms ZTEST_PROGRAM"
  - text: "Aktive Aufrufe/Ereignisse"
  - text: "ZTEST_PROGRAM Zeile 42"
  - text: "SAPMSYST Zeile 100"
  - text: ""
  - text: "Ausgewählte Variablen"
"""

_ST22_DETAIL_EN = """- document:
  - text: "ABAP Runtime Errors"
  - text: "Runtime Error: MESSAGE_TYPE_X"
  - text: "Short Text"
  - text: "The current application program has detected a situation that should not occur."
  - text: "What happened?"
  - text: "The current program had to be terminated."
  - text: "What can you do?"
  - text: "Contact your system administrator."
  - text: "Error Analysis"
  - text: "A termination occurred in line 100 of ZPROG_MAIN."
  - text: "Information on Where Terminated"
  - text: "Program: ZPROG_MAIN"
  - text: "Source Code Line: 100"
  - text: "Source Code Extract"
  - text: "Source Code of ZPROG_MAIN"
  - text: "Active Calls/Events"
  - text: "ZPROG_MAIN Line 100"
  - text: "SAPMSYST Line 200"
  - text: ""
  - text: "Chosen Variables"
"""

_SYNTHETIC: dict[str, dict[str, str]] = {
    "st22": {
        "synthetic_st22_dump_list_de.yaml": _ST22_LIST_DE,
        "synthetic_st22_dump_list_en.yaml": _ST22_LIST_EN,
        "synthetic_st22_dump_detail_de.yaml": _ST22_DETAIL_DE,
        "synthetic_st22_dump_detail_en.yaml": _ST22_DETAIL_EN,
    },
}
"""Hand-written screens for parsers no capture exercises: every ST22 capture is the initial
screen, so the dump list and the dump detail would otherwise run on nothing."""


@dataclass(frozen=True)
class Case:
    """One fixture of one parser family."""

    family: str
    path: Path
    language: str
    text: str | None = None
    """The snapshot of a synthetic fixture; ``None`` reads ``path``."""

    @property
    def id(self) -> str:
        return f"{self.family}:{self.path.name}"

    def read(self) -> str:
        return self.text if self.text is not None else pf.unwrap_envelope(self.path.read_text(encoding="utf-8"))


def _language_of(path: Path) -> str | None:
    match = re.search(r"_(de|en)$", path.stem)
    if match:
        return match.group(1).upper()
    return _UNSUFFIXED.get(path.name)


def _cases() -> Iterator[Case]:
    for family, directories in _DIRECTORIES.items():
        for directory in directories:
            for path in sorted((TESTDATA / directory).glob("*.yaml")):
                language = _language_of(path)
                assert language is not None, f"{path.name}: add its language to _UNSUFFIXED"
                yield Case(family, path, language)
        for name, text in _SYNTHETIC.get(family, {}).items():
            path = Path("synthetic") / name
            language = _language_of(path)
            assert language is not None
            yield Case(family, path, language, text)


CASES = list(_cases())


# =============================================================================
# Running a fixture in both worlds
# =============================================================================


_VOLATILE = frozenset({"retrieved_at"})
"""Result fields that differ between any two calls (the time of the call)."""


def _plain(value: Any) -> Any:
    """A parser result as plain JSON-like data."""
    if isinstance(value, BaseModel):
        return _plain(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items() if key not in _VOLATILE}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted(_plain(item) for item in value)
    return value


def _run(probe: Probe, snapshot: str, t: LanguagePack, path: Path) -> Any:
    try:
        return _plain(probe(snapshot, t, path))
    except Exception as error:  # pylint: disable=broad-exception-caught  # an error is a result to compare too
        return {"raised": type(error).__name__}


@dataclass(frozen=True)
class Outcome:
    """The results of every probe of a family on one fixture."""

    real: dict[str, Any]
    """On the captured fixture, under the session view of its language."""
    pseudo: dict[str, Any]
    """On the rewritten fixture, under the pseudo pack, pseudo letters mapped back."""
    crossed: dict[str, Any]
    """On the *captured* fixture under the pseudo pack: what a parser sees when its texts are gone."""
    replaced: int


@pytest.fixture(scope="session")
def rewritten_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Rewritten fixtures are written once per run and shared by every parser family."""
    return tmp_path_factory.mktemp("pseudo_fixtures")


def _rewritten(case: Case, original: str, directory: Path) -> tuple[str, int]:
    target = directory / case.language / case.path.parent.name / case.path.name
    counter = target.with_suffix(".replaced")
    if not target.exists():
        rewrite = pf.rewrite_aria(original, case.language)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rewrite.text, encoding="utf-8")
        counter.write_text(str(rewrite.replaced), encoding="utf-8")
    return target.read_text(encoding="utf-8"), int(counter.read_text(encoding="utf-8"))


_outcomes: dict[str, Outcome] = {}


def _outcome(case: Case, directory: Path) -> Outcome:
    cached = _outcomes.get(case.id)
    if cached is not None:
        return cached
    original = case.read()
    assert not pf.PSEUDO_LETTERS & set(original), "the fixture already holds pseudo letters; restore() would corrupt it"
    rewritten, replaced = _rewritten(case, original, directory)
    probes = _PROBES[case.family]
    locale = pf.pseudo_locale(case.language)
    with lang.use(case.language):
        real = {name: _run(probe, original, locale.view, case.path) for name, probe in probes.items()}
    with pf.pseudo_session(case.language):
        pseudo = {name: pf.restore(_run(probe, rewritten, locale.pack, case.path)) for name, probe in probes.items()}
        crossed = {name: _run(probe, original, locale.pack, case.path) for name, probe in probes.items()}
    outcome = _outcomes[case.id] = Outcome(real=real, pseudo=pseudo, crossed=crossed, replaced=replaced)
    return outcome


def _difference(real: Any, pseudo: Any) -> str:
    left = json.dumps(real, ensure_ascii=False, indent=1, sort_keys=True, default=str).splitlines()
    right = json.dumps(pseudo, ensure_ascii=False, indent=1, sort_keys=True, default=str).splitlines()
    lines = [f"  real  : {a}\n  pseudo: {b}" for a, b in zip(left, right, strict=False) if a != b][:8]
    if len(left) != len(right):
        lines.append(f"  real has {len(left)} lines, pseudo {len(right)}")
    return "\n".join(lines)


# =============================================================================
# Tests
# =============================================================================


def test_the_pseudo_alphabet_is_sound() -> None:
    pf.check_alphabet()


@pytest.mark.parametrize("case", [case for case in CASES if case.path.name not in _SKIPPED], ids=lambda case: case.id)
def test_parser_result_is_the_same_in_the_pseudo_language(case: Case, rewritten_dir: Path) -> None:
    outcome = _outcome(case, rewritten_dir)
    differing = {
        name: _difference(outcome.real[name], outcome.pseudo[name])
        for name in outcome.real
        if outcome.real[name] != outcome.pseudo[name]
    }
    assert not differing, f"{case.id} ({case.language}): the result depends on a real spelling in\n" + "\n".join(
        f"- {name}\n{text}" for name, text in differing.items()
    )


@pytest.mark.parametrize("family", sorted(_PROBES))
def test_the_family_really_reads_pack_texts(family: str, rewritten_dir: Path) -> None:
    """Guards against a vacuous pass: for every probe, some captured fixture parses differently once
    the pack no longer holds its texts, and that fixture had pack texts rewritten."""
    cases = [case for case in CASES if case.family == family and case.path.name not in _SKIPPED]
    assert cases
    sensitive: set[str] = set()
    for case in cases:
        outcome = _outcome(case, rewritten_dir)
        if outcome.replaced:
            sensitive.update(name for name in outcome.real if outcome.real[name] != outcome.crossed[name])
    not_shown = _NOT_SHOWN.get(family, {})
    assert not sensitive & set(not_shown), f"{family}: {sorted(sensitive & set(not_shown))} are shown after all"
    insensitive = set(_PROBES[family]) - sensitive - set(not_shown)
    assert not insensitive, f"{family}: no fixture shows that {sorted(insensitive)} read a pack text"


_NOT_SHOWN: dict[str, dict[str, str]] = {
    "se16": {"selection_screen": "language-independent: reads roles and field values only"},
    "sm30": {
        "view_type": "the pack text only tells the initial screen from a view without a grid, "
        "and both are 'unsupported'; the captures hold no such view"
    },
}
"""Probes whose captures cannot show a dependency on the pack, with the reason. They still run in
both worlds and must agree."""


def test_skipped_fixtures_exist() -> None:
    names = {case.path.name for case in CASES}
    assert set(_SKIPPED) <= names, sorted(set(_SKIPPED) - names)
