"""SE09 / SE93 parsers in both logon languages (#1044, phase 3, area 4).

The SE09 list region is named ``Liste`` in German and ``List`` in English; the parser used to look
for the German name only, so an English session saw no transport at all.
"""

from pathlib import Path

import pytest

from sapguimcp import lang
from sapguimcp.backend.webgui.parsers.se09_parser import parse_se09_transport_list
from sapguimcp.backend.webgui.parsers.se93_parser import parse_se93_snapshot
from sapguimcp.models import SE93Entry, SE93Error

_SE93_DIR = Path(__file__).parent / "testdata" / "se93_exploration"

_SE09_DE = """\
- main "Transport Organizer: Aufträge":
  - 'heading "Transport Organizer: Aufträge" [level=1]'
  - row "Liste":
    - cell "Liste":
      - region "Liste":
        - text: Änderungsaufträge mit Beteiligung von USER01
        - text: Workbench Workbench-Auftrag
        - text: "-> DUM Dummy Queue"
        - text: Änderbar
        - text: ABCK900001
        - text: USER01 first description
        - text: Customizing Customizing-Auftrag
        - text: Freigegeben
        - text: ABCK900002
        - text: USER01 second description
      - cell
"""

_SE09_EN = """\
- main "Transport Organizer: Requests":
  - 'heading "Transport Organizer: Requests" [level=1]'
  - row "List":
    - cell "List":
      - region "List":
        - text: Change requests with participation of USER01
        - text: Workbench Workbench Request
        - text: "-> DUM Dummy Queue"
        - text: Modifiable
        - text: ABCK900001
        - text: USER01 first description
        - text: Customizing Customizing Request
        - text: Released
        - text: ABCK900002
        - text: USER01 second description
      - cell
"""


@pytest.mark.parametrize(("code", "snapshot"), [("DE", _SE09_DE), ("EN", _SE09_EN)])
def test_se09_list_parses_in_both_languages(code: str, snapshot: str) -> None:
    with lang.use(code):
        result = parse_se09_transport_list(snapshot, lang.current())

    assert [
        (r.request_number, r.owner, r.description, r.status, r.request_type, r.target_system) for r in result.requests
    ] == [
        ("ABCK900001", "USER01", "first description", "Modifiable", "Workbench", "DUM"),
        ("ABCK900002", "USER01", "second description", "Released", "Customizing", "DUM"),
    ]


def test_se09_english_list_region_is_found_in_a_german_session() -> None:
    """A German session also reads the English snapshot (merged view)."""
    with lang.use("DE"):
        result = parse_se09_transport_list(_SE09_EN, lang.current())

    assert result.request_count == 2


def test_se09_screen_without_the_organizer_title_is_empty() -> None:
    with lang.use("EN"):
        result = parse_se09_transport_list('- main "Easy Access":\n  - region "List":\n', lang.current())

    assert result.request_count == 0


@pytest.mark.parametrize(
    ("name", "tcode", "transaction_type"),
    [("se93_va01_details", "VA01", "dialog"), ("se93_se38_details", "SE38", "report")],
)
def test_se93_details_parse(name: str, tcode: str, transaction_type: str) -> None:
    # The captured English "details" snapshots show the initial screen (see the next test), so only German
    # detail fixtures exist.
    snapshot = (_SE93_DIR / f"{name}_de.yaml").read_text(encoding="utf-8")

    with lang.use("DE"):
        result = parse_se93_snapshot(snapshot, tcode, lang.current())

    assert isinstance(result, SE93Entry)
    assert result.tcode == tcode
    assert result.transaction_type == transaction_type
    assert result.program


@pytest.mark.parametrize("code", ["DE", "EN"])
def test_se93_initial_screen_means_not_found(code: str) -> None:
    snapshot = (_SE93_DIR / f"se93_not_found_{code.lower()}.yaml").read_text(encoding="utf-8")

    with lang.use(code):
        result = parse_se93_snapshot(snapshot, "ZZZNOTEXIST99", lang.current())

    assert isinstance(result, SE93Error)
    assert result.error == "Transaction 'ZZZNOTEXIST99' not found"


def test_se93_parser_needs_a_language() -> None:
    with pytest.raises(lang.UnsupportedLanguageError):
        lang.current("sap_se93_lookup")
