# Language Pack Core Implementation Plan (phase 2a of #1044)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `sapguimcp.lang` package exists with the three text types, the pack schema, DE/EN
packs holding today's `lang.py` content, the registry (`current()`, `universal()`, `pack_for()`,
`supported_languages()`, `use()`), and the completeness guards that need no source scanner. Every
existing `from sapguimcp.lang import X_DE` keeps working with identical values, so no consumer
changes, except the SLG1 text fix.

**Architecture:** `src/sapguimcp/lang.py` moves (with `git mv`) to `src/sapguimcp/lang/_legacy.py`
and is re-exported by the new package's `__init__.py`. `text.py` holds the sibling value types
`Text`, `RegexText`, `Template` with cached Python regex builders. `schema.py` holds the frozen,
slotted `LanguagePack`, its sections (each declaring `MERGE` as a `ClassVar`), the canonical enums
and the generic field-wise `merge`. `de.py` / `en.py` are the packs; `invariant.py` holds texts
that are the same in every logon language. `__init__.py` is the registry: it reads the phase-1
context variable through `session_language.current_language()` and caches merged views in a dict.
`models/config.py` takes its `SUPPORTED_LANGUAGES` from `lang.supported_languages()`.

**Tech Stack:** Python 3.11+, frozen slotted dataclasses, `functools.cache`, `re`, pytest.

Spec: `docs/superpowers/specs/2026-11-10-language-packs-design.md` §1–§6 and the scanner-free
part of §10. Phase 1 (session language plumbing) is already on this branch.

**Not in 2a** (split decided):

- **2b:** no-literal scanner, `lang_baseline.json`, synthetic third language (with the
  registration hook it needs, see decision 13), test pack from `lang_test.py` / `lang_strings`.
- **2c:** `sources.py`, `harvest_lang_texts.py`, `Text.for_js()` / `RegexText.for_js()` and the JS
  object-argument convention.

## Decisions made while planning

1. **Legacy shim kept verbatim.** `lang.py` moves to `lang/_legacy.py` unchanged (history kept by
   `git mv`) and gets an explicit `__all__`; `lang/__init__.py` re-exports it with
   `from sapguimcp.lang._legacy import *` plus `__all__ += _legacy.__all__` (mypy `--strict`
   accepts this; verified). Deriving ~150 constants by index from regrouped, de-duplicated pack
   fields would be brittle. Instead `unittests/lang/test_legacy_shim.py` maps every constant to its
   pack field and asserts the constant is one of that field's variants, so the two cannot drift. A
   new constant without a mapping fails the test. Only the SM37 status maps are derived from the
   packs (they are a canonical mapping). Phase 4 deletes `_legacy.py`.
2. **Sections in 2a:** one section per area that has text in `lang.py` today (`se09`, `se11`,
   `se16`, `se24`, `se37`, `se93`, `slg1`, `sm30`, `sm37`, `spro`, `st22`), `common` for the
   de-duplicated shared vocabulary ("Display" ×5, "not found"/"does not exist" ×6, row-select hint
   ×3, "no entries", user, program), and the four `all` sections. `popup`, `status_type` and
   `session_pages` start **empty**: their texts live in backends and JS today, and copying them
   into packs before the phase-3 migration moves the consumers would create a second, untested
   source of truth. `keys` is **seeded** from `sap_tools._is_keyboard_shortcut` (Ctrl/Strg,
   Shift/Umschalt, Alt, Enter/Eingabe, Delete/Entf, all `word=True`), so the `all` merge, a
   canonical mapping in an `all` section and the `same_as_en` check run on real data. `status`,
   `se38`, `abapgit`, `quick_report` are added by their phase-3 migrations, with fields in both
   packs at once (required fields).
3. **Canonical mappings** (`Mapping[Enum, Text]`, frozen with `MappingProxyType` via
   `schema.canonical()`): `sm37.status: JobStatus`, `se09.status: TransportStatus`,
   `se24.visibility: Visibility`, `st22.section: DumpSection`, `keys.names: Key`. The enums live in
   `lang/schema.py` (the package must stay import-light). Field paths use
   `section.field[member value]`, e.g. `sm37.status[Ready]`, in `same_as_en`, tests and later
   `sources.py`.
4. **Templates from today's code:** `se24.display_title` / `se37.display_title` hold the headings
   the SE24/SE37 parsers build from `*_DISPLAY_SUFFIX_DE` / `*_DISPLAY_PREFIX_EN`
   (`Klassenpflege: {name} anzeigen` / `Class Builder: Display {name}`). `spro.results_dialog`
   stays a `Text` holding today's fragments; turning it into a template needs fixture evidence
   (phase 3).
5. **`invariant.py` is its own dataclass**, `Invariant`, reached through `lang.invariant()`, not a
   section merged into `LanguagePack`. A pack field would have to be filled in every pack (required
   fields), and merging language-independent text is the identity. It holds `sm34_hint`
   (`SM30_USE_SM34_*` = "SM34", a transaction code).
6. **`universal()` returns `UniversalView`**, a dataclass with exactly the four `all` sections, not
   a full `LanguagePack`. mypy then rejects parsing a transaction screen against every language. In
   `current()` the `all` sections hold the same texts, session pack first (click-candidate
   order); `universal()` uses registration order.
