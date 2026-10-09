"""SE11 on the desktop: the key flag of a field is a checkbox column of the field list."""

from __future__ import annotations

from sapguimcp.tools.se11_tools import _parse_se11_table_rows


def _row(name: str, key: str, datatype: str, length: str) -> dict[str, str]:
    return {"Feld": name, "Key": key, "Datentyp": datatype, "Länge": length, "DezStellen": "0", "Kurzbeschreibung": ""}


def test_a_field_is_a_key_field_when_its_key_checkbox_is_checked() -> None:
    rows = [_row("MANDT", "X", "CLNT", "3"), _row("BUKRS", "X", "CHAR", "4"), _row("BUTXT", "", "CHAR", "25")]
    assert [(field.name, field.is_key) for field in _parse_se11_table_rows(rows)] == [
        ("MANDT", True),
        ("BUKRS", True),
        ("BUTXT", False),
    ]


def test_a_list_without_a_key_column_has_no_key_fields() -> None:
    rows = [{"Feld": "MANDT", "Datentyp": "CLNT", "Länge": "3", "DezStellen": "0", "Kurzbeschreibung": "Client"}]
    assert [field.is_key for field in _parse_se11_table_rows(rows)] == [False]
