"""SM30 / SPRO parsers in both logon languages (#1044, phase 3, area 5)."""

import pytest

from sapguimcp import lang
from sapguimcp.backend.webgui.parsers.sm30_parser import parse_sm30_snapshot
from sapguimcp.backend.webgui.parsers.spro_parser import parse_spro_search_results

_SM30_DE = """\
- main "Sicht anzeigen":
  - heading "Sicht \\"Globale Parameter der Länder/Regionen\\" anzeigen: Übersicht" [level=1]
  - grid:
    - rowgroup:
      - row "Spalte für Zeilenauswahl Land Name":
        - columnheader "Spalte für Zeilenauswahl"
        - columnheader "Land"
        - columnheader "Name"
    - rowgroup:
      - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. AD Andorra":
        - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
        - gridcell "AD"
        - gridcell "Andorra"
  - button "Eintrag 1 von 249"
"""

_SM30_EN = """\
- main "Display View":
  - heading "Display View \\"Countries\\": Overview" [level=1]
  - grid:
    - rowgroup:
      - row "Column for row selection Country Name":
        - columnheader "Column for row selection"
        - columnheader "Country"
        - columnheader "Name"
    - rowgroup:
      - row "To select a row, press the space bar. AD Andorra":
        - gridcell "To select a row, press the space bar."
        - gridcell "AD"
        - gridcell "Andorra"
  - button "Entry 1 of 249"
"""


@pytest.mark.parametrize(
    ("code", "snapshot", "description", "columns"),
    [
        ("DE", _SM30_DE, "Globale Parameter der Länder/Regionen", ["Land", "Name"]),
        ("EN", _SM30_EN, "Countries", ["Country", "Name"]),
    ],
)
def test_sm30_view_parses_in_both_languages(code: str, snapshot: str, description: str, columns: list[str]) -> None:
    with lang.use(code):
        result = parse_sm30_snapshot(snapshot, "V_T005", lang.current())

    assert result.view_type == "flat"
    assert result.description == description
    assert result.columns == columns
    assert [row.values for row in result.rows] == [{columns[0]: "AD", "Name": "Andorra"}]
    assert result.row_count == 249


@pytest.mark.parametrize(
    ("code", "snapshot"),
    [
        (
            "EN",
            '- main "Table View Maintenance":\n  - note "Error message bar Table/view ZZZ is not in the Dictionary"',
        ),
        (
            "DE",
            '- main "Tabellensicht-Pflege":\n  - note "Fehler Meldungsleiste Tabelle/View ZZZ ist nicht im Dictionary vorhanden"',
        ),
    ],
)
def test_sm30_unknown_view_is_not_found_in_either_language(code: str, snapshot: str) -> None:
    with lang.use(code):
        result = parse_sm30_snapshot(snapshot, "ZZZ", lang.current())

    assert not result.success
    assert result.error == "View 'ZZZ' not found"


_SPRO_EN = """\
- dialog "Search Term \\"COUNTRY\\" Hit List":
  - grid:
    - rowgroup:
      - row "To select a row, press the space bar. Define countries Countries Basic settings":
        - gridcell "To select a row, press the space bar."
        - gridcell "Define countries"
        - gridcell "Countries"
        - gridcell "Basic settings"
"""


def test_spro_english_results_in_an_english_session() -> None:
    with lang.use("EN"):
        result = parse_spro_search_results(_SPRO_EN, "country", lang.current())

    assert [a.activity_name for a in result.activities] == ["Define countries"]
