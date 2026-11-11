"""SE11/SE16 texts of the language packs (#1044, phase 3, pilot area).

The old literals of ``se11_tools.py`` / ``se16_tools.py`` are test data here: every text the old code
matched must still be matched by the pack, in the language it came from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sapguimcp.backend.webgui.parsers.se16_parser import parse_se16_hit_count
from sapguimcp.backend.webgui.types import AriaSnapshot
from sapguimcp.tools.se16_tools import (
    _GRID_HAS_ROWS_JS,
    _check_no_entries_found,
    _check_selection_screen_columns,
    _check_table_not_found,
)
from unittests.lang.node_runner import run_node

if TYPE_CHECKING:
    from sapguimcp.lang.schema import LanguagePack

# ---------------------------------------------------------------------------
# Texts of the old code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", ["lang_de", "lang_en"])
def test_selection_columns_match_the_old_header_sets(fixture: str, request: pytest.FixtureRequest) -> None:
    t: LanguagePack = request.getfixturevalue(fixture)
    de = ["Feldname", "Option", "Von-Wert", "Bis-Wert", "Mehr", "Ausgabe", "Technischer Name"]
    en = ["Field Name", "Option", "From-Value", "To-Value", "More", "Output", "Technical Name"]
    assert _check_selection_screen_columns(de if fixture == "lang_de" else en, t)
    assert not _check_selection_screen_columns(["Transaction Code", "Program"], t)
    assert not _check_selection_screen_columns(["Feldname"], t)  # one header alone is not enough


def test_table_not_found_scans_the_snapshot_narrowly(lang_de: LanguagePack) -> None:
    assert _check_table_not_found('statusbar "ZZZ existiert nicht"', "ZZZ", lang_de) is not None
    assert _check_table_not_found('statusbar "ZZZ does not exist"', "ZZZ", lang_de) is not None
    # result data that says "nicht vorhanden" (a widening of common.does_not_exist) is not an error
    assert _check_table_not_found('gridcell "Wert nicht vorhanden"', "T000", lang_de) is None


def test_no_values_found_in_both_languages(lang_de: LanguagePack, lang_en: LanguagePack) -> None:
    assert _check_no_entries_found("statusbar: Keine Werte gefunden", lang_de)
    assert _check_no_entries_found("statusbar: No values found", lang_de)  # a DE session also matches EN
    assert _check_no_entries_found("statusbar: No values found", lang_en)
    assert not _check_no_entries_found("statusbar: 5 hits", lang_en)


@pytest.mark.parametrize("title", ["Anzahl Treffer: 5", "Number of hits", "Display of Entries Found"])
def test_results_title_matches_the_old_fragments(title: str, lang_de: LanguagePack) -> None:
    assert lang_de.se16.results_title.contains(title)


# ---------------------------------------------------------------------------
# Hit count group separators (single-language bug: only "." was accepted)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("fixture", "label"), [("lang_de", "Anzahl Treffer"), ("lang_en", "Number of Hits")])
@pytest.mark.parametrize("raw", ["5.000", "5,000", "5 000", "5\u00a0000", "5\u202f000", "5'000"])
def test_hit_count_group_separators(fixture: str, label: str, raw: str, request: pytest.FixtureRequest) -> None:
    t: LanguagePack = request.getfixturevalue(fixture)
    assert parse_se16_hit_count(AriaSnapshot(f'textbox "{label}": "{raw}"'), t) == 5000


# ---------------------------------------------------------------------------
# _GRID_HAS_ROWS_JS in Node: padding rows of the selection grid are not data rows
# ---------------------------------------------------------------------------

_HARNESS = """
const fn = (%s);
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = input.cases.map((rows) => {
    const grid = {
        querySelectorAll: () => rows.map((text) => ({ querySelector: () => null, textContent: text })),
    };
    global.document = { querySelectorAll: () => [grid] };
    return fn({ texts: input.texts });
});
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.parametrize(
    ("fixture", "padding"), [("lang_de", "Leer Leer"), ("lang_en", "Empty Empty"), ("lang_de", "Empty Empty")]
)
def test_grid_padding_rows_are_not_data_rows(fixture: str, padding: str, request: pytest.FixtureRequest) -> None:
    """EN: the placeholder is "Empty" (fixed: EN used to end the wait at once on padding rows)."""
    t: LanguagePack = request.getfixturevalue(fixture)
    cases = [[padding], [padding, padding], [padding, "MANDT Client 001"], ["MANDT Client 001"], [""]]
    payload = {"cases": cases, "texts": {"empty": t.se16.empty_cell.for_js()}}
    result = run_node(_HARNESS % _GRID_HAS_ROWS_JS, payload)
    assert result == [False, False, True, True, False]
