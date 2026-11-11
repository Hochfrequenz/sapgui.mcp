"""``scripts/harvest_lang_texts.py`` without SAP: SQL, comparison, XML parsing (#1044, phase 2c)."""

from unittest.mock import patch

import pytest

from sapguimcp.lang.sources import DataElement, DomainValue, Manual, Message, ScreenText, Source, Transaction
from sapguimcp.lang.text import RegexText, Template, Text
from unittests.lang.harvest_script import harvest

PREVIEW_XML = """<?xml version="1.0" encoding="utf-8"?>
<dataPreview:tableData xmlns:dataPreview="http://www.sap.com/adt/dataPreview">
  <dataPreview:totalRows>2</dataPreview:totalRows>
  <dataPreview:columns>
    <dataPreview:metadata dataPreview:name="TEXT"/>
    <dataPreview:dataSet>
      <dataPreview:data>Tabelle &amp;1 nicht gefunden</dataPreview:data>
      <dataPreview:data/>
    </dataPreview:dataSet>
  </dataPreview:columns>
</dataPreview:tableData>"""


class TestSql:
    def test_data_element_reads_the_requested_length(self) -> None:
        sql = harvest.sql_for(DataElement("TABNAME", "medium"), "DE")
        assert sql.startswith("SELECT SCRTEXT_M FROM DD04T WHERE ROLLNAME = 'TABNAME'")
        assert "DDLANGUAGE IN ( SELECT SPRAS FROM T002 WHERE LAISO = 'DE' )" in sql

    @pytest.mark.parametrize(
        ("source", "table"),
        [
            (ScreenText("SAPLSEUK", "0100", "RB_TABL"), "D021T"),
            (Message("00", "001"), "T100"),
            (DomainValue("BTCSTATUS", "F"), "DD07T"),
            (Transaction("SE16"), "TSTCT"),
        ],
    )
    def test_each_source_kind_reads_its_table(self, source: Source, table: str) -> None:
        assert f"FROM {table} " in harvest.sql_for(source, "EN")

    @pytest.mark.parametrize("name", ["X' OR '1' = '1", "lower", ""])
    def test_rejects_values_that_are_not_technical_ids(self, name: str) -> None:
        with pytest.raises(ValueError, match="technical ID"):
            harvest.sql_for(Transaction(name), "EN")

    def test_rejects_a_bad_language_key(self) -> None:
        with pytest.raises(ValueError, match="language key"):
            harvest.sql_for(Transaction("SE16"), "D'")

    def test_manual_has_no_sql(self) -> None:
        with pytest.raises(ValueError, match="Manual"):
            harvest.sql_for(Manual("composed"), "EN")


class TestDrift:
    def test_equal_text_matches_case_insensitively(self) -> None:
        assert harvest.drift(Text(("Tabellenname",)), DataElement("TABNAME", "medium"), ["TABELLENNAME "]) is None

    def test_changed_text_is_reported(self) -> None:
        finding = harvest.drift(Text(("Tabellenname",)), DataElement("TABNAME", "medium"), ["Tabelle"])
        assert finding == "SAP says ['Tabelle']"

    def test_fragment_ignores_message_placeholders(self) -> None:
        source = Message("00", "001", relation="fragment")
        assert harvest.drift(Text(("nicht gefunden",)), source, ["Tabelle &1 nicht gefunden"]) is None

    def test_template_matches_a_message_with_placeholders(self) -> None:
        template = Template(("Tabelle {name} nicht gefunden",))
        assert harvest.drift(template, Message("00", "001"), ["Tabelle &1 nicht gefunden"]) is None

    def test_regex_text_searches(self) -> None:
        assert harvest.drift(RegexText(("Dictionary.*Typ",)), Message("00", "002"), ["Dictionary-Typ"]) is None

    def test_any_row_may_match(self) -> None:
        assert harvest.drift(Text(("B",)), Message("00", "003"), ["A", "B"]) is None

    def test_missing_text_is_reported(self) -> None:
        assert harvest.drift(Text(("A",)), Transaction("SE16"), ["", " "]) == "SAP has no text for this source"


def test_parse_preview_returns_first_column_rows() -> None:
    assert harvest.parse_preview(PREVIEW_XML) == ["Tabelle &1 nicht gefunden", ""]


def test_verify_skips_manual_sources_and_reports_drift() -> None:
    sources = {
        "se16.hit_count_label": DataElement("ZZ_HITS", "long"),
        "se16.column_selection": Manual("not yet looked up"),
    }
    with patch.object(harvest, "SOURCES", sources), patch.object(harvest, "iter_leaves") as leaves:
        leaves.return_value = [
            ("se16.hit_count_label", Text(("Number of Hits",))),
            ("se16.column_selection", Text(("Column Selection",))),
        ]
        findings = harvest.verify("EN", lambda _path, _source: ["Hit count"])
    assert findings == {"se16.hit_count_label": "SAP says ['Hit count']"}


def test_print_sql_lists_only_sourced_fields(capsys: pytest.CaptureFixture[str]) -> None:
    sources = {"a.b": Transaction("SE16"), "a.c": Manual("framework text")}
    with patch.object(harvest, "SOURCES", sources):
        assert harvest.main(["EN", "--print-sql"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "a.b\tSELECT TTEXT FROM TSTCT WHERE TCODE = 'SE16' AND SPRSL IN ( SELECT SPRAS FROM T002 WHERE LAISO = 'EN' )"
    ]


def test_draft_is_not_implemented() -> None:
    with pytest.raises(SystemExit) as exit_info:
        harvest.main(["DE", "--draft"])
    assert exit_info.value.code == 2
