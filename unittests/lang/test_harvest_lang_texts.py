"""``scripts/harvest_lang_texts.py`` without SAP: SQL, comparison, XML parsing (#1044, phase 2c)."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from sapguimcp.lang import pack_for, supported_languages
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.sources import SOURCES, DataElement, DomainValue, Manual, Message, ScreenText, Source, Transaction
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


class TestDraft:
    """``--draft`` without SAP: the draft of a fake language compiles and has EN's structure (#1044)."""

    @staticmethod
    def _fake_fetch(path: str, _source: Source) -> list[str]:
        return {"se16.hit_count_label": ["Anzahl Treffer ", "Anzahl Treffer"]}.get(path, [f"zz {path}"])

    @staticmethod
    def _load(source: str, tmp_path: Path) -> ModuleType:
        module_path = tmp_path / "zz.py"
        module_path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("zz_draft", module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_draft_compiles_with_en_fields_and_flags(self, tmp_path: Path) -> None:
        source = harvest.draft("ZZ", self._fake_fetch)
        compile(source, "zz.py", "exec")
        pack = self._load(source, tmp_path).ZZ
        en_leaves = dict(iter_leaves(pack_for("EN")))
        leaves = dict(iter_leaves(pack))
        assert leaves.keys() == en_leaves.keys()
        assert pack.code == "ZZ"
        for path, leaf in leaves.items():
            assert type(leaf) is type(en_leaves[path]), path
            assert leaf.fold == en_leaves[path].fold, path
            if isinstance(leaf, Text):
                assert leaf.word == en_leaves[path].word, path  # type: ignore[attr-defined]

    def test_sourced_equal_text_field_holds_the_sap_text(self) -> None:
        source = harvest.draft("ZZ", self._fake_fetch)
        assert 'hit_count_label=Text(("Anzahl Treffer",)),' in source

    def test_manual_fields_keep_en_with_a_todo(self) -> None:
        manual = next(path for path, src in SOURCES.items() if isinstance(src, Manual))
        source = harvest.draft("ZZ", self._fake_fetch)
        line = next(line for line in source.splitlines() if f"TODO translate (Manual: {SOURCES[manual].reason}" in line)
        assert "TODO" in line

    def test_fragment_fields_keep_en_and_quote_the_sap_text(self) -> None:
        fragment = next(
            path for path, src in SOURCES.items() if not isinstance(src, Manual) and src.relation == "fragment"
        )
        source = harvest.draft("ZZ", self._fake_fetch)
        assert f"TODO fragment of: zz {fragment}" in source

    def test_missing_sap_text_keeps_en_with_a_todo(self) -> None:
        source = harvest.draft("ZZ", lambda _path, _source: [])
        assert "TODO translate (SAP has no text in this language)" in source

    def test_scalars_are_placeholders(self) -> None:
        source = harvest.draft("ZZ", self._fake_fetch)
        for marker in ("html_lang=", "logon_dropdown=", "date_format=", "same_as_en=frozenset()"):
            assert any(marker in line and "TODO" in line for line in source.splitlines()), marker

    def test_rejects_a_bad_language_key(self) -> None:
        with pytest.raises(ValueError, match="language key"):
            harvest.draft("Z'", self._fake_fetch)

    def test_main_writes_the_draft_to_out_and_does_not_register(self, tmp_path: Path) -> None:
        texts = tmp_path / "texts.json"
        texts.write_text('{"se16.hit_count_label": ["Anzahl Treffer"]}', encoding="utf-8")
        out = tmp_path / "zz.py"
        assert harvest.main(["zz", "--draft", "--sap-texts", str(texts), "--out", str(out)]) == 0
        compile(out.read_text(encoding="utf-8"), str(out), "exec")
        assert "ZZ" not in supported_languages()

    def test_main_does_not_overwrite_an_existing_out_file(self, tmp_path: Path) -> None:
        out = tmp_path / "zz.py"
        out.write_text("keep", encoding="utf-8")
        texts = tmp_path / "t.json"
        texts.write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit) as exit_info:
            harvest.main(["zz", "--draft", "--sap-texts", str(texts), "--out", str(out)])
        assert exit_info.value.code == 2
        assert out.read_text(encoding="utf-8") == "keep"

    def test_main_reports_an_unwritable_out_path(self, tmp_path: Path) -> None:
        texts = tmp_path / "texts.json"
        texts.write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit) as exit_info:
            harvest.main(["zz", "--draft", "--sap-texts", str(texts), "--out", str(tmp_path / "no_dir" / "zz.py")])
        assert exit_info.value.code == 2

    def test_main_prints_to_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        texts = tmp_path / "texts.json"
        texts.write_text("{}", encoding="utf-8")
        assert harvest.main(["zz", "--draft", "--sap-texts", str(texts)]) == 0
        assert capsys.readouterr().out.startswith('"""ZZ language pack: DRAFT')

    def test_draft_needs_an_installed_language(self, capsys: pytest.CaptureFixture[str]) -> None:
        preview = SimpleNamespace(query=lambda _sql: [])
        config = SimpleNamespace(systems={"sysA": object()}, default_system="sysA")
        with (
            patch.object(harvest, "load_default", return_value=config),
            patch.object(harvest.AdtPreview, "for_system", return_value=preview),
        ):
            assert harvest.main(["zz", "--draft"]) == 2
        assert "not a language of T002" in capsys.readouterr().err


def test_print_sql_accepts_an_unregistered_language(capsys: pytest.CaptureFixture[str]) -> None:
    assert harvest.main(["ZZ", "--print-sql"]) == 0
    assert "LAISO = 'ZZ'" in capsys.readouterr().out


def test_verify_rejects_an_unregistered_language() -> None:
    with pytest.raises(SystemExit) as exit_info:
        harvest.main(["ZZ", "--verify", "--sap-texts", "x.json"])
    assert exit_info.value.code == 2


def test_unsupported_language_is_a_parser_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        harvest.main(["XX", "--verify", "--sap-texts", "x.json"])
    assert exit_info.value.code == 2
    assert "unsupported language" in capsys.readouterr().err


def test_unknown_system_is_a_parser_error(capsys: pytest.CaptureFixture[str]) -> None:
    fake_config = SimpleNamespace(systems={"sysA": object()}, default_system="sysA")
    with patch.object(harvest, "load_default", return_value=fake_config), pytest.raises(SystemExit) as exit_info:
        harvest.main(["EN", "--verify", "--system", "sysZ"])
    assert exit_info.value.code == 2
    assert "unknown --system" in capsys.readouterr().err


def test_offline_modes_need_no_configuration(tmp_path: Path) -> None:
    """--print-sql and --verify --sap-texts work without systems.json (Copilot review on #1053)."""
    sap_texts = tmp_path / "texts.json"
    sap_texts.write_text("{}", encoding="utf-8")
    with patch.object(harvest, "load_default", side_effect=FileNotFoundError("no systems.json")) as load:
        assert harvest.main(["EN", "--print-sql"]) == 0
        # An empty texts file makes every sourced field drift (exit 1), but no configuration is read.
        assert harvest.main(["EN", "--verify", "--sap-texts", str(sap_texts)]) in (0, 1)
    load.assert_not_called()
