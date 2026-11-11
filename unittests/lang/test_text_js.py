"""``Text.for_js()`` / ``RegexText.for_js()``: the JS escaper and builder (#1044, phase 2c)."""

import pytest

from sapguimcp.lang.text import RegexText, Text
from unittests.lang.node_runner import check_patterns

SPECIALS = "a/b (c) [d] {e} | ^$*+? \\ . end"


class TestTextForJsShape:
    def test_plain_source_variants_and_flags(self) -> None:
        assert Text(("Methoden",)).for_js() == {"source": "Methoden", "flags": "iu", "variants": ["Methoden"]}

    def test_case_sensitive_text_has_no_i_flag(self) -> None:
        assert Text(("ABC",), fold=False).for_js()["flags"] == "u"

    def test_longest_variant_first_and_deduplicated(self) -> None:
        js = Text(("Programm", "Programmname", "PROGRAMM")).for_js()
        assert js["source"] == "Programmname|Programm"
        assert js["variants"] == ["Programm", "Programmname", "PROGRAMM"]

    @pytest.mark.parametrize("char", [" ", "-", "#", "&", "~", "'", '"', ":"])
    def test_does_not_escape_what_u_mode_rejects(self, char: str) -> None:
        assert "\\" not in Text((f"a{char}b",)).for_js()["source"]

    def test_escapes_syntax_characters(self) -> None:
        assert Text(("a.b(c)",)).for_js()["source"] == r"a\.b\(c\)"

    def test_word_boundaries_are_unicode_lookarounds(self) -> None:
        assert Text(("Alt",), word=True).for_js()["source"] == r"(?<![\p{L}\p{N}_])(?:Alt)(?![\p{L}\p{N}_])"

    def test_python_alt_is_unchanged(self) -> None:
        assert Text(("a b",)).alt == r"(?i:a\ b)"


class TestRegexTextForJs:
    def test_patterns_are_grouped_in_declared_order(self) -> None:
        assert RegexText(("Dictionary.*type", "b+")).for_js() == {
            "source": "(?:Dictionary.*type)|(?:b+)",
            "flags": "iu",
        }

    @pytest.mark.parametrize(
        "pattern",
        [r"\bfoo", r"foo\w+", r"\Afoo", r"foo\Z", "(?i:foo)", "(?#c)foo", r"x\Bfoo"],
    )
    def test_python_only_syntax_is_rejected(self, pattern: str) -> None:
        with pytest.raises(ValueError, match="not portable to JavaScript"):
            RegexText((pattern,)).for_js()

    def test_an_escaped_backslash_before_b_is_portable(self) -> None:
        assert RegexText((r"C:\\bin",)).for_js()["source"] == r"(?:C:\\bin)"


class TestInNode:
    def test_sources_compile_and_match_in_node(self) -> None:
        items: list[dict[str, object]] = [
            {**Text((SPECIALS,)).for_js(), "path": "specials", "matches": [SPECIALS, SPECIALS.upper()]},
            {
                **Text(("Größe",), word=True).for_js(),
                "path": "unicode word",
                "matches": ["die Größe.", "GRÖẞE ist", "größe"],
                "rejects": ["Größen", "Übergröße", "Größe_1"],
            },
            {
                **Text(("Ext. Identif.",), word=True).for_js(),
                "path": "punctuation word",
                "matches": ["Ext. Identif. 4711"],
                "rejects": ["Next. Identif."],
            },
            {**Text(("ABC",), fold=False).for_js(), "path": "case", "matches": ["xABCx"], "rejects": ["abc"]},
            {
                **RegexText((r"To select a row, press the space bar\.", r"Zum Auswählen[^\"]*Leertaste\.")).for_js(),
                "path": "regex with python identity escape",
            },
        ]
        problems = check_patterns(items)
        assert [p["path"] for p in problems] == ["regex with python identity escape"]
        assert "Invalid escape" in problems[0]["error"]