7. **`current()` without a known language raises `UnsupportedLanguageError`** (message "…needs the
   session's logon language, but none is known…"). There is no fallback to the default system:
   `lang/` must not import `models.config`, every tool call sets the variable since phase 1, and
   sessions without a language (legacy `_session` setter) get only `universal()` (spec §5). No
   production code calls `current()` in 2a.
8. **`SapLanguage`, `as_sap_language` and `session_sap_language` stay unchanged in 2a.** They type
   the date formatting of SLG1/SM37/ST22 (phase-1 callers); the pack's `date_format` replaces them
   in the SM37/SLG1/ST22 migration. `models/config.py` switches to `lang.supported_languages()`, and
   a test pins `set(get_args(SapLanguage)) == set(lang.supported_languages())` until then.
9. **SLG1 text fix:** `SLG1_NO_LOGS_FOUND_EN` becomes SAP's BL 208 text "No log found in the
   database". The former text stays as `SLG1_NO_LOGS_FOUND_EN_LEGACY` and as the second variant
   of `slg1.no_logs_found`, because `unittests/test_slg1_desktop_unreadable_list.py` feeds it and
   no fixture proves that no release shows it. The SLG1 tool and parser add the legacy constant to
   their checks: the only consumer edits in 2a.
10. **Pack-level scalars** are filled now: `html_lang` (`de`/`en`), `logon_dropdown`
    (`Deutsch`/`English`, from `set_language_field.js`), `date_format` as a `strftime` pattern
    (`%d.%m.%Y`/`%m/%d/%Y`, from `utils.format_sap_date`). Nothing consumes them before phase 3.
11. **Caching:** `functools.cache` (ruff UP033 rejects `lru_cache(maxsize=None)`; same thing).
    `alt`, compiled patterns and template patterns are keyed by the value's fields; merged views
    by language code in `_views: dict[str, LanguagePack]`; `universal()` is a cached function.
12. **Merging** concatenates variants with exact de-duplication (order kept, session first);
    case-insensitive de-duplication happens only inside `alt`. Merging values with different
    `fold`/`word` flags or kinds raises, so a bad pack fails at the first view build, not
    silently.
13. **No registration API yet.** `_PACKS` is a module-level dict. Phase 2b's synthetic language
    needs a test hook that registers a pack and clears `_views` and `universal.cache_clear()`.

## Testing rules (read before running anything)

- Run unit tests **by explicit path** (`uv run --group tests python -m pytest unittests/<file> -q`).
  Never run the whole suite.
- Live tests touch the single shared SAP connection: only the controller runs them, one at a time,
  after all tasks are done (Task 9). Implementer agents do **not** run `-m integration`.
- Desktop live-test teardown closes the SAP GUI connections it opened.
- **Lint and type check** at the end of every task (from `CONTRIBUTING.md`):
  `uv run --group linting ruff check .`, `uv run --group linting ruff format --check .`,
  `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`.
- Tests that set the session language use `with lang.use(...)` (or `use_language`), so no value
  leaks into other tests.
- Commit with explicit `git add <paths>`; `git commit -a` skips new files.

## File structure

| File                                                                                              | Responsibility                                                                                                                                                |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Move `src/sapguimcp/lang.py` → `src/sapguimcp/lang/_legacy.py`                                    | former constants, verbatim, explicit `__all__`; SM37 maps derived from the packs; SLG1 EN fix                                                                 |
| Create `src/sapguimcp/lang/__init__.py`                                                           | registry and public API; re-exports `_legacy`                                                                                                                 |
| Create `src/sapguimcp/lang/text.py`                                                               | `Text`, `RegexText`, `Template`, `HasAlt`, `alt_of`, cached regex builders                                                                                    |
| Create `src/sapguimcp/lang/schema.py`                                                             | canonical enums, sections with `MERGE`, `LanguagePack`, `sections`/`iter_leaves`/`resolve`, `merge`                                                           |
| Create `src/sapguimcp/lang/de.py`, `en.py`                                                        | the packs                                                                                                                                                     |
| Create `src/sapguimcp/lang/invariant.py`                                                          | `Invariant`, `INVARIANT`                                                                                                                                      |
| Modify `src/sapguimcp/models/config.py`                                                           | `SUPPORTED_LANGUAGES = supported_languages()`                                                                                                                 |
| Modify `src/sapguimcp/tools/slg1_tools.py`, `src/sapguimcp/backend/webgui/parsers/slg1_parser.py` | accept `SLG1_NO_LOGS_FOUND_EN_LEGACY` too                                                                                                                     |
| Tests (new)                                                                                       | `unittests/lang/__init__.py`, `test_text.py`, `test_schema_merge.py`, `test_packs.py`, `test_registry.py`, `test_pack_completeness.py`, `test_legacy_shim.py` |
| Tests (modified)                                                                                  | `unittests/test_sap_config_languages.py`, `unittests/test_slg1_desktop_unreadable_list.py`, `unittests/webgui/test_slg1_parser.py`                            |

## Model assignment and order

Rule from the spec: type design and central paths go to opus (reviewed by fable); mechanical
moves and data entry go to sonnet/haiku. Escalate one level after two failed attempts or a design
finding in review; never downgrade mid-task.

| Task                                            | Implement                                | Review | Depends on | Parallel with |
| ----------------------------------------------- | ---------------------------------------- | ------ | ---------- | ------------- |
| 1 move `lang.py` into the package               | haiku                                    | sonnet | —          | —             |
| 2 `text.py` value types and regex builders      | opus                                     | fable  | 1          | —             |
| 3 `schema.py`: sections, merge modes, `merge`   | opus                                     | fable  | 2          | —             |
| 4 DE/EN packs, `invariant.py`                   | sonnet                                   | sonnet | 3          | —             |
| 5 registry in `__init__.py`                     | opus                                     | fable  | 4          | —             |
| 6 completeness guards (§10, scanner-free)       | sonnet                                   | opus   | 5          | 7, 8          |
| 7 legacy consistency, SM37 derivation, SLG1 fix | sonnet                                   | sonnet | 5          | 6, 8          |
| 8 `SUPPORTED_LANGUAGES` from the packs          | sonnet                                   | opus   | 5          | 6, 7          |
| 9 final verification and live tests             | controller (haiku may collect summaries) | —      | 6, 7, 8    | —             |

Tasks 6, 7 and 8 touch disjoint files. When they run in parallel in one working tree, each agent
stages only its own paths; if `git commit` reports `index.lock`, wait and retry the commit.

---

### Task 1: Move `lang.py` into the `lang/` package

Python cannot have both `sapguimcp/lang.py` and `sapguimcp/lang/`: a directory without
`__init__.py` loses to the module, and every later task imports `sapguimcp.lang.<submodule>`. So
the move comes first. No new test: the existing importers and their tests are the safety net.

**Files:**

- Move: `src/sapguimcp/lang.py` → `src/sapguimcp/lang/_legacy.py`
- Create: `src/sapguimcp/lang/__init__.py`

- [ ] **Step 1: Move with history**

```bash
mkdir -p src/sapguimcp/lang
git mv src/sapguimcp/lang.py src/sapguimcp/lang/_legacy.py
```

- [ ] **Step 2: Replace the module docstring** of `_legacy.py` (the first 6 lines) with:

```python
"""The former ``sapguimcp/lang.py`` constants, re-exported by ``sapguimcp.lang`` (#1044).

Kept verbatim so no importer changes in phase 2a. The packs in ``de.py`` / ``en.py`` hold the same
texts, regrouped into sections; ``unittests/lang/test_legacy_shim.py`` checks that every constant
here is a variant of its pack field, so the two cannot drift. The phase-3 migrations move each
importer to ``lang.current()``; phase 4 deletes this module.
"""
```

- [ ] **Step 3: Add `__all__`** (all upper-case constants plus `bilingual_pattern`, sorted) in
      front of the SE16 section banner:

```bash
uv run python - <<'EOF'
import pathlib, re
path = pathlib.Path("src/sapguimcp/lang/_legacy.py")
source = path.read_text(encoding="utf-8")
names = sorted(set(re.findall(r"^([A-Z][A-Z0-9_]+) = ", source, re.M)) | {"bilingual_pattern"})
block = "__all__ = [\n" + "".join(f'    "{name}",\n' for name in names) + "]\n\n\n"
marker = "# =============================================================================\n# SE16"
assert source.count(marker) == 1
path.write_text(source.replace(marker, block + marker, 1), encoding="utf-8", newline="\n")
print(len(names))
EOF
```

Expected output: `155`.

- [ ] **Step 4: Create `src/sapguimcp/lang/__init__.py`** (Task 5 replaces it with the registry):

```python
"""Language packs: every SAP-language-dependent text in one place (#1044).

Re-exports the former ``lang.py`` constants from :mod:`sapguimcp.lang._legacy` until the phase-3
migrations remove their last importer.
"""

from sapguimcp.lang import _legacy
from sapguimcp.lang._legacy import *  # noqa: F403  # re-export of the former lang.py constants

__all__: list[str] = []
__all__ += _legacy.__all__
```

- [ ] **Step 5: Check that every value is unchanged**

```bash
# <scratch> = any directory outside the repository, e.g. the agent's scratchpad
git show HEAD:src/sapguimcp/lang.py > <scratch>/old_lang.py
uv run python - <scratch>/old_lang.py <<'EOF'
import runpy, sys
import sapguimcp.lang as new
old = runpy.run_path(sys.argv[1])
names = [name for name in old if name.isupper()]
assert all(getattr(new, name) == old[name] for name in names), [n for n in names if getattr(new, n, None) != old[n]]
assert new.bilingual_pattern("a.b", "c") == old["bilingual_pattern"]("a.b", "c")
print(len(names), "constants unchanged")
EOF
```

Expected: `154 constants unchanged`.

- [ ] **Step 6: Run the importers' tests and an import smoke test** — expected PASS:

```bash
uv run python -c "import sapguimcp.tools.se09_tools, sapguimcp.tools.se11_tools, sapguimcp.tools.se16_tools, sapguimcp.tools.slg1_tools, sapguimcp.tools.sm30_tools, sapguimcp.tools.spro_tools, sapguimcp.backend.webgui.parsers.se09_parser, sapguimcp.backend.webgui.parsers.se16_parser, sapguimcp.backend.webgui.parsers.se24_parser, sapguimcp.backend.webgui.parsers.se37_parser, sapguimcp.backend.webgui.parsers.se93_parser, sapguimcp.backend.webgui.parsers.slg1_parser, sapguimcp.backend.webgui.parsers.sm30_parser, sapguimcp.backend.webgui.parsers.sm37_parser, sapguimcp.backend.webgui.parsers.spro_parser, sapguimcp.backend.webgui.parsers.st22_parser"
uv run --group tests python -m pytest unittests/webgui/test_se09_parser.py unittests/webgui/test_se11_parser.py unittests/webgui/test_se16_parser.py unittests/webgui/test_se24_parser.py unittests/webgui/test_se37_parser.py unittests/webgui/test_se93_parser.py unittests/webgui/test_slg1_parser.py unittests/webgui/test_sm30_parser.py unittests/webgui/test_sm37_parser.py unittests/webgui/test_spro_parser.py unittests/webgui/test_st22_parser.py unittests/test_spro_scope_note.py unittests/test_se09_label_parsing.py unittests/test_se11_readiness.py unittests/test_slg1_desktop_unreadable_list.py -q
```

- [ ] **Step 7: Lint and type check** (commands in the testing rules). `ruff format` may want blank
      lines around `__all__`; run `uv run --group linting ruff format src/sapguimcp/lang` if so.

- [ ] **Step 8: Commit**

```bash
git add src/sapguimcp/lang/_legacy.py src/sapguimcp/lang/__init__.py
git commit -m "refactor(lang): move lang.py into the lang package as a re-export shim (#1044)"
```

(`git mv` already staged the deletion of `src/sapguimcp/lang.py`.)

---

### Task 2: Value types `Text`, `RegexText`, `Template`

Spec §2. Siblings, not subclasses. `for_js()` is **not** part of 2a (phase 2c).

**Files:**

- Create: `src/sapguimcp/lang/text.py`
- Test: `unittests/lang/__init__.py` (empty), `unittests/lang/test_text.py`

- [ ] **Step 1: Write the failing tests** — create the empty `unittests/lang/__init__.py` and
      `unittests/lang/test_text.py`:

```python
"""Unit tests for the language pack value types (#1044, phase 2a)."""

import re

import pytest

from sapguimcp.lang.text import HasAlt, RegexText, Template, Text, alt_of


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

    def test_has_alt_protocol(self) -> None:
        assert isinstance(Text(("x",)), HasAlt)
        assert isinstance(RegexText(("x",)), HasAlt)
        assert not isinstance(Template(("{x}",)), HasAlt)


class TestRegexText:
    def test_an_invalid_pattern_fails_at_construction(self) -> None:
        with pytest.raises(re.error):
            RegexText(("(unclosed",))

    def test_patterns_are_isolated_groups(self) -> None:
        regex = RegexText(("Dictionary.*Typ", "Dictionary.*type"))
        assert regex.alt == "(?i:(?:Dictionary.*Typ)|(?:Dictionary.*type))"
        assert regex.pattern.search("dictionary: TYPE")


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


class TestAltOf:
    def test_joins_texts_into_one_group(self) -> None:
        pattern = re.compile(alt_of(Text(("Klasse", "Class")), Text(("Interface",))))
        assert pattern.fullmatch("interface")
        assert pattern.fullmatch("Klasse")

    def test_needs_a_text(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            alt_of()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/lang/test_text.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'sapguimcp.lang.text'`.

- [ ] **Step 3: Implement `src/sapguimcp/lang/text.py`**

```python
"""The three value types of a language pack: ``Text``, ``RegexText`` and ``Template`` (#1044).

They are siblings, not subclasses, so mypy rejects clicking a regex or filling a template.
All three are frozen and slotted. Slotted dataclasses have no ``__dict__``, so derived regex
sources and compiled patterns come from module-level ``functools.cache`` builders keyed by the
value's fields.

Python only. The JavaScript builder (``for_js()``) arrives with the JS object-argument
convention in phase 2c.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

T = TypeVar("T")

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_DEFAULT_GROUP = r".+?"


@runtime_checkable
class HasAlt(Protocol):
    """Anything that renders as a regex alternation group to embed into a larger regex."""

    @property
    def alt(self) -> str:
        """The regex source, a self-contained group with its own case flag."""


def _require_strings(kind: str, values: object) -> tuple[str, ...]:
    """Validate a variants/patterns tuple: a non-empty tuple of non-empty strings."""
    if not isinstance(values, tuple):
        # Text("Anzeigen") would otherwise iterate the characters of the string.
        raise TypeError(f"{kind} must be a tuple of strings, got {type(values).__name__}")
    if not values:
        raise ValueError(f"{kind} must not be empty")
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{kind} must hold non-empty strings, got {value!r}")
    return values


def _fold_key(value: str, fold: bool) -> str:
    return value.lower() if fold else value


def _unique(values: tuple[str, ...], fold: bool) -> tuple[str, ...]:
    """Drop duplicates (case-insensitively when folding), keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = _fold_key(value, fold)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return tuple(unique)


def _scoped(body: str, fold: bool) -> str:
    """Wrap ``body`` in a group that carries its own case flag."""
    return f"(?i:{body})" if fold else f"(?:{body})"


@cache
def literal_alt(variants: tuple[str, ...], fold: bool, word: bool) -> str:
    """Escaped alternation of literal variants, de-duplicated and longest first.

    Longest first, because a short variant would otherwise shadow a longer one
    (``Programm|Programmname`` captures ``name ZFOO``). ``sorted`` is stable, so variants of equal
    length keep their declared order. Word boundaries are ``(?<!\\w)…(?!\\w)`` rather than ``\\b``,
    so variants that start or end with punctuation (``Ext. Identif.``) still match.
    """
    ordered = sorted(_unique(variants, fold), key=len, reverse=True)
    body = "|".join(re.escape(variant) for variant in ordered)
    if word:
        body = rf"(?<!\w)(?:{body})(?!\w)"
    return _scoped(body, fold)


@cache
def regex_alt(patterns: tuple[str, ...], fold: bool) -> str:
    """Alternation of raw regex patterns, each isolated in its own group, in declared order."""
    body = "|".join(f"(?:{pattern})" for pattern in _unique(patterns, fold=False))
    return _scoped(body, fold)


@cache
def compiled(source: str) -> re.Pattern[str]:
    """Compile and cache a regex source."""
    return re.compile(source)


@cache
def template_patterns(
    variants: tuple[str, ...], fold: bool, groups: tuple[tuple[str, str], ...]
) -> tuple[re.Pattern[str], ...]:
    """One compiled pattern per template variant (Python rejects duplicate group names).

    ``groups`` maps placeholder names to the regex source of their capture group; placeholders
    without an entry capture ``.+?``. Literal parts are escaped.
    """
    sources = dict(groups)
    patterns: list[re.Pattern[str]] = []
    for variant in variants:
        parts: list[str] = []
        position = 0
        for match in _PLACEHOLDER.finditer(variant):
            parts.append(re.escape(variant[position : match.start()]))
            name = match.group(1)
            parts.append(f"(?P<{name}>{sources.get(name, _DEFAULT_GROUP)})")
            position = match.end()
        parts.append(re.escape(variant[position:]))
        patterns.append(re.compile(_scoped("".join(parts), fold)))
    return tuple(patterns)


def placeholder_names(variant: str) -> tuple[str, ...]:
    """Placeholder names of one template variant, in order of appearance."""
    return tuple(match.group(1) for match in _PLACEHOLDER.finditer(variant))


@dataclass(frozen=True, slots=True)
class Text:
    """Literal text with one or more variants; the common case.

    Variants cover every spelling SAP shows for one text: SAP release differences (ECC vs
    S/4HANA) and truncations. A merged view appends the variants of the fallback languages.
    """

    variants: tuple[str, ...]
    fold: bool = True
    """Case-insensitive matching (``lower()`` on both sides, the same folding as ``IGNORECASE``)."""
    word: bool = False
    """Require word boundaries around the variant (``Line``, ``Alt``, ``ja``)."""

    def __post_init__(self) -> None:
        _require_strings("Text variants", self.variants)

    def __iter__(self) -> Iterator[str]:
        """Candidates for clicking, filling or tab selection, in declared order."""
        return iter(self.variants)

    def contains(self, s: str) -> bool:
        """``True`` if any variant occurs in ``s``."""
        if self.word:
            return self.pattern.search(s) is not None
        haystack = _fold_key(s, self.fold)
        return any(_fold_key(variant, self.fold) in haystack for variant in self.variants)

    def equals(self, s: str) -> bool:
        """``True`` if ``s`` equals one of the variants (no stripping)."""
        needle = _fold_key(s, self.fold)
        return any(_fold_key(variant, self.fold) == needle for variant in self.variants)

    def first_key(self, row: Mapping[str, T]) -> T | None:
        """Value of the first variant that is a key of ``row`` (column header lookup)."""
        for variant in self.variants:
            if variant in row:
                return row[variant]
        if self.fold:
            folded: dict[str, str] = {}
            for key in row:
                folded.setdefault(key.lower(), key)
            for variant in self.variants:
                original = folded.get(variant.lower())
                if original is not None:
                    return row[original]
        return None

    @property
    def alt(self) -> str:
        """Escaped alternation for embedding, e.g. ``(?i:Number\\ of\\ Hits|Anzahl\\ Treffer)``."""
        return literal_alt(self.variants, self.fold, self.word)

    @property
    def pattern(self) -> re.Pattern[str]:
        """Compiled :attr:`alt`."""
        return compiled(self.alt)


@dataclass(frozen=True, slots=True)
class RegexText:
    """Irregular text that needs a regex; raw pattern strings. No iteration, no clicking."""

    patterns: tuple[str, ...]
    fold: bool = True

    def __post_init__(self) -> None:
        for pattern in _require_strings("RegexText patterns", self.patterns):
            re.compile(pattern)  # fail at import, not at first use

    @property
    def alt(self) -> str:
        """Alternation of all patterns, each in its own group, with the case flag scoped."""
        return regex_alt(self.patterns, self.fold)

    @property
    def pattern(self) -> re.Pattern[str]:
        """Compiled :attr:`alt`."""
        return compiled(self.alt)


@dataclass(frozen=True, slots=True)
class Template:
    """Text with placeholders whose word order depends on the language.

    ``Template(("{name} anzeigen",))`` and ``Template(("Display {name}",))``: every variant has the
    same placeholders, so callers read ``m["name"]`` regardless of language.
    """

    variants: tuple[str, ...]
    fold: bool = True

    def __post_init__(self) -> None:
        names = {placeholder_names(variant) for variant in _require_strings("Template variants", self.variants)}
        for found in names:
            if len(set(found)) != len(found):
                raise ValueError(f"Template placeholder used twice in one variant: {self.variants!r}")
        if len({frozenset(found) for found in names}) != 1:
            raise ValueError(f"Template variants differ in their placeholders: {self.variants!r}")

    @property
    def placeholders(self) -> frozenset[str]:
        """The placeholder names, identical for every variant."""
        return frozenset(placeholder_names(self.variants[0]))

    def _patterns(self, groups: Mapping[str, str | HasAlt]) -> tuple[re.Pattern[str], ...]:
        unknown = set(groups) - self.placeholders
        if unknown:
            raise KeyError(f"unknown template placeholders: {sorted(unknown)}")
        sources = tuple(
            sorted((name, value if isinstance(value, str) else value.alt) for name, value in groups.items())
        )
        return template_patterns(self.variants, self.fold, sources)

    def search(self, s: str, **groups: str | HasAlt) -> re.Match[str] | None:
        """First variant found anywhere in ``s``; a ``str`` group value is a raw regex."""
        for pattern in self._patterns(groups):
            match = pattern.search(s)
            if match is not None:
                return match
        return None

    def match(self, s: str, **groups: str | HasAlt) -> re.Match[str] | None:
        """First variant matching at the start of ``s``."""
        for pattern in self._patterns(groups):
            match = pattern.match(s)
            if match is not None:
                return match
        return None

    def format(self, **values: str) -> str:
        """The first variant with its placeholders filled in."""
        missing = self.placeholders - set(values)
        if missing:
            raise KeyError(f"missing template values: {sorted(missing)}")
        return _PLACEHOLDER.sub(lambda match: values[match.group(1)], self.variants[0])


def alt_of(*texts: HasAlt) -> str:
    """Join several texts into one alternation group, e.g. ``Class|Klasse|Interface``."""
    if not texts:
        raise ValueError("alt_of needs at least one text")
    return "(?:" + "|".join(text.alt for text in texts) + ")"
```

Notes for the implementer:

- `Text.alt` de-duplicates case-insensitively when `fold` is set and sorts longest first;
  `sorted` is stable, so equal lengths keep the declared order.
- `re.escape` escapes spaces (`Anzahl\ Treffer`), exactly like today's `bilingual_pattern`.
- `(?i:…)` scopes the case flag, so `alt` embeds into case-sensitive regexes.
- A `str` group value in `Template.search` is a raw regex; a `HasAlt` value contributes its `alt`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --group tests python -m pytest unittests/lang/test_text.py -q`
Expected: all pass.

- [ ] **Step 5: Lint and type check.**

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/lang/text.py unittests/lang/__init__.py unittests/lang/test_text.py
git commit -m "feat(lang): Text, RegexText and Template value types (#1044)"
```

---

### Task 3: Schema, merge modes and the generic merge

Spec §3 and §4. Required fields, no defaults. `MERGE` is a `ClassVar` in each section's own class
body (a class keyword argument is dropped by `@dataclass(slots=True)`).

**Files:**

- Create: `src/sapguimcp/lang/schema.py`
- Test: `unittests/lang/test_schema_merge.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the generic language pack merge (#1044, phase 2a)."""

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from sapguimcp.lang.schema import JobStatus, PopupSection, canonical, merge
from sapguimcp.lang.text import RegexText, Template, Text


@dataclasses.dataclass(frozen=True, slots=True)
class _Toy:
    code: str
    label: Text
    status: Mapping[JobStatus, Text]


def test_merge_concatenates_variants_without_duplicates() -> None:
    assert merge([Text(("Anzeigen", "Display")), Text(("Display",))]) == Text(("Anzeigen", "Display"))


def test_merge_keeps_flags() -> None:
    assert merge([Text(("Alt",), word=True), Text(("Alt",), word=True)]).word


def test_merge_rejects_differing_flags() -> None:
    with pytest.raises(ValueError, match="flags differ"):
        merge([Text(("a",)), Text(("a",), word=True)])


def test_merge_rejects_differing_kinds() -> None:
    with pytest.raises(TypeError, match="cannot merge"):
        merge([Text(("a",)), RegexText(("a",))])


def test_merge_regex_and_templates() -> None:
    assert merge([RegexText(("a.*",)), RegexText(("b.*",))]).patterns == ("a.*", "b.*")
    merged = merge([Template(("{n} anzeigen",)), Template(("Display {n}",))])
    assert merged.variants == ("{n} anzeigen", "Display {n}")


def test_merge_dataclasses_field_by_field() -> None:
    first = _Toy("DE", Text(("Geplant",)), canonical({JobStatus.SCHEDULED: Text(("Geplant",))}))
    second = _Toy(
        "EN",
        Text(("Scheduled",)),
        canonical({JobStatus.SCHEDULED: Text(("Scheduled",)), JobStatus.READY: Text(("Ready",))}),
    )
    merged = merge([first, second])
    assert merged.code == "DE"  # scalars come from the first item
    assert merged.label.variants == ("Geplant", "Scheduled")
    assert isinstance(merged.status, MappingProxyType)
    assert merged.status[JobStatus.SCHEDULED].variants == ("Geplant", "Scheduled")
    assert merged.status[JobStatus.READY].variants == ("Ready",)


def test_merge_needs_items() -> None:
    with pytest.raises(ValueError, match="at least one"):
        merge([])


def test_merge_mode_survives_slots() -> None:
    assert PopupSection.MERGE == "all"
    assert "MERGE" in vars(PopupSection)
    assert "MERGE" not in {field.name for field in dataclasses.fields(PopupSection)}
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/lang/test_schema_merge.py -q`
Expected: `ModuleNotFoundError: No module named 'sapguimcp.lang.schema'`.

- [ ] **Step 3: Implement `src/sapguimcp/lang/schema.py`**

```python
"""The language pack schema: ``LanguagePack``, its sections, canonical enums and the merge (#1044).

Every field is required; no field has a default. A pack that omits a field fails mypy and fails
at import. Packs and merged views share the one type ``LanguagePack``.

Each section declares its merge mode as a ``ClassVar`` named ``MERGE`` in its own class body. A
class keyword argument would not work: ``@dataclass(slots=True)`` re-creates the class and drops
it silently.

- ``session_en``: the session pack, then EN (standard SAP shows untranslated texts in the
  secondary language, usually EN).
- ``all``: every registered pack (popups, status-type inference, session pages, key names must
  work regardless of the session language).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, ClassVar, Literal, TypeVar, cast

from sapguimcp.lang.text import RegexText, Template, Text

MergeMode = Literal["session_en", "all"]
Leaf = Text | RegexText | Template
S = TypeVar("S")


# =============================================================================
# Canonical enums (keys of canonical mappings)
# =============================================================================


class JobStatus(StrEnum):
    """SM37 job status; the values are the normalised status the tools report."""

    SCHEDULED = "Scheduled"
    RELEASED = "Released"
    READY = "Ready"
    ACTIVE = "Active"
    FINISHED = "Finished"
    CANCELED = "Canceled"


class TransportStatus(StrEnum):
    """SE09 request status filter."""

    MODIFIABLE = "Modifiable"
    RELEASED = "Released"


class Visibility(StrEnum):
    """SE24 component visibility."""

    PUBLIC = "Public"
    PROTECTED = "Protected"
    PRIVATE = "Private"


class DumpSection(StrEnum):
    """ST22 dump detail section."""

    WHAT_HAPPENED = "what_happened"
    HOW_TO_CORRECT = "how_to_correct"
    ERROR_ANALYSIS = "error_analysis"


class Key(StrEnum):
    """Canonical keyboard key names, as the desktop key mapping accepts them."""

    CTRL = "Ctrl"
    SHIFT = "Shift"
    ALT = "Alt"
    ENTER = "Enter"
    DELETE = "Delete"


def canonical(entries: Mapping[S, Text]) -> Mapping[S, Text]:
    """Freeze a canonical mapping (enum member -> ``Text``)."""
    return MappingProxyType(dict(entries))


# =============================================================================
# Sections merged across every registered pack
# =============================================================================


@dataclass(frozen=True, slots=True)
class PopupSection:
    """Popup texts. Empty until the popup migration (phase 3) moves them here."""

    MERGE: ClassVar[MergeMode] = "all"


@dataclass(frozen=True, slots=True)
class StatusTypeSection:
    """Keywords that infer a message's type. Empty until the status-bar migration (phase 3)."""

    MERGE: ClassVar[MergeMode] = "all"


@dataclass(frozen=True, slots=True)
class SessionPagesSection:
    """Login, logoff and timeout page texts. Empty until the session-pages migration (phase 3)."""

    MERGE: ClassVar[MergeMode] = "all"


@dataclass(frozen=True, slots=True)
class KeysSection:
    """Localized key names, from ``sap_tools._is_keyboard_shortcut``."""

    MERGE: ClassVar[MergeMode] = "all"
    names: Mapping[Key, Text]


# =============================================================================
# Sections merged as session pack, then EN
# =============================================================================


@dataclass(frozen=True, slots=True)
class CommonSection:
    """Vocabulary shared by several transactions."""

    MERGE: ClassVar[MergeMode] = "session_en"
    display: Text
    not_found: Text
    does_not_exist: Text
    no_entries: Text
    row_select_hint: Text
    user: Text
    program: Text


@dataclass(frozen=True, slots=True)
class Se09Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    status: Mapping[TransportStatus, Text]


@dataclass(frozen=True, slots=True)
class Se11Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    database_table: Text
    data_type: Text
    table_name: Text
    transparent_table: Text
    structure: Text
    short_description: Text
    row_select_full: RegexText
    dictionary_type: RegexText


@dataclass(frozen=True, slots=True)
class Se16Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    hit_count_label: Text
    column_selection: Text
    no_values_found: Text


@dataclass(frozen=True, slots=True)
class Se24Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    class_builder: Text
    initial_screen: Text
    display_title: Template
    object_type: Text
    class_label: Text
    interface_label: Text
    visibility: Mapping[Visibility, Text]
    static: Text
    abstract: Text


@dataclass(frozen=True, slots=True)
class Se37Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    display_title: Template


@dataclass(frozen=True, slots=True)
class Se93Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    dialog_transaction: Text
    report_transaction: Text
    gui_html: Text
    gui_java: Text
    gui_windows: Text
    screen_number: Text
    selection_screen: Text
    start_with_variant: Text
    transaction_code: Text
    transaction_text: Text
    package: Text
    auth_object: Text


@dataclass(frozen=True, slots=True)
class Slg1Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    log_list_screen: Text
    no_logs_found: Text


@dataclass(frozen=True, slots=True)
class Sm30Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    maintain: Text
    table_view: Text
    display_view: Text


@dataclass(frozen=True, slots=True)
class Sm37Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    status: Mapping[JobStatus, Text]


@dataclass(frozen=True, slots=True)
class SproSection:
    MERGE: ClassVar[MergeMode] = "session_en"
    initial_screen: Text
    sap_reference_img: Text
    search_button: Text
    search_dialog: Text
    search_field: Text
    results_dialog: Text
    column_hits: Text
    column_parent: Text
    column_area: Text
    img_heading: Text


@dataclass(frozen=True, slots=True)
class St22Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    section: Mapping[DumpSection, Text]


# =============================================================================
# The pack
# =============================================================================


@dataclass(frozen=True, slots=True)
class LanguagePack:
    """All language-dependent texts of one SAP logon language, or a merged view of several."""

    code: str
    """SAP language key, e.g. ``"DE"``."""
    html_lang: str
    """ISO code the WebGUI page reports in ``<html lang>``, e.g. ``"de"``."""
    logon_dropdown: str
    """Text of the WebGUI logon language dropdown, e.g. ``"Deutsch"``."""
    date_format: str
    """Default date input format as a ``strftime`` pattern (#1043 reads the user's own)."""
    same_as_en: frozenset[str]
    """Field paths whose value deliberately equals EN (checked by the untranslated-field test)."""

    common: CommonSection
    popup: PopupSection
    status_type: StatusTypeSection
    session_pages: SessionPagesSection
    keys: KeysSection
    se09: Se09Section
    se11: Se11Section
    se16: Se16Section
    se24: Se24Section
    se37: Se37Section
    se93: Se93Section
    slg1: Slg1Section
    sm30: Sm30Section
    sm37: Sm37Section
    spro: SproSection
    st22: St22Section


# =============================================================================
# Walking and merging
# =============================================================================


def sections(pack: LanguagePack) -> Iterator[tuple[str, Any]]:
    """``(name, section)`` for every section field of ``pack`` (skips scalar pack fields)."""
    for field in dataclasses.fields(pack):
        value = getattr(pack, field.name)
        if dataclasses.is_dataclass(value):
            yield field.name, value


def iter_leaves(pack: LanguagePack) -> Iterator[tuple[str, Leaf]]:
    """Every text of ``pack`` with its path: ``se16.hit_count_label``, ``sm37.status[Ready]``."""
    for section_name, section in sections(pack):
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            path = f"{section_name}.{field.name}"
            if isinstance(value, Mapping):
                for key, leaf in value.items():
                    yield f"{path}[{key}]", leaf
            else:
                yield path, value


def resolve(pack: LanguagePack, path: str) -> Leaf:
    """The text at ``path`` (as produced by :func:`iter_leaves`); ``KeyError`` if there is none."""
    for leaf_path, leaf in iter_leaves(pack):
        if leaf_path == path:
            return leaf
    raise KeyError(path)


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _merge_leaves(leaves: Sequence[Leaf]) -> Leaf:
    first = leaves[0]
    for other in leaves[1:]:
        if type(other) is not type(first):
            raise TypeError(f"cannot merge {type(first).__name__} with {type(other).__name__}")
    if isinstance(first, Text):
        texts = cast("Sequence[Text]", leaves)
        if any((t.fold, t.word) != (first.fold, first.word) for t in texts):
            raise ValueError(f"Text flags differ: {texts!r}")
        return Text(_unique([v for t in texts for v in t.variants]), fold=first.fold, word=first.word)
    if isinstance(first, RegexText):
        regexes = cast("Sequence[RegexText]", leaves)
        if any(r.fold != first.fold for r in regexes):
            raise ValueError(f"RegexText flags differ: {regexes!r}")
        return RegexText(_unique([p for r in regexes for p in r.patterns]), fold=first.fold)
    templates = cast("Sequence[Template]", leaves)
    if any(t.fold != first.fold for t in templates):
        raise ValueError(f"Template flags differ: {templates!r}")
    return Template(_unique([v for t in templates for v in t.variants]), fold=first.fold)


def merge(items: Sequence[S]) -> S:
    """Field-wise merge of packs or sections, first item first.

    Texts concatenate their variants (de-duplicated, order kept); canonical mappings merge per
    key; nested dataclasses merge field by field; anything else (pack code, ``html_lang``,
    ``same_as_en``, ...) is taken from the first item.
    """
    if not items:
        raise ValueError("merge needs at least one item")
    first = items[0]
    if isinstance(first, Text | RegexText | Template):
        return cast("S", _merge_leaves(cast("Sequence[Leaf]", items)))
    if isinstance(first, Mapping):
        mappings = cast("Sequence[Mapping[object, object]]", items)
        keys = _unique_keys(mappings)
        return cast("S", MappingProxyType({key: merge([m[key] for m in mappings if key in m]) for key in keys}))
    if dataclasses.is_dataclass(first) and not isinstance(first, type):
        values = {
            field.name: merge([getattr(item, field.name) for item in items]) for field in dataclasses.fields(first)
        }
        return cast("S", type(first)(**values))
    return first


def _unique_keys(mappings: Sequence[Mapping[object, object]]) -> list[object]:
    keys: dict[object, None] = {}
    for mapping in mappings:
        keys.update(dict.fromkeys(mapping))
    return list(keys)
```

Notes for the implementer:

- `merge` recurses: leaves concatenate, mappings merge per key (keys in first-seen order), nested
  dataclasses field by field, anything else is taken from the first item. Session views therefore
  keep the session pack's `code`, `html_lang`, `same_as_en`, … .
- Merged mappings are `MappingProxyType` again, so views stay read-only.
- `iter_leaves` / `resolve` define the field-path syntax used by `same_as_en`, the guards, and
  later `sources.py`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --group tests python -m pytest unittests/lang/test_schema_merge.py unittests/lang/test_text.py -q`

- [ ] **Step 5: Lint and type check.**

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/lang/schema.py unittests/lang/test_schema_merge.py
git commit -m "feat(lang): language pack schema with per-section merge modes (#1044)"
```

---

### Task 4: DE and EN packs, invariant texts

Today's `lang.py` content, regrouped (decisions 2–5). Copy the texts exactly as they are in
`_legacy.py`; Task 7's shim test proves it. The one intended change is the SLG1 EN text
(decision 9).

**Files:**

- Create: `src/sapguimcp/lang/de.py`, `src/sapguimcp/lang/en.py`, `src/sapguimcp/lang/invariant.py`
- Test: `unittests/lang/test_packs.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the DE/EN packs and the leaf walk over a pack (#1044, phase 2a)."""

import dataclasses

import pytest

from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.invariant import INVARIANT
from sapguimcp.lang.schema import JobStatus, LanguagePack, iter_leaves, resolve, sections
from sapguimcp.lang.text import Template, Text


def test_packs_carry_their_language() -> None:
    assert (DE.code, DE.html_lang, DE.logon_dropdown) == ("DE", "de", "Deutsch")
    assert (EN.code, EN.html_lang, EN.logon_dropdown) == ("EN", "en", "English")


def test_canonical_mappings_are_read_only() -> None:
    with pytest.raises(TypeError):
        DE.sm37.status[JobStatus.READY] = Text(("x",))  # type: ignore[index]


def test_templates_keep_the_word_order_of_each_language() -> None:
    assert isinstance(DE.se24.display_title, Template)
    match = DE.se24.display_title.search("Klassenpflege: CL_FOO anzeigen", name=r"[A-Z0-9_/]+")
    assert match is not None
    assert match["name"] == "CL_FOO"
    assert EN.se37.display_title.format(name="Z_FM") == "Function Builder: Display Z_FM"


def test_invariant_texts() -> None:
    assert INVARIANT.sm34_hint == Text(("SM34",))


def test_sections_skip_scalar_pack_fields() -> None:
    names = [name for name, _ in sections(DE)]
    assert "code" not in names
    assert names[0] == "common"
    assert len(names) == len(dataclasses.fields(LanguagePack)) - 5


def test_iter_leaves_and_resolve() -> None:
    leaves = dict(iter_leaves(DE))
    assert leaves["se16.hit_count_label"] == Text(("Anzahl Treffer",))
    assert leaves["sm37.status[Ready]"] == Text(("Bereit",))
    assert resolve(DE, "sm37.status[Ready]") == Text(("Bereit",))
    with pytest.raises(KeyError):
        resolve(DE, "se16.missing")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/lang/test_packs.py -q`
Expected: `ModuleNotFoundError: No module named 'sapguimcp.lang.de'`.

- [ ] **Step 3: Implement `src/sapguimcp/lang/de.py`**

```python
"""German language pack (SAP logon language DE)."""

from sapguimcp.lang.schema import (
    CommonSection,
    DumpSection,
    JobStatus,
    Key,
    KeysSection,
    LanguagePack,
    PopupSection,
    Se09Section,
    Se11Section,
    Se16Section,
    Se24Section,
    Se37Section,
    Se93Section,
    SessionPagesSection,
    Slg1Section,
    Sm30Section,
    Sm37Section,
    SproSection,
    St22Section,
    StatusTypeSection,
    TransportStatus,
    Visibility,
    canonical,
)
from sapguimcp.lang.text import RegexText, Template, Text

DE = LanguagePack(
    code="DE",
    html_lang="de",
    logon_dropdown="Deutsch",
    date_format="%d.%m.%Y",
    same_as_en=frozenset({"se24.interface_label", "keys.names[Alt]"}),
    common=CommonSection(
        display=Text(("Anzeigen",)),
        not_found=Text(("nicht gefunden",)),
        does_not_exist=Text(("existiert nicht", "ist noch nicht vorhanden", "nicht vorhanden")),
        no_entries=Text(("Keine Einträge gefunden",)),
        row_select_hint=Text(("Zum Auswählen einer Zeile", "Zum Auswählen")),
        user=Text(("Benutzer",)),
        program=Text(("Programm",)),
    ),
    popup=PopupSection(),
    status_type=StatusTypeSection(),
    session_pages=SessionPagesSection(),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Strg",), word=True),
                Key.SHIFT: Text(("Umschalt",), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Eingabe",), word=True),
                Key.DELETE: Text(("Entf",), word=True),
            }
        ),
    ),
    se09=Se09Section(
        status=canonical(
            {
                TransportStatus.MODIFIABLE: Text(("Änderbar",)),
                TransportStatus.RELEASED: Text(("Freigegeben",)),
            }
        ),
    ),
    se11=Se11Section(
        database_table=Text(("Datenbanktabelle",)),
        data_type=Text(("Datentyp",)),
        table_name=Text(("Tabellenname",)),
        transparent_table=Text(("Transp.Tabelle",)),
        structure=Text(("Struktur",)),
        short_description=Text(("Kurzbeschreibung",)),
        row_select_full=RegexText((r"Zum Auswählen[^\"]*Leertaste\.",)),
        dictionary_type=RegexText(("Dictionary.*Typ",)),
    ),
    se16=Se16Section(
        hit_count_label=Text(("Anzahl Treffer",)),
        column_selection=Text(("Spalte für Zeilenauswahl",)),
        no_values_found=Text(("keine werte gefunden",)),
    ),
    se24=Se24Section(
        class_builder=Text(("Klassenpflege",)),
        initial_screen=Text(("Klassenpflege: Einstieg",)),
        display_title=Template(("Klassenpflege: {name} anzeigen",)),
        object_type=Text(("Objekttyp",)),
        class_label=Text(("Klasse",)),
        interface_label=Text(("Interface",)),
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Öffentlich",)),
                Visibility.PROTECTED: Text(("Geschützt",)),
                Visibility.PRIVATE: Text(("Privat",)),
            }
        ),
        static=Text(("Statisch",)),
        abstract=Text(("Abstrakt",)),
    ),
    se37=Se37Section(
        initial_screen=Text(("Function Builder: Einstieg",)),
        display_title=Template(("Function Builder: {name} anzeigen",)),
    ),
    se93=Se93Section(
        initial_screen=Text(("Transaktionspflege",)),
        dialog_transaction=Text(("Dialogtransaktion",)),
        report_transaction=Text(("Reporttransaktion",)),
        gui_html=Text(("SAP GUI für HTML",)),
        gui_java=Text(("SAP GUI für Java",)),
        gui_windows=Text(("SAP GUI für Windows",)),
        screen_number=Text(("Dynpronummer",)),
        selection_screen=Text(("Selektionsbild",)),
        start_with_variant=Text(("Start mit Variante",)),
        transaction_code=Text(("Transaktionscode",)),
        transaction_text=Text(("Transaktionstext",)),
        package=Text(("Paket",)),
        auth_object=Text(("Berechtigungsobjekt",)),
    ),
    slg1=Slg1Section(
        initial_screen=Text(("Anwendungslog auswerten",)),
        log_list_screen=Text(("Protokolle anzeigen",)),
        no_logs_found=Text(("Es konnte kein Protokoll auf der Datenbank gefunden werden",)),
    ),
    sm30=Sm30Section(
        initial_screen=Text(("Tabellensicht-Pflege",)),
        maintain=Text(("Pflegen",)),
        table_view=Text(("Tabelle/Sicht",)),
        display_view=Text(("Sicht",)),
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Geplant",)),
                JobStatus.RELEASED: Text(("Freigegeben",)),
                JobStatus.READY: Text(("Bereit",)),
                JobStatus.ACTIVE: Text(("Aktiv",)),
                JobStatus.FINISHED: Text(("Fertig",)),
                JobStatus.CANCELED: Text(("Abgebrochen",)),
            }
        ),
    ),
    spro=SproSection(
        initial_screen=Text(("Customizing: Projektbearbeitung",)),
        sap_reference_img=Text(("SAP Referenz-IMG",)),
        search_button=Text(("Suchen (Strg+F)",)),
        search_dialog=Text(("Suche in der Struktur",)),
        search_field=Text(("Suchbegriff",)),
        results_dialog=Text(("Trefferliste zum Suchbegriff",)),
        column_hits=Text(("Gefundene Treffer",)),
        column_parent=Text(("Übergeordneter Knoten",)),
        column_area=Text(("Im Bereich",)),
        img_heading=Text(("IMG anzeigen",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("Was ist geschehen?",)),
                DumpSection.HOW_TO_CORRECT: Text(("Was können Sie tun?",)),
                DumpSection.ERROR_ANALYSIS: Text(("Fehleranalyse",)),
            }
        ),
    ),
)
```

- [ ] **Step 4: Implement `src/sapguimcp/lang/en.py`**

```python
"""English language pack (SAP logon language EN); the fallback merged into every session view."""

from sapguimcp.lang.schema import (
    CommonSection,
    DumpSection,
    JobStatus,
    Key,
    KeysSection,
    LanguagePack,
    PopupSection,
    Se09Section,
    Se11Section,
    Se16Section,
    Se24Section,
    Se37Section,
    Se93Section,
    SessionPagesSection,
    Slg1Section,
    Sm30Section,
    Sm37Section,
    SproSection,
    St22Section,
    StatusTypeSection,
    TransportStatus,
    Visibility,
    canonical,
)
from sapguimcp.lang.text import RegexText, Template, Text

EN = LanguagePack(
    code="EN",
    html_lang="en",
    logon_dropdown="English",
    date_format="%m/%d/%Y",
    same_as_en=frozenset(),
    common=CommonSection(
        display=Text(("Display",)),
        not_found=Text(("not found",)),
        does_not_exist=Text(("does not exist",)),
        no_entries=Text(("No entries found",)),
        row_select_hint=Text(("To select a row", "To select")),
        user=Text(("User",)),
        program=Text(("Program",)),
    ),
    popup=PopupSection(),
    status_type=StatusTypeSection(),
    session_pages=SessionPagesSection(),
    keys=KeysSection(
        names=canonical(
            {
                Key.CTRL: Text(("Ctrl",), word=True),
                Key.SHIFT: Text(("Shift",), word=True),
                Key.ALT: Text(("Alt",), word=True),
                Key.ENTER: Text(("Enter",), word=True),
                Key.DELETE: Text(("Delete",), word=True),
            }
        ),
    ),
    se09=Se09Section(
        status=canonical(
            {
                TransportStatus.MODIFIABLE: Text(("Modifiable",)),
                TransportStatus.RELEASED: Text(("Released",)),
            }
        ),
    ),
    se11=Se11Section(
        database_table=Text(("Database table",)),
        data_type=Text(("Data type",)),
        table_name=Text(("Table name",)),
        transparent_table=Text(("Transparent Table",)),
        structure=Text(("Structure",)),
        short_description=Text(("Short Description",)),
        row_select_full=RegexText((r"To select a row, press the space bar\.",)),
        dictionary_type=RegexText(("Dictionary.*type",)),
    ),
    se16=Se16Section(
        hit_count_label=Text(("Number of Hits",)),
        column_selection=Text(("Column for row selection",)),
        no_values_found=Text(("no values found",)),
    ),
    se24=Se24Section(
        class_builder=Text(("Class Builder",)),
        initial_screen=Text(("Class Builder: Initial",)),
        display_title=Template(("Class Builder: Display {name}",)),
        object_type=Text(("Object Type",)),
        class_label=Text(("Class",)),
        interface_label=Text(("Interface",)),
        visibility=canonical(
            {
                Visibility.PUBLIC: Text(("Public",)),
                Visibility.PROTECTED: Text(("Protected",)),
                Visibility.PRIVATE: Text(("Private",)),
            }
        ),
        static=Text(("Static",)),
        abstract=Text(("Abstract",)),
    ),
    se37=Se37Section(
        initial_screen=Text(("Function Builder: Initial Screen",)),
        display_title=Template(("Function Builder: Display {name}",)),
    ),
    se93=Se93Section(
        initial_screen=Text(("Transaction Maintenance",)),
        dialog_transaction=Text(("Dialog Transaction",)),
        report_transaction=Text(("Report Transaction",)),
        gui_html=Text(("SAP GUI for HTML",)),
        gui_java=Text(("SAP GUI for Java",)),
        gui_windows=Text(("SAP GUI for Windows",)),
        screen_number=Text(("Screen number",)),
        selection_screen=Text(("Selection screen",)),
        start_with_variant=Text(("Start with variant",)),
        transaction_code=Text(("Transaction code",)),
        transaction_text=Text(("Transaction text",)),
        package=Text(("Package",)),
        auth_object=Text(("Authorization object",)),
    ),
    slg1=Slg1Section(
        initial_screen=Text(("Analyze Application Log",)),
        log_list_screen=Text(("Display Logs",)),
        # BL 208 in EN. The second variant is the text lang.py expected before #1044; kept until
        # the SLG1 migration confirms no release shows it.
        no_logs_found=Text(("No log found in the database", "No log could be found in the database")),
    ),
    sm30=Sm30Section(
        initial_screen=Text(("Table View Maintenance",)),
        maintain=Text(("Maintain",)),
        table_view=Text(("Table/View",)),
        display_view=Text(("View",)),
    ),
    sm37=Sm37Section(
        status=canonical(
            {
                JobStatus.SCHEDULED: Text(("Scheduled",)),
                JobStatus.RELEASED: Text(("Released",)),
                JobStatus.READY: Text(("Ready",)),
                JobStatus.ACTIVE: Text(("Active",)),
                JobStatus.FINISHED: Text(("Finished",)),
                JobStatus.CANCELED: Text(("Canceled",)),
            }
        ),
    ),
    spro=SproSection(
        initial_screen=Text(("Customizing: Execute Project",)),
        sap_reference_img=Text(("SAP Reference IMG",)),
        search_button=Text(("Find (Ctrl+F)",)),
        search_dialog=Text(("Search in the structure",)),
        search_field=Text(("Search Term",)),
        results_dialog=Text(("Hit List",)),
        column_hits=Text(("Hits",)),
        column_parent=Text(("Parent Node",)),
        column_area=Text(("In area",)),
        img_heading=Text(("Display IMG",)),
    ),
    st22=St22Section(
        section=canonical(
            {
                DumpSection.WHAT_HAPPENED: Text(("What happened?",)),
                DumpSection.HOW_TO_CORRECT: Text(("How to Correct the Error",)),
                DumpSection.ERROR_ANALYSIS: Text(("Error Analysis",)),
            }
        ),
    ),
)
```

- [ ] **Step 5: Implement `src/sapguimcp/lang/invariant.py`**

```python
"""Texts that are the same in every SAP logon language (#1044).

Only text that is fixed regardless of the logon language belongs here: transaction codes in
messages, abapGit's English-only UI, the output of our own Z report. SAP-translated texts that
merely coincide in DE and EN (``Interface``) stay in the packs, because a third language may
differ. Fields are added by the phase-3 migrations.
"""

from dataclasses import dataclass

from sapguimcp.lang.text import Text


@dataclass(frozen=True, slots=True)
class Invariant:
    """Language-independent texts, available in every session via ``lang.invariant()``."""

    sm34_hint: Text
    """SM30 points to SM34 for view clusters; the transaction code is not translated."""


INVARIANT = Invariant(
    sm34_hint=Text(("SM34",)),
)
```

- [ ] **Step 6: Run to verify they pass**

Run: `uv run --group tests python -m pytest unittests/lang/test_packs.py unittests/lang/test_schema_merge.py -q`

- [ ] **Step 7: Lint and type check.**

- [ ] **Step 8: Commit**

```bash
git add src/sapguimcp/lang/de.py src/sapguimcp/lang/en.py src/sapguimcp/lang/invariant.py unittests/lang/test_packs.py
git commit -m "feat(lang): DE and EN language packs from the lang.py texts (#1044)"
```

---

### Task 5: Registry and accessors

Spec §4–§6. `lang/` must not import `sapguimcp.models.config` (the config imports from here).
`session_language` imports only `sapguimcp.utils` at module level, so importing it is safe.

**Files:**

- Modify (replace): `src/sapguimcp/lang/__init__.py`
- Test: `unittests/lang/test_registry.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for the language pack registry and accessors (#1044, phase 2a)."""

import subprocess
import sys

import pytest

from sapguimcp import lang
from sapguimcp.lang import UnsupportedLanguageError
from sapguimcp.lang.de import DE
from sapguimcp.lang.schema import Key
from sapguimcp.session_language import current_language


def test_supported_languages_in_registration_order() -> None:
    assert lang.supported_languages() == ("DE", "EN")


def test_pack_for_normalizes_the_code() -> None:
    assert lang.pack_for(" de ") is DE


def test_pack_for_an_unknown_language() -> None:
    with pytest.raises(UnsupportedLanguageError, match="supported: DE, EN") as excinfo:
        lang.pack_for("IT")
    assert excinfo.value.language == "IT"
    assert excinfo.value.supported == ("DE", "EN")


def test_use_sets_the_session_language() -> None:
    with lang.use("de"):
        assert current_language() == "DE"
    assert current_language() is None


def test_current_merges_the_session_pack_with_en() -> None:
    with lang.use("DE"):
        view = lang.current()
    assert view.code == "DE"
    assert view.same_as_en == DE.same_as_en
    assert view.se16.hit_count_label.variants == ("Anzahl Treffer", "Number of Hits")


def test_current_for_en_has_only_en() -> None:
    with lang.use("EN"):
        assert lang.current().se16.hit_count_label.variants == ("Number of Hits",)


def test_current_is_cached() -> None:
    with lang.use("DE"):
        assert lang.current() is lang.current()


def test_all_sections_in_the_session_view_match_every_language() -> None:
    with lang.use("EN"):
        assert lang.current().keys.names[Key.CTRL].variants == ("Ctrl", "Strg")


def test_current_without_a_session_language() -> None:
    with lang.use(None), pytest.raises(UnsupportedLanguageError, match="none is known"):
        lang.current("SE24 lookup")


def test_current_for_a_language_without_a_pack() -> None:
    with lang.use("IT"), pytest.raises(UnsupportedLanguageError, match="SE24 lookup needs a language pack for IT"):
        lang.current("SE24 lookup")


def test_universal_needs_no_session() -> None:
    with lang.use(None):
        names = lang.universal().keys.names
    assert names[Key.CTRL].variants == ("Strg", "Ctrl")
    assert names[Key.ALT].variants == ("Alt",)
    assert lang.universal() is lang.universal()


def test_invariant_texts() -> None:
    assert lang.invariant().sm34_hint.variants == ("SM34",)


def test_lang_does_not_import_the_config() -> None:
    """``models.config`` imports ``lang``; the reverse would be an import cycle (spec section 1)."""
    code = "import sys, sapguimcp.lang; sys.exit('sapguimcp.models.config' in sys.modules)"
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0  # noqa: S603
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/lang/test_registry.py -q`
Expected: `ImportError: cannot import name 'UnsupportedLanguageError' from 'sapguimcp.lang'`.

- [ ] **Step 3: Replace `src/sapguimcp/lang/__init__.py`**

```python
"""Language packs: every SAP-language-dependent text in one place (#1044).

Public API:

- :func:`current` - the session's merged view (session pack, then EN); raises
  :class:`UnsupportedLanguageError` when the session language has no pack.
- :func:`universal` - the sections that match every registered language (popups, status-type
  inference, session pages, key names), usable without any session.
- :func:`invariant` - texts that are the same in every logon language.
- :func:`use` / :func:`set_session_language` - set the session language (tests, login).
- :func:`pack_for`, :func:`supported_languages` - the registry.

The ``X_DE`` / ``X_EN`` constants and ``bilingual_pattern`` of the former ``lang.py`` module are
re-exported from :mod:`sapguimcp.lang._legacy` until the phase-3 migrations remove their last
importer.

This package must not import ``sapguimcp.models.config``: the config imports
:func:`supported_languages` from here.
"""

from __future__ import annotations

import dataclasses
import functools
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sapguimcp.lang import _legacy
from sapguimcp.lang._legacy import *  # noqa: F403  # re-export of the former lang.py constants
from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.invariant import INVARIANT, Invariant
from sapguimcp.lang.schema import (
    KeysSection,
    LanguagePack,
    PopupSection,
    SessionPagesSection,
    StatusTypeSection,
    merge,
    sections,
)
from sapguimcp.lang.text import HasAlt, RegexText, Template, Text, alt_of
from sapguimcp.session_language import current_language, normalize_language, set_session_language, use_language

if TYPE_CHECKING:
    from collections.abc import Iterator

__all__ = [
    "HasAlt",
    "Invariant",
    "LanguagePack",
    "RegexText",
    "Template",
    "Text",
    "UniversalView",
    "UnsupportedLanguageError",
    "alt_of",
    "current",
    "invariant",
    "pack_for",
    "set_session_language",
    "supported_languages",
    "universal",
    "use",
    "view_for",
]
__all__ += _legacy.__all__

FALLBACK_LANGUAGE = "EN"

_PACKS: dict[str, LanguagePack] = {pack.code: pack for pack in (DE, EN)}
"""Registered packs in registration order (the order of :func:`supported_languages`)."""

_views: dict[str, LanguagePack] = {}
"""Merged session views by language code. Packs hold mappings and are not hashable."""


class UnsupportedLanguageError(RuntimeError):
    """The session's logon language has no language pack."""

    def __init__(self, language: str | None, feature: str) -> None:
        self.language = language
        self.supported = supported_languages()
        supported = ", ".join(self.supported)
        if language is None:
            message = (
                f"{feature} needs the session's logon language, but none is known; "
                f"log in first (supported: {supported})"
            )
        else:
            message = f"{feature} needs a language pack for {language}; supported: {supported}"
        super().__init__(message)


@dataclasses.dataclass(frozen=True, slots=True)
class UniversalView:
    """The ``all`` sections merged over every registered pack, independent of any session."""

    popup: PopupSection
    status_type: StatusTypeSection
    session_pages: SessionPagesSection
    keys: KeysSection


def supported_languages() -> tuple[str, ...]:
    """SAP language keys that have a pack, in registration order (``("DE", "EN")``)."""
    return tuple(_PACKS)


def pack_for(code: str) -> LanguagePack:
    """The registered (unmerged) pack for ``code``; :class:`UnsupportedLanguageError` if none."""
    normalized = normalize_language(code)
    pack = _PACKS.get(normalized) if normalized is not None else None
    if pack is None:
        raise UnsupportedLanguageError(normalized, "this lookup")
    return pack


def _build_view(code: str) -> LanguagePack:
    """Merge each section per its ``MERGE`` mode; scalar pack fields come from the session pack."""
    session = _PACKS[code]
    every = [session, *(pack for pack in _PACKS.values() if pack is not session)]
    session_en = [session] if code == FALLBACK_LANGUAGE else [session, _PACKS[FALLBACK_LANGUAGE]]
    merged = {
        name: merge([getattr(pack, name) for pack in (every if section.MERGE == "all" else session_en)])
        for name, section in sections(session)
    }
    return dataclasses.replace(session, **merged)


def view_for(code: str) -> LanguagePack:
    """The merged view for ``code``: every section merged per its ``MERGE`` mode, cached."""
    pack = pack_for(code)
    view = _views.get(pack.code)
    if view is None:
        view = _views[pack.code] = _build_view(pack.code)
    return view


def current(feature: str = "this tool") -> LanguagePack:
    """The merged view for the current session's language.

    Raises :class:`UnsupportedLanguageError` (naming ``feature``) when no language is known or
    the language has no pack.
    """
    code = current_language()
    if code is None or code not in _PACKS:
        raise UnsupportedLanguageError(code, feature)
    return view_for(code)


@functools.cache
def universal() -> UniversalView:
    """The ``all`` sections merged over every registered pack, in registration order."""
    packs = list(_PACKS.values())
    return UniversalView(
        **{
            field.name: merge([getattr(pack, field.name) for pack in packs])
            for field in dataclasses.fields(UniversalView)
        }
    )


def invariant() -> Invariant:
    """Texts that are the same in every logon language."""
    return INVARIANT


@contextmanager
def use(code: str | None) -> Iterator[None]:
    """Temporarily set the session language: ``with lang.use("DE"): lang.current()``."""
    with use_language(code):
        yield
```

Notes for the implementer:

- Keep the import block as shown. After Task 7, `_legacy` itself imports `lang.de` / `lang.en`;
  they only need `schema` and `text`, so there is no cycle through the half-initialised
  `__init__`.
- `_build_view` uses `dataclasses.replace(session, **merged)`, so every scalar pack field comes
  from the session pack without listing them.
- `current()` checks `code not in _PACKS` itself (rather than calling `pack_for`) so the error names
  the caller's `feature`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --group tests python -m pytest unittests/lang/ -q`

- [ ] **Step 5: Re-run the importers' tests from Task 1 Step 6** (the re-export must still work).

- [ ] **Step 6: Lint and type check.**

- [ ] **Step 7: Commit**

```bash
git add src/sapguimcp/lang/__init__.py unittests/lang/test_registry.py
git commit -m "feat(lang): pack registry with current(), universal() and pack_for() (#1044)"
```

---

### Task 6: Completeness and translation guards

Spec §10, the checks that need no source scanner. These tests pass against correct packs, so the
TDD step is a **mutation check**: break a pack on purpose, see the right test fail, revert.

**Files:**

- Test: `unittests/lang/test_pack_completeness.py`

- [ ] **Step 1: Write the guards**

```python
"""Completeness and translation guards over every registered language pack (#1044, spec section 10).

Phase 2a covers the checks that need no source scanner. The synthetic third language and the
no-literal scanner follow in phase 2b.
"""

import dataclasses
import re
from collections.abc import Mapping
from datetime import date
from enum import StrEnum

import pytest

from sapguimcp import lang
from sapguimcp.lang.schema import (
    DumpSection,
    JobStatus,
    Key,
    LanguagePack,
    Leaf,
    TransportStatus,
    Visibility,
    iter_leaves,
    resolve,
    sections,
)
from sapguimcp.lang.text import RegexText, Template, Text

LANGUAGES = lang.supported_languages()
EN = lang.pack_for("EN")

# Every canonical mapping of the schema and the enum whose members it must cover.
CANONICAL: dict[str, type[StrEnum]] = {
    "keys.names": Key,
    "se09.status": TransportStatus,
    "se24.visibility": Visibility,
    "sm37.status": JobStatus,
    "st22.section": DumpSection,
}

ALL_SECTIONS = {"popup", "status_type", "session_pages", "keys"}


def _packs() -> list[LanguagePack]:
    return [lang.pack_for(code) for code in LANGUAGES]


def _mappings(pack: LanguagePack) -> dict[str, Mapping[StrEnum, Text]]:
    found: dict[str, Mapping[StrEnum, Text]] = {}
    for section_name, section in sections(pack):
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            if isinstance(value, Mapping):
                found[f"{section_name}.{field.name}"] = value
    return found


def _group_names(leaf: Leaf) -> frozenset[str]:
    if isinstance(leaf, Template):
        return leaf.placeholders
    if isinstance(leaf, RegexText):
        return frozenset(name for pattern in leaf.patterns for name in re.compile(pattern).groupindex)
    return frozenset()


@pytest.mark.parametrize("code", LANGUAGES)
def test_pack_scalars(code: str) -> None:
    pack = lang.pack_for(code)
    assert pack.code == code
    assert pack.html_lang == pack.html_lang.lower()
    assert pack.logon_dropdown.strip()
    assert date(2026, 2, 22).strftime(pack.date_format)


def test_html_lang_codes_are_unique() -> None:
    assert len({pack.html_lang for pack in _packs()}) == len(LANGUAGES)


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_leaf_is_a_text_value_with_variants(code: str) -> None:
    for path, leaf in iter_leaves(lang.pack_for(code)):
        assert isinstance(leaf, Text | RegexText | Template), path
        values = leaf.patterns if isinstance(leaf, RegexText) else leaf.variants
        assert values, path
        assert all(value.strip() for value in values), path


@pytest.mark.parametrize("code", LANGUAGES)
def test_every_regex_compiles(code: str) -> None:
    for path, leaf in iter_leaves(lang.pack_for(code)):
        if isinstance(leaf, Template):
            leaf.search("")  # compiles one pattern per variant
        else:
            assert isinstance(leaf.pattern, re.Pattern), path


@pytest.mark.parametrize("code", LANGUAGES)
def test_same_fields_kinds_and_flags_as_en(code: str) -> None:
    pack = dict(iter_leaves(lang.pack_for(code)))
    reference = dict(iter_leaves(EN))
    assert pack.keys() == reference.keys()
    for path, leaf in pack.items():
        other = reference[path]
        assert type(leaf) is type(other), path
        assert leaf.fold == other.fold, path
        assert getattr(leaf, "word", False) == getattr(other, "word", False), path


@pytest.mark.parametrize("code", LANGUAGES)
def test_same_placeholders_and_groups_as_en(code: str) -> None:
    for path, leaf in iter_leaves(lang.pack_for(code)):
        assert _group_names(leaf) == _group_names(resolve(EN, path)), path


def test_merge_modes() -> None:
    section_types = {name: type(section) for name, section in sections(EN)}
    for name, section_type in section_types.items():
        assert "MERGE" in vars(section_type), f"{name}: declare MERGE in the class body"
    assert {name for name, section_type in section_types.items() if section_type.MERGE == "all"} == ALL_SECTIONS
    assert {section_type.MERGE for section_type in section_types.values()} == {"all", "session_en"}


def test_universal_holds_exactly_the_all_sections() -> None:
    assert {field.name for field in dataclasses.fields(lang.UniversalView)} == ALL_SECTIONS


def test_canonical_mappings_are_declared() -> None:
    assert _mappings(EN).keys() == CANONICAL.keys()


@pytest.mark.parametrize("code", LANGUAGES)
def test_canonical_mappings_cover_every_member(code: str) -> None:
    for path, mapping in _mappings(lang.pack_for(code)).items():
        assert set(mapping) == set(CANONICAL[path]), path


def _assert_no_collisions(view_name: str, mappings: dict[str, Mapping[StrEnum, Text]]) -> None:
    for path, mapping in mappings.items():
        owner: dict[str, StrEnum] = {}
        for member, text in mapping.items():
            for variant in text:
                key = variant.lower() if text.fold else variant
                assert owner.setdefault(key, member) == member, (
                    f"{view_name} {path}: {variant!r} maps to {owner[key]} and {member}"
                )


@pytest.mark.parametrize("code", LANGUAGES)
def test_no_variant_maps_to_two_members_in_a_session_view(code: str) -> None:
    with lang.use(code):
        _assert_no_collisions(code, _mappings(lang.current()))


def test_no_variant_maps_to_two_members_in_the_universal_view() -> None:
    _assert_no_collisions("universal", {"keys.names": lang.universal().keys.names})


def test_en_declares_nothing_as_same_as_en() -> None:
    assert EN.same_as_en == frozenset()


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "EN"])
def test_untranslated_fields_are_declared(code: str) -> None:
    """A field equal to EN must be listed in ``same_as_en``, so a copied ``en.py`` fails."""
    pack = lang.pack_for(code)
    equal = {path for path, leaf in iter_leaves(pack) if leaf == resolve(EN, path)}
    assert equal == pack.same_as_en


@pytest.mark.parametrize("code", [code for code in LANGUAGES if code != "EN"])
def test_same_as_en_entries_resolve(code: str) -> None:
    """Stale entries fail: every entry names a field that exists and still equals EN."""
    pack = lang.pack_for(code)
    for path in pack.same_as_en:
        assert resolve(pack, path) == resolve(EN, path), path
```

- [ ] **Step 2: Run** — expected PASS:

Run: `uv run --group tests python -m pytest unittests/lang/test_pack_completeness.py -q`

- [ ] **Step 3: Mutation checks** — apply each edit alone, run the file, confirm the named test
      fails, then `git checkout -- src/sapguimcp/lang/` before the next one:

| Edit                                                                     | Expected failure                                                          |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------- |
| `de.py`: `same_as_en=frozenset()`                                        | `test_untranslated_fields_are_declared[DE]`                               |
| `de.py`: add `"se16.missing"` to `same_as_en`                            | `test_same_as_en_entries_resolve[DE]` (`KeyError`)                        |
| `de.py`: `Key.ALT: Text(("Alt",))` (drop `word=True`)                    | `test_same_fields_kinds_and_flags_as_en[DE]` and the DE `same_as_en` test |
| `de.py`: delete the `JobStatus.CANCELED` entry                           | `test_canonical_mappings_cover_every_member[DE]`                          |
| `de.py`: `JobStatus.READY: Text(("Geplant",))`                           | `test_no_variant_maps_to_two_members_in_a_session_view[DE]`               |
| `de.py`: `display_title=Template(("Klassenpflege: {object} anzeigen",))` | `test_same_placeholders_and_groups_as_en[DE]`                             |
| `schema.py`: `PopupSection.MERGE = "session_en"`                         | `test_merge_modes`                                                        |

Note: a flag mismatch also makes `view_for("DE")` raise in `merge`; that is intended (decision 12).

- [ ] **Step 4: Lint and type check.**

- [ ] **Step 5: Commit**

```bash
git add unittests/lang/test_pack_completeness.py
git commit -m "test(lang): completeness, collision, flag and untranslated-field guards (#1044)"
```

---

### Task 7: Legacy consistency, SM37 maps from the packs, SLG1 text fix

Decisions 1 and 9.

**Files:**

- Modify: `src/sapguimcp/lang/_legacy.py`, `src/sapguimcp/tools/slg1_tools.py`,
  `src/sapguimcp/backend/webgui/parsers/slg1_parser.py`
- Test: `unittests/lang/test_legacy_shim.py` (new), `unittests/test_slg1_desktop_unreadable_list.py`,
  `unittests/webgui/test_slg1_parser.py`

- [ ] **Step 1: Write the failing shim test**

```python
"""The former ``lang.py`` constants stay importable and agree with the packs (#1044, phase 2a).

Every constant maps to the pack field that now holds its text. The test fails when a constant is
added without a mapping, or when a pack text and its constant drift apart.
"""

import pytest

from sapguimcp import lang
from sapguimcp.lang import _legacy
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.text import RegexText, Text

# Constant name without _DE/_EN -> pack field path ("invariant." paths point into lang.invariant()).
LEGACY_PATHS: dict[str, str] = {
    "SE16_HIT_COUNT_LABEL": "se16.hit_count_label",
    "SE16_ROW_SELECT_HINT": "common.row_select_hint",
    "SE16_COLUMN_SELECTION": "se16.column_selection",
    "SE16_NO_ENTRIES": "se16.no_values_found",
    "SE11_DATABASE_TABLE": "se11.database_table",
    "SE11_DATA_TYPE": "se11.data_type",
    "SE11_TABLE_NAME": "se11.table_name",
    "SE11_DISPLAY_BUTTON": "common.display",
    "SE11_TRANSPARENT_TABLE": "se11.transparent_table",
    "SE11_STRUCTURE": "se11.structure",
    "SE11_SHORT_DESC": "se11.short_description",
    "SE11_ROW_SELECT_PREFIX": "common.row_select_hint",
    "SE11_ROW_SELECT_FULL": "se11.row_select_full",
    "SE11_DICTIONARY_TYPE": "se11.dictionary_type",
    "SE11_NOT_EXIST": "common.does_not_exist",
    "SE11_NOT_FOUND": "common.not_found",
    "SE37_INITIAL_SCREEN": "se37.initial_screen",
    "SE37_NOT_EXIST": "common.does_not_exist",
    "SE37_NOT_FOUND": "common.does_not_exist",
    "SE24_CLASS_BUILDER": "se24.class_builder",
    "SE24_OBJECT_TYPE": "se24.object_type",
    "SE24_CLASS": "se24.class_label",
    "SE24_INTERFACE": "se24.interface_label",
    "SE24_PUBLIC": "se24.visibility[Public]",
    "SE24_PRIVATE": "se24.visibility[Private]",
    "SE24_PROTECTED": "se24.visibility[Protected]",
    "SE24_STATIC": "se24.static",
    "SE24_ABSTRACT": "se24.abstract",
    "SE24_INITIAL_SCREEN": "se24.initial_screen",
    "SE24_NOT_FOUND": "common.does_not_exist",
    "SE24_NOT_EXIST": "common.does_not_exist",
    "SE93_DIALOG_TRANSACTION": "se93.dialog_transaction",
    "SE93_REPORT_TRANSACTION": "se93.report_transaction",
    "SE93_INITIAL_SCREEN": "se93.initial_screen",
    "SE93_GUI_HTML": "se93.gui_html",
    "SE93_GUI_JAVA": "se93.gui_java",
    "SE93_GUI_WINDOWS": "se93.gui_windows",
    "SE93_SCREEN_NUMBER": "se93.screen_number",
    "SE93_SELECTION_SCREEN": "se93.selection_screen",
    "SE93_START_WITH_VARIANT": "se93.start_with_variant",
    "SE93_TRANSACTION_CODE": "se93.transaction_code",
    "SE93_TRANSACTION_TEXT": "se93.transaction_text",
    "SE93_PACKAGE": "se93.package",
    "SE93_PROGRAM": "common.program",
    "SE93_AUTH_OBJECT": "se93.auth_object",
    "SLG1_INITIAL_SCREEN": "slg1.initial_screen",
    "SLG1_LOG_LIST_SCREEN": "slg1.log_list_screen",
    "SLG1_NO_LOGS_FOUND": "slg1.no_logs_found",
    "SE09_USER_FIELD": "common.user",
    "SE09_MODIFIABLE": "se09.status[Modifiable]",
    "SE09_RELEASED": "se09.status[Released]",
    "SE09_DISPLAY_BUTTON": "common.display",
    "SM30_DISPLAY_BUTTON": "common.display",
    "SM30_MAINTAIN_BUTTON": "sm30.maintain",
    "SM30_TABLE_VIEW": "sm30.table_view",
    "SM30_INITIAL_SCREEN": "sm30.initial_screen",
    "SM30_NOT_FOUND": "common.does_not_exist",
    "SM30_DISPLAY_VIEW": "sm30.display_view",
    "SM30_USE_SM34": "invariant.sm34_hint",
    "SM30_ROW_SELECT_HINT": "common.row_select_hint",
    "SPRO_INITIAL_SCREEN": "spro.initial_screen",
    "SPRO_SAP_REF_IMG": "spro.sap_reference_img",
    "SPRO_SEARCH_BUTTON": "spro.search_button",
    "SPRO_SEARCH_DIALOG": "spro.search_dialog",
    "SPRO_SEARCH_FIELD": "spro.search_field",
    "SPRO_RESULTS_DIALOG": "spro.results_dialog",
    "SPRO_COL_HITS": "spro.column_hits",
    "SPRO_COL_PARENT": "spro.column_parent",
    "SPRO_COL_AREA": "spro.column_area",
    "SPRO_IMG_HEADING": "spro.img_heading",
    "ST22_WHAT_HAPPENED": "st22.section[what_happened]",
    "ST22_HOW_TO_CORRECT": "st22.section[how_to_correct]",
    "ST22_ERROR_ANALYSIS": "st22.section[error_analysis]",
    "ST22_NO_DUMPS": "common.no_entries",
}

# Constants whose name does not follow BASE_DE / BASE_EN.
IRREGULAR: dict[str, tuple[str, str]] = {
    "SE37_DISPLAY_SUFFIX_DE": ("DE", "common.display"),
    "SE37_DISPLAY_PREFIX_EN": ("EN", "common.display"),
    "SE24_DISPLAY_SUFFIX_DE": ("DE", "common.display"),
    "SE24_DISPLAY_PREFIX_EN": ("EN", "common.display"),
    "SLG1_NO_LOGS_FOUND_EN_LEGACY": ("EN", "slg1.no_logs_found"),
}

NOT_TEXTS = {"bilingual_pattern", "SM37_STATUS_MAP_DE", "SM37_STATUS_MAP_EN"}


def _target(name: str) -> tuple[str, str]:
    if name in IRREGULAR:
        return IRREGULAR[name]
    base, _, code = name.rpartition("_")
    return code, LEGACY_PATHS[base]


def _values(code: str, path: str) -> set[str]:
    if path.startswith("invariant."):
        leaf = getattr(lang.invariant(), path.removeprefix("invariant."))
    else:
        leaf = dict(iter_leaves(lang.pack_for(code)))[path]
    assert isinstance(leaf, Text | RegexText), path
    values = leaf.patterns if isinstance(leaf, RegexText) else leaf.variants
    return {value.lower() for value in values}


TEXT_CONSTANTS = sorted(set(_legacy.__all__) - NOT_TEXTS)


def test_every_constant_is_exported_by_the_package() -> None:
    for name in _legacy.__all__:
        assert getattr(lang, name) is getattr(_legacy, name)


@pytest.mark.parametrize("name", TEXT_CONSTANTS)
def test_constant_is_a_variant_of_its_pack_field(name: str) -> None:
    code, path = _target(name)
    assert getattr(_legacy, name).lower() in _values(code, path)


def test_sm37_status_maps_are_unchanged() -> None:
    assert lang.SM37_STATUS_MAP_DE == {
        "geplant": "Scheduled",
        "freigegeben": "Released",
        "bereit": "Ready",
        "aktiv": "Active",
        "fertig": "Finished",
        "abgebrochen": "Canceled",
    }
    assert lang.SM37_STATUS_MAP_EN == {
        "scheduled": "Scheduled",
        "released": "Released",
        "ready": "Ready",
        "active": "Active",
        "finished": "Finished",
        "canceled": "Canceled",
    }


def test_bilingual_pattern_is_unchanged() -> None:
    assert lang.bilingual_pattern("a.b", "c") == r"(?:a\.b|c)"
    assert lang.bilingual_pattern("a.b", "c", escape=False) == "(?:a.b|c)"


def test_slg1_no_logs_found_en_is_sap_message_bl_208() -> None:
    assert lang.SLG1_NO_LOGS_FOUND_EN == "No log found in the database"
    assert lang.SLG1_NO_LOGS_FOUND_EN_LEGACY == "No log could be found in the database"
```

- [ ] **Step 2: Add the BL 208 text to the SLG1 tests.** In
      `unittests/test_slg1_desktop_unreadable_list.py`, extend the `message` parametrization of
      `test_a_no_logs_status_is_still_an_empty_result`:

```python
    [
        "No application log found",
        "Es konnte kein Protokoll auf der Datenbank gefunden werden",
        "No log found in the database",
        "No log could be found in the database",
    ],
```

In `unittests/webgui/test_slg1_parser.py`, add `from sapguimcp.backend.webgui.types import AriaSnapshot`
to the imports and append to `TestSLG1ScreenDetection`:

```python
    @pytest.mark.parametrize(
        "message",
        [
            "Es konnte kein Protokoll auf der Datenbank gefunden werden",
            "No log found in the database",
            "No log could be found in the database",
        ],
    )
    def test_detect_no_results_from_the_status_bar_text(self, message: str) -> None:
        assert is_slg1_no_results(AriaSnapshot(f'- status "{message}"')) is True
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/lang/test_legacy_shim.py unittests/test_slg1_desktop_unreadable_list.py unittests/webgui/test_slg1_parser.py -q`
Expected failures: `test_slg1_no_logs_found_en_is_sap_message_bl_208` and the new
`"No log found in the database"` cases in both SLG1 files. Every other shim case passes already:
that proves Task 4 copied the texts (the old EN text is the pack's second variant, so
`[SLG1_NO_LOGS_FOUND_EN]` passes before and after).

- [ ] **Step 4: Fix the SLG1 text in `_legacy.py`.** Replace the line
      `SLG1_NO_LOGS_FOUND_EN = "No log could be found in the database"` with:

```python
# SAP message BL 208 in EN (#1044: the former text was hand-typed and drifted).
SLG1_NO_LOGS_FOUND_EN = "No log found in the database"
# The former expectation; still accepted by the SLG1 tool and parser until the SLG1 migration.
SLG1_NO_LOGS_FOUND_EN_LEGACY = "No log could be found in the database"
```

and add `"SLG1_NO_LOGS_FOUND_EN_LEGACY",` to `__all__` right after `"SLG1_NO_LOGS_FOUND_EN",`.

- [ ] **Step 5: Derive the SM37 maps from the packs.** In `_legacy.py`, add below `import re`:

```python
from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
```

and replace the two literal `SM37_STATUS_MAP_DE` / `SM37_STATUS_MAP_EN` dicts (keep the comment
above them) with:

```python
SM37_STATUS_MAP_DE: dict[str, str] = {
    variant.lower(): status.value for status, text in DE.sm37.status.items() for variant in text
}

SM37_STATUS_MAP_EN: dict[str, str] = {
    variant.lower(): status.value for status, text in EN.sm37.status.items() for variant in text
}
```

- [ ] **Step 6: Let the SLG1 consumers accept the legacy text.** In
      `src/sapguimcp/tools/slg1_tools.py`:

```python
from sapguimcp.lang import SLG1_NO_LOGS_FOUND_DE, SLG1_NO_LOGS_FOUND_EN, SLG1_NO_LOGS_FOUND_EN_LEGACY
```

and in the no-logs list add `SLG1_NO_LOGS_FOUND_EN_LEGACY,` after `SLG1_NO_LOGS_FOUND_EN,`.

In `src/sapguimcp/backend/webgui/parsers/slg1_parser.py`, import `SLG1_NO_LOGS_FOUND_EN_LEGACY`
in the existing `from sapguimcp.lang import (...)` block and make `is_slg1_no_results` return:

```python
    return any(
        text.lower() in snapshot_lower
        for text in (SLG1_NO_LOGS_FOUND_DE, SLG1_NO_LOGS_FOUND_EN, SLG1_NO_LOGS_FOUND_EN_LEGACY)
    )
```

- [ ] **Step 7: Run to verify they pass**

Run: `uv run --group tests python -m pytest unittests/lang/ unittests/test_slg1_desktop_unreadable_list.py unittests/webgui/test_slg1_parser.py unittests/webgui/test_sm37_parser.py unittests/test_sm37_desktop_empty_result.py -q`

- [ ] **Step 8: Re-run Task 1 Step 5** (value comparison). Expected now: the assertion lists exactly
      `['SLG1_NO_LOGS_FOUND_EN']`; that is the intended fix. Everything else is unchanged.

- [ ] **Step 9: Lint and type check.**

- [ ] **Step 10: Commit**

```bash
git add src/sapguimcp/lang/_legacy.py src/sapguimcp/tools/slg1_tools.py src/sapguimcp/backend/webgui/parsers/slg1_parser.py unittests/lang/test_legacy_shim.py unittests/test_slg1_desktop_unreadable_list.py unittests/webgui/test_slg1_parser.py
git commit -m "fix(slg1): expect SAP's EN text for 'no log found' (BL 208); legacy constants checked against the packs (#1044)"
```

---

### Task 8: `SUPPORTED_LANGUAGES` from the language packs

Spec §6, building on #1042: a new pack becomes an accepted `systems.json` language at once.

**Files:**

- Modify: `src/sapguimcp/models/config.py`
- Test: `unittests/test_sap_config_languages.py`

- [ ] **Step 1: Update the tests.** In `unittests/test_sap_config_languages.py`, add
      `from sapguimcp import lang` and `from sapguimcp.lang import supported_languages` to the
      imports and replace `test_supported_languages_derive_from_sap_language_literal` with:

```python
def test_supported_languages_come_from_the_language_packs() -> None:
    assert config_module.SUPPORTED_LANGUAGES == supported_languages() == ("DE", "EN")


def test_sap_language_literal_matches_the_packs() -> None:
    """``utils.SapLanguage`` types date formatting until phase 3 retires it; it must not drift."""
    assert set(get_args(SapLanguage)) == set(supported_languages())


def test_config_accepts_every_registered_pack_language(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []

    def fake_load(*, supported_languages: tuple[str, ...]) -> object:
        seen.append(supported_languages)
        return object()

    monkeypatch.setattr(config_module, "_sap_config", None)
    monkeypatch.setattr(config_module, "load_sap_config", fake_load)
    monkeypatch.setitem(lang._PACKS, "XX", lang.pack_for("EN"))  # pylint: disable=protected-access
    config_module.get_sap_config()
    assert seen == [("DE", "EN", "XX")]
```

- [ ] **Step 2: Run to verify the last test fails**

Run: `uv run --group tests python -m pytest unittests/test_sap_config_languages.py -q`
Expected: `test_config_accepts_every_registered_pack_language` fails with
`[('DE', 'EN')] == [('DE', 'EN', 'XX')]`; the others pass.

- [ ] **Step 3: Implement.** In `src/sapguimcp/models/config.py`:
    - change `from typing import Literal, Optional, get_args` to `from typing import Literal, Optional`;
    - replace `from sapguimcp.utils import SapLanguage` with `from sapguimcp.lang import supported_languages`;
    - replace the `SUPPORTED_LANGUAGES` block with:

```python
# Login languages this server can drive: one per registered language pack (#1044), so a new
# pack is accepted in systems.json at once. ``utils.SapLanguage`` must list the same codes until
# the phase-3 migrations retire it (checked by unittests/test_sap_config_languages.py).
SUPPORTED_LANGUAGES: tuple[str, ...] = supported_languages()
```

- in `get_sap_config`, read the registry at load time and update the docstring's first sentence:

```python
    A system whose ``language`` has no language pack (``lang.supported_languages()``) makes this
```

```python
        _sap_config = load_sap_config(supported_languages=supported_languages())
```

- [ ] **Step 4: Run** — expected PASS:

`uv run --group tests python -m pytest unittests/test_sap_config_languages.py unittests/test_config.py unittests/test_config_error_classification.py unittests/test_utils.py unittests/test_session_language.py unittests/test_tools_session_language.py unittests/lang/test_registry.py -q`

`test_registry.py::test_lang_does_not_import_the_config` is the cycle guard; also run
`uv run python -c "import sapguimcp.models.config, sapguimcp.server"` (the server import pulls
the whole tool graph).

- [ ] **Step 5: Lint and type check.**

- [ ] **Step 6: Commit**

```bash
git add src/sapguimcp/models/config.py unittests/test_sap_config_languages.py
git commit -m "feat(config): supported logon languages come from the language packs (#1044)"
```

---

### Task 9: Final verification (controller)

- [ ] Lint and type check on the whole repo (commands in the testing rules).
- [ ] All unit tests touched by 2a, by path:

```bash
uv run --group tests python -m pytest unittests/lang/ unittests/test_sap_config_languages.py unittests/test_config.py unittests/test_config_error_classification.py unittests/test_utils.py unittests/test_session_language.py unittests/test_tools_session_language.py unittests/test_slg1_desktop_unreadable_list.py unittests/test_sm37_desktop_empty_result.py unittests/test_spro_scope_note.py unittests/test_se09_label_parsing.py unittests/test_se11_readiness.py unittests/webgui/test_se09_parser.py unittests/webgui/test_se11_parser.py unittests/webgui/test_se16_parser.py unittests/webgui/test_se24_parser.py unittests/webgui/test_se37_parser.py unittests/webgui/test_se93_parser.py unittests/webgui/test_slg1_parser.py unittests/webgui/test_sm30_parser.py unittests/webgui/test_sm37_parser.py unittests/webgui/test_spro_parser.py unittests/webgui/test_st22_parser.py -q
```

- [ ] Value comparison against `main` (Task 1 Step 5 with `git show main:src/sapguimcp/lang.py`):
      only `SLG1_NO_LOGS_FOUND_EN` differs.
- [ ] `git grep -n "sapguimcp/lang.py\|lang\.py" -- src unittests` lists only the docstrings that
      name the former module on purpose (`_legacy.py`, `unittests/webgui/testdata/lang_test.py`,
      which 2b rewrites).
- [ ] Leak check of the diff before pushing (CLAUDE.md): grep for an internal domain suffix, a
      `<SID>K9…` transport number and a `/XXX/` namespace prefix.
- [ ] **Live tests** (controller only, single SAP connection, one at a time). 2a changes runtime
      behaviour only in the SLG1 no-logs check and the config's language list:
    - Desktop, on both systems, in the configured language:
      `uv run --group tests python -m pytest unittests/desktop/test_slg1_integration.py unittests/desktop/test_session_language_integration.py -q`
    - WebGUI, if its environment is available: `unittests/webgui/test_slg1_integration.py`;
      otherwise say in the PR that it was not run and why.
    - Record the literal pytest summaries; rerun a failure on its own and compare with `main`
      before calling it real (flaky-test rule in the spec). Explain every skip.
- [ ] Continue with the branch's PR workflow (self-review, Copilot review, CI green, ask before
      merging).
