"""Unit tests for the language pack value types (#1044, phase 2a)."""

import re

import pytest

from sapguimcp.lang.text import RegexText, Template, Text, alt_of


class TestTextValidation:
    def test_a_plain_string_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="tuple"):
            Text("Anzeigen")  # type: ignore[arg-type]

    @pytest.mark.parametrize("variants", [(), ("",), ("  ",)])
    def test_empty_variants_are_rejected(self, variants: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="Text variants"):
            Text(variants)


class TestTextMatching:
    def test_iterates_variants_in_declared_order(self) -> None:
        assert list(Text(("Source Code", "Source text"))) == ["Source Code", "Source text"]

    def test_contains_folds_case(self) -> None:
        assert Text(("Anzahl Treffer",)).contains("ANZAHL TREFFER: 5")
        assert not Text(("Abc",), fold=False).contains("abc")

    def test_contains_with_word_boundaries(self) -> None:
        alt = Text(("Alt",), word=True)
        assert alt.contains("Alt+F4")
        assert not alt.contains("Alternative")

    def test_word_boundaries_allow_punctuation_at_the_edges(self) -> None:
        text = Text(("Ext. Identif.",), word=True)
        assert text.contains("Ext. Identif. 42")
        assert not text.contains("XExt. Identif.")

    def test_equals(self) -> None:
        text = Text(("Display",))
        assert text.equals("display")
        assert not text.equals("Display IMG")

    def test_first_key_prefers_exact_then_folded(self) -> None:
        text = Text(("Methode", "Method"))
        assert text.first_key({"Method": 2, "Methode": 1}) == 1
        assert text.first_key({"METHOD": 3}) == 3
        assert text.first_key({"Other": 4}) is None
        assert Text(("Method",), fold=False).first_key({"METHOD": 3}) is None


class TestTextAlt:
    def test_longest_variant_first(self) -> None:
        match = Text(("Programm", "Programmname")).pattern.search("Programmname ZFOO")
        assert match is not None
        assert match.group() == "Programmname"

    def test_duplicates_are_dropped_case_insensitively(self) -> None:
        assert Text(("Display", "display")).alt == "(?i:Display)"

    def test_case_flag_is_scoped(self) -> None:
        pattern = re.compile(rf"{Text(('Anzahl Treffer',)).alt}: [A-Z]+$")
        assert pattern.search("anzahl treffer: ABC")
        assert not pattern.search("anzahl treffer: abc")

    def test_special_characters_are_escaped(self) -> None:
        assert Text(("Suchen (Strg+F)",)).pattern.search("Suchen (Strg+F)")
        assert not Text(("a.c",)).pattern.search("abc")

    def test_without_fold_the_group_is_case_sensitive(self) -> None:
        assert Text(("Abc",), fold=False).alt == "(?:Abc)"


class TestRegexText:
    def test_an_invalid_pattern_fails_at_construction(self) -> None:
        with pytest.raises(re.error):
            RegexText(("(unclosed",))

    def test_patterns_are_isolated_groups(self) -> None:
        regex = RegexText(("Dictionary.*Typ", "Dictionary.*type"))
        assert regex.alt == "(?i:(?:Dictionary.*Typ)|(?:Dictionary.*type))"
        assert regex.pattern.search("dictionary: TYPE")

    def test_named_groups_are_rejected(self) -> None:
        with pytest.raises(ValueError, match="belong in Template"):
            RegexText(("Display (?P<name>\\w+)",))

    def test_unnamed_groups_are_fine(self) -> None:
        assert RegexText(("Dictionary (Typ|type)",)).pattern.search("dictionary TYPE")


class TestTemplate:
    def test_search_reads_the_same_group_in_every_language(self) -> None:
        template = Template(("Klassenpflege: {name} anzeigen", "Class Builder: Display {name}"))
        for heading in ("Klassenpflege: CL_FOO anzeigen", "Class Builder: Display CL_FOO"):
            match = template.search(heading, name=r"[A-Z0-9_/]+")
            assert match is not None
            assert match["name"] == "CL_FOO"

    def test_group_value_may_be_a_text(self) -> None:
        template = Template(("{kind} {name}",))
        match = template.search("Klasse ZCL_X", kind=Text(("Klasse", "Class")), name=r"\w+")
        assert match is not None
        assert match["kind"] == "Klasse"

    def test_match_is_anchored(self) -> None:
        template = Template(("Display {name}",))
        assert template.match("Display X") is not None
        assert template.match("x Display X") is None

    def test_format_uses_the_first_variant(self) -> None:
        assert Template(("{name} anzeigen", "Display {name}")).format(name="ZFOO") == "ZFOO anzeigen"

    def test_format_needs_every_placeholder(self) -> None:
        with pytest.raises(KeyError, match="name"):
            Template(("Display {name}",)).format()

    def test_variants_must_share_placeholders(self) -> None:
        with pytest.raises(ValueError, match="differ"):
            Template(("{name} anzeigen", "Display {object}"))

    def test_a_placeholder_must_not_repeat(self) -> None:
        with pytest.raises(ValueError, match="twice"):
            Template(("{name} {name}",))

    def test_unknown_group_is_rejected(self) -> None:
        with pytest.raises(KeyError, match="other"):
            Template(("Display {name}",)).search("Display X", other=r"\w+")

    def test_a_group_value_stays_outside_the_case_fold(self) -> None:
        template = Template(("Display {name}",))
        assert template.search("Display abc", name=r"[A-Z]+") is None
        assert template.search("DISPLAY ABC", name=r"[A-Z]+") is not None  # the literal part folds

    def test_a_trailing_placeholder_captures_the_whole_rest(self) -> None:
        match = Template(("Display {name}",)).search("Display CL_FOO")
        assert match is not None
        assert match["name"] == "CL_FOO"

    def test_a_placeholder_in_the_middle_is_lazy(self) -> None:
        match = Template(("Class Builder: {name} display",)).search("Class Builder: CL_FOO display")
        assert match is not None
        assert match["name"] == "CL_FOO"

    def test_whitespace_in_a_literal_part_matches_any_whitespace_run(self) -> None:
        template = Template(("Display {name}",))
        for heading in ("Display  CL_FOO", "Display\tCL_FOO", "Display\u00a0CL_FOO"):
            match = template.search(heading, name=r"\w+")
            assert match is not None, heading
            assert match["name"] == "CL_FOO"

    def test_braces_that_are_not_identifiers_stay_literal(self) -> None:
        template = Template(("{1} and {name}",))
        assert template.placeholders == {"name"}
        assert template.format(name="X") == "{1} and X"


class TestAltOf:
    def test_joins_texts_into_one_group(self) -> None:
        pattern = re.compile(alt_of(Text(("Klasse", "Class")), Text(("Interface",))))
        assert pattern.fullmatch("interface")
        assert pattern.fullmatch("Klasse")

    def test_accepts_regex_texts(self) -> None:
        pattern = re.compile(alt_of(Text(("Klasse",)), RegexText(("Dictionary.*Typ",))))
        assert pattern.fullmatch("dictionary: Typ")

    def test_needs_a_text(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            alt_of()
