# Language Pack Guards and Test Pack Implementation Plan (phase 2b of #1044)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The guards of spec §10 that phase 2a left out exist and pass on today's code: a
registration helper for test packs, a synthetic third language that runs through the registry and
every 2a guard, the WebGUI test pack replacing `lang_test.py` / `lang_strings`, and the no-literal
scanner `unittests/test_no_ui_literals.py` with a seeded, shrink-only `unittests/lang_baseline.json`.
After this phase a phase-3 migration PR only deletes baseline entries, and any new SAP UI literal
outside `lang/` fails the unit tests.

**Architecture:** `sapguimcp.lang._register_for_tests(pack)` is a context manager that adds a pack
to the module-level `_PACKS` registry and clears the merged-view caches (`_views`,
`universal.cache_clear()`) on enter and exit. `unittests/lang/synthetic_pack.py` derives a complete
pack `XX` from EN by prefixing every text with the marker `⟦XX⟧ `, so phase-3 schema growth needs
no edit there. The WebGUI test pack is a small frozen-dataclass schema of `Text` fields in
`unittests/webgui/testdata/lang_test.py` with its own completeness test. The scanner is one
self-contained pytest module: an AST pass for Python (sink rule, value rule, skips), a small
tokenizer for JavaScript files and for JS functions held in Python strings, a file + literal ->
count baseline, and the `lang-ok` comment exemption.

**Tech Stack:** Python 3.11+, `ast`, `tokenize`, `re`, frozen slotted dataclasses, pytest.

Spec: `docs/superpowers/specs/2026-11-10-language-packs-design.md` §10 (guard tests, "Language in
the test suite"), "Today's ways" row 13, §11 step 2. Phase 2a (`docs/superpowers/plans/2026-11-11-language-packs-core.md`)
is merged to `main` before this plan starts; Task 0 checks that.

**Not in 2b** (unchanged from the 2a split):

- **2c:** `sources.py`, `harvest_lang_texts.py`, `Text.for_js()` / `RegexText.for_js()` and the JS
  object-argument convention, and the `html_lang` -> SAP language key lookup.
- **Phase 3:** moving any literal into a pack. 2b changes no runtime behaviour: the only `src/`
  edits are the test-only registration helper and `lang-ok` comments.
- **Phase 4:** the pseudo-locale test and the `ARCHITECTURE.md` / `CONTRIBUTING.md` rule.

## Scanner prototype: measured on today's code

Run before writing this plan, on a copy of the phase-2a branch head (`7293c0d`) outside the
repository, with exactly the code embedded in Tasks 3 and 4.

| Measure                                              | Value                                                                                                                                         |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Files scanned                                        | 161 (140 Python outside `lang/`, 21 JS)                                                                                                       |
| Scan time (incl. importing `sapguimcp.lang`)         | 0.8-0.9 s                                                                                                                                     |
| Whole test module (45 tests), pytest-reported / wall | 1.0-1.1 s / 1.8 s                                                                                                                             |
| Determinism                                          | identical hits, lines and counts (SHA-256 of the dump) on CPython 3.11.15, 3.13.13, 3.14.4, 3.15.0a8                                          |
| Hits before exemptions                               | 344 hits, 266 distinct file + literal, 36 files                                                                                               |
| Hits per rule                                        | value 108, compare 104, sink-call 41, row-key 34, js-method 31, selector 9, js-array 5, js-selector 5, js-equality 3, sink-keyword 2, regex 2 |
| False positives                                      | 37 hits (10.8 %): 15 get `lang-ok` (13 lines, 8 files), 22 stay on the baseline (mixed lines, `breakpoint_tools.py`)                          |
| Detected entries after `lang-ok`                     | 257 in 31 files (329 hits)                                                                                                                    |
| Sweep candidates (`sweep_candidates.py`)             | 231: 155 from the German heuristic (the prototype kept 150, dropping 5 of the server's own messages) and 76 from the loose value match        |
| Seeded baseline (with the 150 reviewed candidates)   | 407 entries (559 literal occurrences) in 33 files; `breakpoint_tools.py` 26 entries                                                           |
| Source lines covered (hits + sweep)                  | 312 lines in 35 files, 15 of them in `breakpoint_tools.py`                                                                                    |

The spec estimated ~175 sites in 34 files plus ~10 in `breakpoint_tools.py`. The scanner counts
lines and literals, where the spec counted checks (one check often spans several lines and a DE
and an EN literal), so the larger number is expected; the file count matches.

**How the rules were tuned.** A first prototype that applied §10 literally (value rule as a plain
case-folded substring, no filters) produced 862 hits / 676 distinct literals, 493 of them from the
value rule and mostly false: the server's own messages ("Field not found: "), `center` containing
the key name `enter`, identifiers like `program_name` and `SEOCLASS-CLSNAME`, CSS selectors like
`[class*='lsPopupWindow']`. The deviations in decision 6 brought that to 344 hits with 37 false
positives. Diffing the two hit lists shows the price: a handful of true hits the naive version found
by accident are gone (lower-case single words such as `aktiviert` / `inaktiv`, `inaktive objekte`,
`bereits angemeldet`, and a long regex alternation in `backend/webgui/backend.py`). The sweep
helper's second heuristic lists exactly that class again, so the seed still covers them.

**Known false negatives** (why the baseline is seeded from a sweep, spec §10): module-level tuples of
lower-case fragments (`_ACTIVATION_CONFIRMED = ("aktiviert", "activated")`), lower-case checks
against variables whose names do not look like screen text, English-only literals without a German
sibling, and regex constants used far from their definition. The sweep in Task 4 covers today's
code; the phase-4 pseudo-locale test covers regressions.

## Decisions made while planning

1. **The registration helper** is `sapguimcp.lang._register_for_tests(pack)`, a context manager
   yielding the pack. It refuses a code that is already registered (replacing DE or EN would leak
   into other tests) and a code that is not upper-case and stripped. It clears `_views` and
   `universal.cache_clear()` on enter and on exit, also when the block raises. It stays out of
   `__all__`; tests import it by name.
2. **The synthetic language is derived, not hand-written.** `synthetic_pack()` walks the EN pack
   and prefixes every `Text` / `Template` variant with `⟦XX⟧ ` and every `RegexText` pattern with
   the escaped marker plus a group (so `a|b` keeps the marker on both branches). It keeps the kind,
   the flags and the placeholders, and keeps one field identical to EN (`keys.names[Alt]`, listed
   in `same_as_en`) so the untranslated-field guards run on a real entry. Code `XX`, `html_lang`
   `xx`. Fields that phase 3 adds to the schema appear in it automatically.
3. **The 2a guards are reused, not copied:** `test_synthetic_language.py` imports the `_check_*`
   helpers and `_mappings` from `unittests/lang/test_pack_completeness.py` (2a decision 14).
   `unittests/test_sap_config_languages.py` stops monkeypatching `lang._PACKS` and uses the helper
   with the synthetic pack (2a decision 13 said 2b replaces it).
4. **The test pack keeps its file.** `unittests/webgui/testdata/lang_test.py` is rewritten in place
   as a schema (`BpTexts`, `Sm30Texts`, `Se38Texts`, `ButtonTexts`, `UiTestPack`) with `TEST_DE`,
   `TEST_EN` and `UI_TEST_PACKS`; every value is a `Text`, `same_as_en` lists `buttons.ok`. No name
   in it starts with `Test`/`test`: the file matches pytest's default `*_test.py` collection
   pattern. `unittests/webgui/test_lang_test_pack.py` checks one test pack per registered
   language, same fields, kinds and flags, and the untranslated fields.
5. **Fixtures:** `lang_strings` (a `dict[str, str]`) becomes `ui_texts` (the `UiTestPack`). The
   `sap_language` fixture keeps its behaviour, default DE and DE for a value without a pack, with the
   list from `supported_languages()` (`resolve_sap_language()` in `lang_test.py`). The six consumers
   (five snapshot unit tests in `test_selectors.py`, one live test in `test_popup_integration.py`)
   switch to `ui_texts`; the live test builds the same selector string as before (first variant),
   the snapshot tests use `Text.contains`, which is case-insensitive. Yes/No are `word=True`, so
   "No" does not match inside "Note".
6. **Scanner deviations from the letter of §10** (each one measured in the prototype):
    - a. The value rule matches pack variants as **whole words** (`(?<!\w)…(?!\w)`), not as plain
      substrings.
    - b. The value rule ignores the `keys` section: `Enter`, `Delete`, `Escape` are the
      `press_key` API, not screen text.
    - c. The value rule skips the server's own messages (f-string parts, `raise` arguments,
      `error=` / `message=` / `hint=` / ... values, `{"error": ...}` dict values,
      `.get("error", default)`), identifiers (`active`, `data-program`, Windows paths), CSS selectors
      and literals of more than six words. The sink rule still applies to all of them.
    - d. All rules drop literals that are code: no letters, one character, `snake_case`, words
      that are all ALL CAPS, or only lower-case DOM / ARIA / JS vocabulary (`button`, `hidden`,
      `row`, ...). `Table` (capitalised) stays a hit.
    - e. The row-key rule counts only literals that start with a capital letter (SAP column
      headers); `row["time"]` on our own dicts is not a hit.
    - f. `name=` is a sink only in `get_by_role`; local helpers matching
      `bilingual|^_?click_\w*(button|tab)|^find_button` are sinks, and the keys of a dict passed to
      a sink (`fill_form({...})`, `bilingual_target(checkboxes_de={...})`) are sink literals.
    - g. A Python string that holds a JS function (`"() => {...}"`) is scanned with the JS rule,
      as spec §8 asks for inline JS.
7. **The baseline stores counts:** `{file: {literal: count}}`, where `count` is the number of
   (not skipped, not `lang-ok`) literals with exactly that value in the file. A second occurrence of
   an already baselined literal therefore fails as a new site, and a phase-3 PR that removes one of
   two occurrences lowers the count. Keyed by file + literal, never by line, as the spec says.
8. **`lang-ok` is line-scoped:** `# lang-ok: <reason>` (JS: `// lang-ok: <reason>`) on any line of
   a literal exempts every literal on that line, and a bare `lang-ok` without a reason exempts
   nothing and fails `test_every_lang_ok_names_a_reason`. Therefore a false positive that shares a
   line with real screen text goes on the baseline, not behind `lang-ok` (SE09 / SM37 tool
   parameter values next to checkbox labels). Phase 3 adds the `lang-ok` when the screen text
   leaves that line.
9. **Only `--prune` is committed.** `python unittests/test_no_ui_literals.py --prune` lowers counts
   and deletes zero entries, never adds one. The seed, sweep and marking scripts are one-off and
   live outside the repository, so nobody can regenerate the baseline wholesale. Shrink-only is
   enforced by the count check plus review: after Task 4, every diff of `lang_baseline.json` must
   consist of removals only (see "Consequences for phase 3" for the one exception).
10. **No timing assertion.** The scanner takes about 1 s; a wall-clock assertion would be the
    flakiest test in CI. Task 5 records the measured time in the PR instead.
11. **`breakpoint_tools.py` is not edited**, not even a `lang-ok` comment: all its hits, true or
    false, are baseline entries, and `test_breakpoint_tools_stays_on_the_baseline` keeps it there.
12. **No live tests in this plan.** 2b changes no runtime path (a test-only helper, comments, test
    files). The one live test it edits (`test_popup_integration.py`) builds a byte-identical
    selector; Task 5 checks that it still collects (`--collect-only` starts no SAP session).
13. **Model assignment** follows the controller's rule for this phase (haiku for mechanical work,
    sonnet by default, opus for the scanner). The spec's table proposed an opus review for the
    synthetic-language guards too; this plan uses sonnet there because the code below was run and
    verified. Escalate per the spec rule if a review finds a design problem.

## Consequences for phase 3 (read before planning it)

- **A migration PR deletes baseline entries.** Move the texts into the pack, then run
  `uv run python unittests/test_no_ui_literals.py --prune` and commit the shrunken
  `lang_baseline.json` with the migration. The scanner then proves that the area has no literal
  left. Never re-seed.
- **The one allowed addition.** The value rule reads the packs. A PR that adds pack variants can
  make the scanner flag a literal in a file outside the PR's area that the seed sweep missed. Move
  that literal too, or, if that is out of scope, add that single entry with a sentence in the PR
  description. Any other growth of the baseline is a review finding.
- **False positives that phase 3 frees.** The SE09 and SM37 tool-parameter literals (`all`,
  `modifiable`, `released`, `scheduled`, ...) are on the baseline only because they share lines with
  checkbox labels. When the labels move into the pack, mark the remaining parameter checks
  `# lang-ok: tool parameter value` and delete the entries.
- **`lang-ok` exempts the whole line.** Never put it on a line that still holds screen text; split
  the line or keep the entry.
- **New sinks need no scanner change** when they take a `Text` (the shared `click_tab` /
  `set_checkbox` of the spec): a literal passed to them is still flagged because `click_tab`,
  `set_checkbox`, ... are sink names. A new helper with another naming scheme belongs in
  `SINK_CALLS` / `SINK_CALL_PATTERN` in the same PR.
- **Register test packs with `_register_for_tests`.** Never patch `lang._PACKS`; the merged views
  would keep the patched pack.
- **The synthetic pack follows the schema.** New sections and fields need no edit in
  `synthetic_pack.py`; a new text kind would need a branch in `mark()`.
- **Test-only texts go into the test pack** (`UiTestPack`), with DE and EN at once; the
  completeness test fails otherwise. Live tests that still branch on
  `os.environ["SAP_LANGUAGE"] == "DE"` (`test_bp_integration.py`, `test_navigation_integration.py`,
  ...) are outside 2b; an area migration that touches them moves their texts into the test pack.
- **2c's `for_js()`** moves the JS literals into Python arguments; the JS baseline entries then go
  the same way as the Python ones.
- **Phase 4's pseudo-locale test** becomes possible once the baseline is nearly empty; it is the
  net for the scanner's known false negatives listed above.

## Testing rules (read before running anything)

- Run unit tests **by explicit path** (`uv run --group tests python -m pytest unittests/<file> -q`).
  Never run the whole suite, never `-m integration`, never a live test. Collecting a live test
  module with `--collect-only` is allowed (it opens no SAP session).
- **Lint and type check** at the end of every task (from `CONTRIBUTING.md`):
  `uv run --group linting ruff check .`, `uv run --group linting ruff format --check .`,
  `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`. Tasks that touch JS
  also run `npx prettier --check "src/**/*.js"`; on a Windows checkout with CRLF line endings,
  prettier reports every file, so compare against an untouched file or check the LF content.
- One-off scripts (Tasks 3 and 4) go into a temporary directory **outside the repository**
  (`mktemp -d`), are run from the repository root, and are never committed.
- Commit with explicit `git add <paths>`; `git commit -a` skips new files.

## File structure

| File                                                  | Responsibility                                                                            |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Modify `src/sapguimcp/lang/__init__.py`               | `_clear_caches()`, `_register_for_tests(pack)`                                            |
| Create `unittests/lang/synthetic_pack.py`             | `synthetic_pack()`, `mark()`, `CODE`, `MARK`                                              |
| Create `unittests/lang/test_synthetic_language.py`    | helper, every 2a guard, N-language merge, group naming, flags, `UnsupportedLanguageError` |
| Modify `unittests/test_sap_config_languages.py`       | the helper instead of patching `lang._PACKS`                                              |
| Rewrite `unittests/webgui/testdata/lang_test.py`      | the WebGUI test pack and `resolve_sap_language()`                                         |
| Create `unittests/webgui/test_lang_test_pack.py`      | completeness of the test pack, `SAP_LANGUAGE` resolution                                  |
| Modify `unittests/webgui/conftest.py`                 | `sap_language` from the packs, `ui_texts` replaces `lang_strings`                         |
| Modify `unittests/webgui/test_selectors.py`           | five snapshot tests use `ui_texts`                                                        |
| Modify `unittests/webgui/test_popup_integration.py`   | one live test uses `ui_texts` (same selector)                                             |
| Create `unittests/test_no_ui_literals.py`             | the scanner, its rule tests, the baseline guard and `--prune`                             |
| Create `unittests/lang_baseline.json`                 | the seeded, shrink-only baseline                                                          |
| Modify 8 files under `src/sapguimcp/` (comments only) | `lang-ok` on 13 false-positive lines (Task 4)                                             |

## Model assignment and order

| Task                                               | Implement                                | Review | Depends on |
| -------------------------------------------------- | ---------------------------------------- | ------ | ---------- |
| 0 branch from `main`, check preconditions          | controller                               | -      | -          |
| 1 registration helper and synthetic third language | sonnet                                   | sonnet | 0          |
| 2 WebGUI test pack                                 | haiku                                    | sonnet | 0          |
| 3 scanner and initial baseline                     | sonnet                                   | opus   | 0          |
| 4 false positives, sweep, final baseline           | sonnet                                   | opus   | 3          |
| 5 final verification                               | controller (haiku may collect summaries) | -      | 1-4        |

Tasks run in order 0 -> 1 -> 2 -> 3 -> 4 -> 5, one agent at a time in one working tree. Tasks 1,
2 and 3 touch disjoint files and could run in parallel in separate worktrees, but one shared index
makes parallel commits fragile, so the default is sequential. Task 4 must follow Task 3: it marks
the false positives Task 3's scanner reports and re-seeds the baseline Task 3 created.

---

### Task 0: Branch from `main` and check the preconditions

Phase 2a is merged, so the work branches from `main`. Stop and report if a check fails.

- [ ] **Step 1: Branch**

```bash
git fetch origin
git switch -c feat/1044-phase2b-guards origin/main
```

- [ ] **Step 2: Check what phase 2a provides** — every command must succeed:

```bash
grep -n "^_PACKS: dict\[str, LanguagePack\]" src/sapguimcp/lang/__init__.py
grep -n "^_views: dict\[str, LanguagePack\]" src/sapguimcp/lang/__init__.py
grep -n "^def universal" src/sapguimcp/lang/__init__.py
grep -c "^def _check_" unittests/lang/test_pack_completeness.py   # expect 10
grep -n "def lang_strings" unittests/webgui/conftest.py
grep -n "monkeypatch.setitem(lang._PACKS" unittests/test_sap_config_languages.py
test ! -e unittests/test_no_ui_literals.py
test ! -e unittests/lang_baseline.json
git grep -n "_register_for_tests" -- src unittests; test $? -eq 1
```

If `main` moved on since `7293c0d`, the numbers in Tasks 3 and 4 may drift a little; that is
expected, and each step says what to do then.

---

### Task 1: Registration helper and synthetic third language

Spec §10 ("a synthetic third language is registered in tests") and 2a decision 13.

**Files:**

- Modify: `src/sapguimcp/lang/__init__.py`
- Create: `unittests/lang/synthetic_pack.py`
- Create: `unittests/lang/test_synthetic_language.py`
- Modify: `unittests/test_sap_config_languages.py`

- [ ] **Step 1: Write the synthetic pack** — `unittests/lang/synthetic_pack.py`:

```python
"""A synthetic third language pack for the guard tests (#1044, spec section 10).

``synthetic_pack()`` derives a complete pack from EN: every text gets the marker prefix
``⟦XX⟧ ``, except the fields listed in ``same_as_en``, which stay identical to EN. Derived, not
hand-written, so the fields the phase-3 migrations add to the schema appear here without an edit.

Register it only through ``lang._register_for_tests``; never patch ``lang._PACKS``.
"""

import dataclasses
import re
from collections.abc import Mapping

from sapguimcp import lang
from sapguimcp.lang.schema import LanguagePack, Leaf, canonical, sections
from sapguimcp.lang.text import RegexText, Template, Text

CODE = "XX"
MARK = "⟦XX⟧ "
SAME_AS_EN = frozenset({"keys.names[Alt]"})
"""One deliberately untranslated field, so the ``same_as_en`` guards run on a real entry."""


def mark(leaf: Leaf) -> Leaf:
    """The marked copy of one text, with the same kind, flags and placeholders."""
    if isinstance(leaf, Text):
        return Text(tuple(MARK + variant for variant in leaf.variants), fold=leaf.fold, word=leaf.word)
    if isinstance(leaf, RegexText):
        # Grouped, so a top-level alternation in the pattern keeps the marker on every branch.
        return RegexText(tuple(f"{re.escape(MARK)}(?:{pattern})" for pattern in leaf.patterns), fold=leaf.fold)
    return Template(tuple(MARK + variant for variant in leaf.variants), fold=leaf.fold)


def synthetic_pack(code: str = CODE, same_as_en: frozenset[str] = SAME_AS_EN) -> LanguagePack:
    """A complete pack derived from EN; fields in ``same_as_en`` keep the EN value."""
    reference = lang.pack_for("EN")
    replaced: dict[str, object] = {}
    for section_name, section in sections(reference):
        values: dict[str, object] = {}
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            path = f"{section_name}.{field.name}"
            if isinstance(value, Mapping):
                values[field.name] = canonical(
                    {key: leaf if f"{path}[{key}]" in same_as_en else mark(leaf) for key, leaf in value.items()}
                )
            else:
                values[field.name] = value if path in same_as_en else mark(value)
        replaced[section_name] = type(section)(**values)
    return dataclasses.replace(
        reference,
        code=code,
        html_lang=code.lower(),
        logon_dropdown="Synthetisch",
        date_format="%Y-%m-%d",
        same_as_en=same_as_en,
        **replaced,
    )
```

- [ ] **Step 2: Write the failing tests** — `unittests/lang/test_synthetic_language.py`:

```python
"""A synthetic third language through the registry and every guard (#1044, spec section 10).

Exercises the N-language merge, template group naming, flag consistency and the
``UnsupportedLanguageError`` path before a real third language exists.
"""

import dataclasses
from collections.abc import Iterator

import pytest

from sapguimcp import lang
from sapguimcp.lang import UnsupportedLanguageError, _register_for_tests
from sapguimcp.lang.de import DE
from sapguimcp.lang.en import EN
from sapguimcp.lang.schema import JobStatus, Key, KeysSection, LanguagePack, canonical, merge
from sapguimcp.lang.text import RegexText, Text
from unittests.lang.synthetic_pack import CODE, MARK, mark, synthetic_pack
from unittests.lang.test_pack_completeness import (
    _check_canonical_mappings,
    _check_leaves_are_texts,
    _check_merge_modes,
    _check_no_collisions,
    _check_regexes_compile,
    _check_same_as_en_entries,
    _check_same_placeholders,
    _check_same_shape_as,
    _check_scalars,
    _check_untranslated_declared,
    _mappings,
)

XX = synthetic_pack()


@pytest.fixture
def xx() -> Iterator[LanguagePack]:
    with _register_for_tests(XX) as pack:
        yield pack


# ---------------------------------------------------------------------------
# The registration helper
# ---------------------------------------------------------------------------


def test_registration_is_scoped_to_the_block() -> None:
    before = lang.universal()  # primes the cache the helper has to clear
    with _register_for_tests(XX):
        assert lang.supported_languages() == ("DE", "EN", CODE)
        assert lang.pack_for("xx") is XX
        assert lang.universal() is not before
    assert lang.supported_languages() == ("DE", "EN")
    assert lang.universal().keys.names[Key.CTRL].variants == ("Strg", "Ctrl")
    with pytest.raises(UnsupportedLanguageError, match=r"supported: DE, EN$"):
        lang.pack_for(CODE)


def test_registration_clears_the_session_views() -> None:
    de_before = lang.view_for("DE")
    with _register_for_tests(XX):
        de_inside = lang.view_for("DE")
        assert de_inside is not de_before
        assert de_inside.keys.names[Key.CTRL].variants == ("Strg", "Ctrl", f"{MARK}Ctrl")
    assert lang.view_for("DE").keys.names[Key.CTRL].variants == ("Strg", "Ctrl")


def test_registration_refuses_a_registered_code() -> None:
    with pytest.raises(ValueError, match="already registered"), _register_for_tests(dataclasses.replace(XX, code="DE")):
        pass
    assert lang.pack_for("DE") is DE


def test_registration_refuses_an_unnormalized_code() -> None:
    with pytest.raises(ValueError, match="upper-case"), _register_for_tests(dataclasses.replace(XX, code="xx")):
        pass
    assert lang.supported_languages() == ("DE", "EN")


def test_registration_is_undone_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError, match="boom"), _register_for_tests(XX):
        raise RuntimeError("boom")
    assert lang.supported_languages() == ("DE", "EN")


# ---------------------------------------------------------------------------
# Every 2a guard over the synthetic pack
# ---------------------------------------------------------------------------


def test_synthetic_pack_passes_every_guard(xx: LanguagePack) -> None:
    view = lang.view_for(CODE)
    _check_scalars(xx)
    for pack in (xx, view):
        _check_leaves_are_texts(pack)
        _check_regexes_compile(pack)
        _check_canonical_mappings(pack)
    _check_regexes_compile(lang.universal())
    _check_same_shape_as(xx, EN)
    _check_same_placeholders(xx, EN)
    _check_merge_modes(xx)
    _check_untranslated_declared(xx, EN)
    _check_same_as_en_entries(xx, EN)
    assert len({lang.pack_for(code).html_lang for code in lang.supported_languages()}) == 3


@pytest.mark.parametrize("code", ["DE", "EN", CODE])
@pytest.mark.usefixtures("xx")
def test_no_variant_maps_to_two_members_with_three_languages(code: str) -> None:
    with lang.use(code):
        _check_no_collisions(code, _mappings(lang.current()))
    _check_no_collisions("universal", {"keys.names": lang.universal().keys.names})


def test_a_synthetic_pack_without_its_same_as_en_entry_fails_the_guard() -> None:
    with pytest.raises(AssertionError):
        _check_untranslated_declared(dataclasses.replace(XX, same_as_en=frozenset()), EN)


# ---------------------------------------------------------------------------
# N-language merge
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("xx")
def test_session_en_sections_hold_the_session_pack_then_en() -> None:
    with lang.use(CODE):
        view = lang.current()
    assert view.code == CODE
    assert view.same_as_en == XX.same_as_en
    assert view.se16.hit_count_label.variants == (f"{MARK}Number of Hits", "Number of Hits")  # no DE
    assert lang.view_for("DE").se16.hit_count_label.variants == ("Anzahl Treffer", "Number of Hits")  # no XX


@pytest.mark.usefixtures("xx")
def test_all_sections_hold_every_language() -> None:
    with lang.use(CODE):
        assert lang.current().keys.names[Key.CTRL].variants == (f"{MARK}Ctrl", "Strg", "Ctrl")  # session first
    assert lang.universal().keys.names[Key.CTRL].variants == ("Strg", "Ctrl", f"{MARK}Ctrl")  # registration order
    assert lang.universal().keys.names[Key.ALT].variants == ("Alt",)  # same_as_en: de-duplicated


@pytest.mark.usefixtures("xx")
def test_canonical_mapping_matches_every_language() -> None:
    status = lang.view_for(CODE).sm37.status
    assert status[JobStatus.READY].equals(f"{MARK}Ready")
    assert status[JobStatus.READY].equals("Ready")
    assert not status[JobStatus.READY].equals("Bereit")


# ---------------------------------------------------------------------------
# Template group naming across languages
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("xx")
def test_template_groups_have_the_same_name_in_every_language() -> None:
    title = lang.view_for(CODE).se24.display_title
    for heading in (f"{MARK}Class Builder: Display ZCL_FOO", "Class Builder: Display ZCL_FOO"):
        match = title.search(heading, name=r"[A-Z0-9_/]+")
        assert match is not None, heading
        assert match["name"] == "ZCL_FOO"


def test_a_three_language_template_merge_keeps_one_group_name() -> None:
    merged = merge([DE.se24.display_title, EN.se24.display_title, XX.se24.display_title])
    assert len(merged.variants) == 3
    for heading in (
        "Klassenpflege: ZCL_FOO anzeigen",
        "Class Builder: Display ZCL_FOO",
        f"{MARK}Class Builder: Display ZCL_FOO",
    ):
        match = merged.search(heading, name=r"[A-Z0-9_/]+")
        assert match is not None, heading
        assert match["name"] == "ZCL_FOO"


def test_regex_marker_covers_every_branch_of_an_alternation() -> None:
    marked = mark(RegexText(("Alpha|Beta",)))
    assert marked.pattern.search(f"{MARK}Beta")
    assert not marked.pattern.search("Beta")


# ---------------------------------------------------------------------------
# Flag consistency
# ---------------------------------------------------------------------------


def _with_ctrl(text: Text) -> LanguagePack:
    return dataclasses.replace(XX, keys=KeysSection(names=canonical({**XX.keys.names, Key.CTRL: text})))


def test_a_flag_that_differs_from_en_fails_the_shape_guard() -> None:
    with pytest.raises(AssertionError):
        _check_same_shape_as(_with_ctrl(Text((f"{MARK}Ctrl",))), EN)  # word=True dropped


def test_a_flag_that_differs_fails_the_merge_of_every_language() -> None:
    with _register_for_tests(_with_ctrl(Text((f"{MARK}Ctrl",)))), pytest.raises(ValueError, match="flags differ"):
        lang.universal()


def test_a_kind_that_differs_fails_the_session_merge() -> None:
    broken = dataclasses.replace(XX, se11=dataclasses.replace(XX.se11, dictionary_type=Text(("Typ",))))
    with _register_for_tests(broken), pytest.raises(TypeError, match="cannot merge"):
        lang.view_for(CODE)


# ---------------------------------------------------------------------------
# UnsupportedLanguageError
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("xx")
def test_current_names_the_third_language_while_it_is_registered() -> None:
    with lang.use("IT"), pytest.raises(UnsupportedLanguageError, match="supported: DE, EN, XX") as excinfo:
        lang.current("SE24 lookup")
    assert excinfo.value.supported == ("DE", "EN", CODE)


def test_current_fails_for_the_third_language_once_it_is_gone() -> None:
    with _register_for_tests(XX), lang.use(CODE):
        assert lang.current().code == CODE
    with (
        lang.use(CODE),
        pytest.raises(UnsupportedLanguageError, match=r"needs a language pack for XX; supported: DE, EN$"),
    ):
        lang.current("SE24 lookup")
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run --group tests python -m pytest unittests/lang/test_synthetic_language.py -q`
Expected: collection error, `ImportError: cannot import name '_register_for_tests' from 'sapguimcp.lang'`.

- [ ] **Step 4: Implement the helper** in `src/sapguimcp/lang/__init__.py`:

```diff
--- a/src/sapguimcp/lang/__init__.py
+++ b/src/sapguimcp/lang/__init__.py
@@ -9,6 +9,7 @@
 - :data:`INVARIANT` - texts that are the same in every logon language (an :class:`Invariant`).
 - :func:`use` / :func:`set_session_language` - set the session language (tests, login).
 - :func:`pack_for`, :func:`supported_languages` - the registry.
+- ``_register_for_tests`` - registers an extra pack inside a ``with`` block (tests only).

 The ``X_DE`` / ``X_EN`` constants and ``bilingual_pattern`` of the former ``lang.py`` module are
 re-exported from :mod:`sapguimcp.lang._legacy` until the phase-3 migrations remove their last
@@ -148,3 +149,31 @@
     """Temporarily set the session language: ``with lang.use("DE"): lang.current()``."""
     with use_language(code):
         yield
+
+
+def _clear_caches() -> None:
+    """Forget every merged view; the next :func:`view_for` / :func:`universal` call rebuilds it."""
+    _views.clear()
+    universal.cache_clear()
+
+
+@contextmanager
+def _register_for_tests(pack: LanguagePack) -> Iterator[LanguagePack]:
+    """Register ``pack`` for the duration of a ``with`` block. Tests only (#1044, phase 2b).
+
+    Clears the merged-view caches on enter and on exit, so :func:`view_for`, :func:`current`,
+    :func:`universal` and :func:`supported_languages` see the pack inside the block and forget it
+    afterwards. Refuses a code that is already registered (replacing DE or EN would change what
+    other tests see) and a code that is not a normalized SAP language key.
+    """
+    if normalize_language(pack.code) != pack.code:
+        raise ValueError(f"pack code must be an upper-case SAP language key, got {pack.code!r}")
+    if pack.code in _PACKS:
+        raise ValueError(f"a pack for {pack.code} is already registered")
+    _PACKS[pack.code] = pack
+    _clear_caches()
+    try:
+        yield pack
+    finally:
+        del _PACKS[pack.code]
+        _clear_caches()
```

- [ ] **Step 5: Run** — expected PASS (21 tests):

`uv run --group tests python -m pytest unittests/lang/test_synthetic_language.py -q`

- [ ] **Step 6: Move the config test to the helper** (2a decision 13):

```diff
--- a/unittests/test_sap_config_languages.py
+++ b/unittests/test_sap_config_languages.py
@@ -6,10 +6,10 @@

 import pytest

-from sapguimcp import lang
-from sapguimcp.lang import supported_languages
+from sapguimcp.lang import _register_for_tests, supported_languages
 from sapguimcp.models import config as config_module
 from sapguimcp.utils import SapLanguage
+from unittests.lang.synthetic_pack import synthetic_pack


 def _system(**overrides: str) -> dict[str, str]:
@@ -60,10 +60,8 @@

     monkeypatch.setattr(config_module, "_sap_config", None)
     monkeypatch.setattr(config_module, "load_sap_config", fake_load)
-    # Only the registry is patched: the loader reads supported_languages(), which does not touch
-    # the merged-view caches. Do not combine this with lang.current()/universal() (decision 13).
-    monkeypatch.setitem(lang._PACKS, "XX", lang.pack_for("EN"))  # pylint: disable=protected-access
-    config_module.get_sap_config()
+    with _register_for_tests(synthetic_pack()):
+        config_module.get_sap_config()
     assert seen == [("DE", "EN", "XX")]


```

Keep the `monkeypatch` parameter of that test: it still patches `_sap_config` and `load_sap_config`.

- [ ] **Step 7: Run** — expected PASS:

`uv run --group tests python -m pytest unittests/lang/ unittests/test_sap_config_languages.py -q`

(In the prototype: 278 passed for `unittests/lang/`, 6 for the config test.)

- [ ] **Step 8: Lint and type check** (commands in the testing rules).

- [ ] **Step 9: Commit**

```bash
git add src/sapguimcp/lang/__init__.py unittests/lang/synthetic_pack.py unittests/lang/test_synthetic_language.py unittests/test_sap_config_languages.py
git commit -m "test(lang): registration helper and a synthetic third language through every guard (#1044)"
```

---

### Task 2: WebGUI test pack

Spec "Today's ways" row 13 and §10 "Language in the test suite": the test-only constants become a
test pack with the same `Text` type, sections and a completeness test; the `("DE", "EN")` check
becomes `supported_languages()`. Behaviour of the live tests is unchanged.

**Files:**

- Rewrite: `unittests/webgui/testdata/lang_test.py`
- Create: `unittests/webgui/test_lang_test_pack.py`
- Modify: `unittests/webgui/conftest.py`, `unittests/webgui/test_selectors.py`,
  `unittests/webgui/test_popup_integration.py`

- [ ] **Step 1: Check the consumers** — the only users of the old names must be these:

```bash
git grep -n "lang_strings\|lang_test import\|SapLanguage" -- unittests/webgui
```

Expected: `conftest.py` (fixture, `SapLanguage`, the import), five tests in `test_selectors.py`,
one in `test_popup_integration.py`. Stop and report if there are others.

- [ ] **Step 2: Write the completeness test** — `unittests/webgui/test_lang_test_pack.py`:

```python
"""Completeness of the WebGUI test packs (#1044, spec section 10, "Language in the test suite")."""

import dataclasses
from collections.abc import Iterator

import pytest

from sapguimcp import lang
from sapguimcp.lang import Text
from unittests.webgui.testdata.lang_test import TEST_DE, UI_TEST_PACKS, UiTestPack, resolve_sap_language

EN = UI_TEST_PACKS["EN"]


def _leaves(pack: UiTestPack) -> Iterator[tuple[str, object]]:
    """``(section.field, value)`` for every text of a test pack."""
    for section in dataclasses.fields(pack):
        value = getattr(pack, section.name)
        if dataclasses.is_dataclass(value):
            for field in dataclasses.fields(value):
                yield f"{section.name}.{field.name}", getattr(value, field.name)


def _check_complete(pack: UiTestPack) -> None:
    """Same fields, kinds and flags as the EN test pack; every value a ``Text`` with variants."""
    leaves = dict(_leaves(pack))
    expected = dict(_leaves(EN))
    assert leaves.keys() == expected.keys()
    for path, leaf in leaves.items():
        assert isinstance(leaf, Text), path
        assert all(variant.strip() for variant in leaf.variants), path
        other = expected[path]
        assert isinstance(other, Text), path
        assert (leaf.fold, leaf.word) == (other.fold, other.word), path


def _check_untranslated_declared(pack: UiTestPack) -> None:
    equal = {path for path, leaf in _leaves(pack) if leaf == dict(_leaves(EN))[path]}
    assert equal == pack.same_as_en


def test_every_registered_language_has_a_test_pack() -> None:
    assert set(UI_TEST_PACKS) == set(lang.supported_languages())


@pytest.mark.parametrize("code", sorted(UI_TEST_PACKS))
def test_test_pack_is_complete(code: str) -> None:
    pack = UI_TEST_PACKS[code]
    assert pack.code == code
    _check_complete(pack)


def test_en_test_pack_declares_nothing_as_same_as_en() -> None:
    assert EN.same_as_en == frozenset()


@pytest.mark.parametrize("code", sorted(code for code in UI_TEST_PACKS if code != "EN"))
def test_untranslated_test_texts_are_declared(code: str) -> None:
    _check_untranslated_declared(UI_TEST_PACKS[code])


def test_guard_rejects_a_missing_translation() -> None:
    copied = dataclasses.replace(TEST_DE, bp=EN.bp)
    with pytest.raises(AssertionError):
        _check_untranslated_declared(copied)


def test_guard_rejects_a_flag_that_differs_from_en() -> None:
    changed = dataclasses.replace(TEST_DE, bp=dataclasses.replace(TEST_DE.bp, yes_button=Text(("Ja",))))
    with pytest.raises(AssertionError):
        _check_complete(changed)


@pytest.mark.parametrize(
    ("env", "expected"),
    [(None, "DE"), ("en", "EN"), ("DE", "DE"), ("IT", "DE")],
)
def test_sap_language_fixture_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, env: str | None, expected: str
) -> None:
    if env is None:
        monkeypatch.delenv("SAP_LANGUAGE", raising=False)
    else:
        monkeypatch.setenv("SAP_LANGUAGE", env)
    assert resolve_sap_language() == expected
```

Run: `uv run --group tests python -m pytest unittests/webgui/test_lang_test_pack.py -q`
Expected: collection error, `ImportError: cannot import name 'TEST_DE' from 'unittests.webgui.testdata.lang_test'`.

- [ ] **Step 3: Rewrite the test pack** — replace the whole of
      `unittests/webgui/testdata/lang_test.py` with:

```python
"""Test-only SAP texts of the WebGUI tests, as one test pack per logon language (#1044).

The same mechanism as the language packs in ``sapguimcp.lang``: frozen dataclass sections with
required fields only, every value a ``Text``, and a completeness test
(``unittests/webgui/test_lang_test_pack.py``) that checks every registered language has a test
pack with the same fields, kinds and flags. A field whose value deliberately equals EN is listed
in ``same_as_en``. The ``ui_texts`` fixture in ``unittests/webgui/conftest.py`` selects the pack
for ``SAP_LANGUAGE``.

These texts belong to the tests, not to the server, so they live here and not in a language pack.
"""

import os
from dataclasses import dataclass

from sapguimcp.lang import Text, supported_languages

DEFAULT_LANGUAGE = "DE"


@dataclass(frozen=True, slots=True)
class BpTexts:
    """BP transaction (business partner)."""

    postal_code: Text
    city: Text
    street: Text
    gp_role_label: Text
    grouping_label: Text
    gp_role_default: Text
    """Partial match: the full EN value is "Business Partner (Gen.)"."""
    yes_button: Text
    no_button: Text


@dataclass(frozen=True, slots=True)
class Sm30Texts:
    """SM30 (table maintenance)."""

    maintain_button: Text
    table_view_label: Text


@dataclass(frozen=True, slots=True)
class Se38Texts:
    """SE38 (ABAP editor)."""

    create_button: Text
    continue_button: Text
    long_doc_button: Text


@dataclass(frozen=True, slots=True)
class ButtonTexts:
    """Common popup and dialog buttons."""

    cancel: Text
    ok: Text
    save: Text
    back: Text


@dataclass(frozen=True, slots=True)
class UiTestPack:
    """Test-only texts of one SAP logon language."""

    code: str
    same_as_en: frozenset[str]
    bp: BpTexts
    sm30: Sm30Texts
    se38: Se38Texts
    buttons: ButtonTexts


TEST_DE = UiTestPack(
    code="DE",
    same_as_en=frozenset({"buttons.ok"}),
    bp=BpTexts(
        postal_code=Text(("Postleitzahl",)),
        city=Text(("Ort",)),
        street=Text(("Straße",)),
        gp_role_label=Text(("GP-Rolle",)),
        grouping_label=Text(("Gruppierung",)),
        gp_role_default=Text(("GPartner allgemein",)),
        yes_button=Text(("Ja",), word=True),
        no_button=Text(("Nein",), word=True),
    ),
    sm30=Sm30Texts(
        maintain_button=Text(("Pflegen",)),
        table_view_label=Text(("Tabelle/Sicht",)),
    ),
    se38=Se38Texts(
        create_button=Text(("Anlegen",)),
        continue_button=Text(("Weiter",)),
        long_doc_button=Text(("Langdokumentation",)),
    ),
    buttons=ButtonTexts(
        cancel=Text(("Abbrechen",)),
        ok=Text(("OK",)),
        save=Text(("Sichern",)),
        back=Text(("Zurück",)),
    ),
)

TEST_EN = UiTestPack(
    code="EN",
    same_as_en=frozenset(),
    bp=BpTexts(
        postal_code=Text(("Postal Code",)),
        city=Text(("City",)),
        street=Text(("Street",)),
        gp_role_label=Text(("Role",)),
        grouping_label=Text(("Grouping",)),
        gp_role_default=Text(("Business Partner",)),
        yes_button=Text(("Yes",), word=True),
        no_button=Text(("No",), word=True),
    ),
    sm30=Sm30Texts(
        maintain_button=Text(("Maintain",)),
        table_view_label=Text(("Table/View",)),
    ),
    se38=Se38Texts(
        create_button=Text(("Create",)),
        continue_button=Text(("Continue",)),
        long_doc_button=Text(("Long text",)),
    ),
    buttons=ButtonTexts(
        cancel=Text(("Cancel",)),
        ok=Text(("OK",)),
        save=Text(("Save",)),
        back=Text(("Back",)),
    ),
)

UI_TEST_PACKS: dict[str, UiTestPack] = {pack.code: pack for pack in (TEST_DE, TEST_EN)}
"""Test packs by SAP language key; the completeness test requires one per registered language."""


def resolve_sap_language() -> str:
    """The WebGUI tests' logon language from ``SAP_LANGUAGE``; DE when unset or without a pack.

    Unchanged behaviour from the former ``("DE", "EN")`` check, with the list now coming from the
    registered language packs.
    """
    code = os.environ.get("SAP_LANGUAGE", DEFAULT_LANGUAGE).upper()
    return code if code in supported_languages() else DEFAULT_LANGUAGE
```

Every former constant is a field with the same value (`BP_POSTAL_CODE_DE` -> `TEST_DE.bp.postal_code`,
..., `BUTTON_BACK_EN` -> `TEST_EN.buttons.back`); compare the two versions field by field before
moving on.

- [ ] **Step 4: Fixtures** in `unittests/webgui/conftest.py`:

```diff
--- a/unittests/webgui/conftest.py
+++ b/unittests/webgui/conftest.py
@@ -6,7 +6,7 @@
 import sys
 from collections.abc import AsyncGenerator
 from pathlib import Path
-from typing import Any, Literal, TypeVar
+from typing import Any, TypeVar

 import pytest
 from dotenv import load_dotenv
@@ -16,6 +16,7 @@

 from sapguimcp.models import LoginResult
 from unittests.conftest import has_sap_webgui_creds
+from unittests.webgui.testdata.lang_test import UI_TEST_PACKS, UiTestPack, resolve_sap_language


 def resolve_login_user(login: LoginResult) -> str:
@@ -41,67 +42,22 @@
 # LANGUAGE HANDLING
 # =============================================================================

-SapLanguage = Literal["DE", "EN"]
-

 @pytest.fixture
-def sap_language() -> SapLanguage:
-    """Get current SAP language from environment (default: DE)."""
-    lang = os.environ.get("SAP_LANGUAGE", "DE").upper()
-    if lang not in ("DE", "EN"):
-        return "DE"
-    return lang  # type: ignore[return-value]
+def sap_language() -> str:
+    """SAP logon language of the WebGUI tests from ``SAP_LANGUAGE``: DE when unset or without a pack."""
+    return resolve_sap_language()


 @pytest.fixture
-def lang_strings(sap_language: SapLanguage) -> dict[str, str]:
-    """
-    Get language-specific test strings based on SAP_LANGUAGE.
+def ui_texts(sap_language: str) -> UiTestPack:
+    """Test-only SAP texts for ``SAP_LANGUAGE`` (see ``unittests/webgui/testdata/lang_test.py``).

     Usage in tests:
-        def test_something(lang_strings):
-            assert lang_strings["yes"] in button_text
+        def test_something(ui_texts):
+            assert ui_texts.bp.yes_button.contains(button_text)
     """
-    from unittests.webgui.testdata.lang_test import (
-        BP_GP_ROLE_DEFAULT_DE,
-        BP_GP_ROLE_DEFAULT_EN,
-        BP_GP_ROLE_LABEL_DE,
-        BP_GP_ROLE_LABEL_EN,
-        BP_GROUPING_LABEL_DE,
-        BP_GROUPING_LABEL_EN,
-        BP_NO_BUTTON_DE,
-        BP_NO_BUTTON_EN,
-        BP_POSTAL_CODE_DE,
-        BP_POSTAL_CODE_EN,
-        BP_YES_BUTTON_DE,
-        BP_YES_BUTTON_EN,
-        SE38_CREATE_BUTTON_DE,
-        SE38_CREATE_BUTTON_EN,
-        SM30_MAINTAIN_BUTTON_DE,
-        SM30_MAINTAIN_BUTTON_EN,
-    )
-
-    if sap_language == "DE":
-        return {
-            "postal_code": BP_POSTAL_CODE_DE,
-            "yes": BP_YES_BUTTON_DE,
-            "no": BP_NO_BUTTON_DE,
-            "gp_role_label": BP_GP_ROLE_LABEL_DE,
-            "gp_role_default": BP_GP_ROLE_DEFAULT_DE,
-            "grouping_label": BP_GROUPING_LABEL_DE,
-            "create": SE38_CREATE_BUTTON_DE,
-            "maintain": SM30_MAINTAIN_BUTTON_DE,
-        }
-    return {
-        "postal_code": BP_POSTAL_CODE_EN,
-        "yes": BP_YES_BUTTON_EN,
-        "no": BP_NO_BUTTON_EN,
-        "gp_role_label": BP_GP_ROLE_LABEL_EN,
-        "gp_role_default": BP_GP_ROLE_DEFAULT_EN,
-        "grouping_label": BP_GROUPING_LABEL_EN,
-        "create": SE38_CREATE_BUTTON_EN,
-        "maintain": SM30_MAINTAIN_BUTTON_EN,
-    }
+    return UI_TEST_PACKS[sap_language]


 # Path to HTML snapshots directory for selector unit tests
```

`os` stays imported (the `sap_mcp_client` fixture uses it).

- [ ] **Step 5: Consumers** — `unittests/webgui/test_selectors.py`:

```diff
--- a/unittests/webgui/test_selectors.py
+++ b/unittests/webgui/test_selectors.py
@@ -37,6 +37,7 @@
 # Import the selectors we want to test
 from sapguimcp.backend.webgui.utils import escape_css_selector
 from sapguimcp.tools.sap_tools import SELECTORS, parse_shortcut_from_title
+from unittests.webgui.testdata.lang_test import UiTestPack


 @pytest.fixture
@@ -1113,7 +1114,7 @@
             pytest.skip(f"Snapshot {snapshot_path.name} doesn't contain popup elements")
         assert popup is not None, "Expected popup container element"

-    def test_se38_error_popup_has_buttons(self, html_snapshots_path: Path, lang_strings: dict[str, str]) -> None:
+    def test_se38_error_popup_has_buttons(self, html_snapshots_path: Path) -> None:
         """Verify SE38 error popup has expected buttons."""
         snapshot_path = get_snapshot_path(html_snapshots_path, "se38_error_popup")
         if not snapshot_path:
@@ -1169,9 +1170,7 @@
         blocking_layer = soup.select_one("#urPopupWindowBlockLayer, .lsBlockLayer")
         assert blocking_layer is not None, "Expected blocking layer element"

-    def test_bp_validation_popup_has_ja_nein_buttons(
-        self, html_snapshots_path: Path, lang_strings: dict[str, str]
-    ) -> None:
+    def test_bp_validation_popup_has_ja_nein_buttons(self, html_snapshots_path: Path, ui_texts: UiTestPack) -> None:
         """Verify BP validation popup has Yes/No buttons."""
         snapshot_path = get_snapshot_path(html_snapshots_path, "bp_validation_popup")
         if not snapshot_path:
@@ -1185,9 +1184,10 @@
         button_texts = [btn.get_text(strip=True) for btn in buttons]

         # Should have Yes and No buttons (DE: Ja/Nein, EN: Yes/No)
-        has_yes = any(lang_strings["yes"] in text for text in button_texts)
-        has_no = any(lang_strings["no"] in text for text in button_texts)
-        assert has_yes and has_no, f"Expected {lang_strings['yes']}/{lang_strings['no']} buttons. Got: {button_texts}"
+        yes, no = ui_texts.bp.yes_button, ui_texts.bp.no_button
+        has_yes = any(yes.contains(text) for text in button_texts)
+        has_no = any(no.contains(text) for text in button_texts)
+        assert has_yes and has_no, f"Expected {yes.variants}/{no.variants} buttons. Got: {button_texts}"

     def test_se38_initial_has_no_popup(self, html_snapshots_path: Path) -> None:
         """Verify SE38 initial screen has no blocking popup."""
@@ -1224,7 +1224,7 @@
         dropdowns = soup.select('input[ct="CB"]')
         assert len(dropdowns) >= 1, "Expected at least one dropdown field in BP create person"

-    def test_bp_create_person_gp_rolle_dropdown(self, html_snapshots_path: Path, lang_strings: dict[str, str]) -> None:
+    def test_bp_create_person_gp_rolle_dropdown(self, html_snapshots_path: Path, ui_texts: UiTestPack) -> None:
         """Verify GP-Rolle/Role dropdown has expected attributes."""
         snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
         if not snapshot_path:
@@ -1236,21 +1236,21 @@
         # Find dropdown with GP-Rolle/Role label (look for lsdata containing the text)
         dropdowns = soup.select('input[ct="CB"]')
         gp_rolle_dropdown = None
-        role_label = lang_strings["gp_role_label"]
+        role_label = ui_texts.bp.gp_role_label
         for dd in dropdowns:
             title = dd.get("title", "")
             # Check for both DE and EN labels in case of fallback
-            if role_label in title or "GP-Rolle" in title or "Role" in title:
+            if role_label.contains(title) or "GP-Rolle" in title or "Role" in title:
                 gp_rolle_dropdown = dd
                 break

-        assert gp_rolle_dropdown is not None, f"Expected {role_label} dropdown field"
+        assert gp_rolle_dropdown is not None, f"Expected {role_label.variants} dropdown field"
         assert gp_rolle_dropdown.get("readonly") is not None or gp_rolle_dropdown.has_attr("readonly"), (
             "Dropdown should be readonly"
         )
         assert gp_rolle_dropdown.get("aria-haspopup") == "true", "Dropdown should have aria-haspopup=true"

-    def test_bp_create_person_dropdown_has_value(self, html_snapshots_path: Path, lang_strings: dict[str, str]) -> None:
+    def test_bp_create_person_dropdown_has_value(self, html_snapshots_path: Path, ui_texts: UiTestPack) -> None:
         """Verify GP-Rolle dropdown has default value (GPartner allgemein / General BP)."""
         snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
         if not snapshot_path:
@@ -1261,20 +1261,18 @@

         # Find dropdown with value containing the expected default
         dropdowns = soup.select('input[ct="CB"]')
-        expected_value = lang_strings["gp_role_default"]
+        expected_value = ui_texts.bp.gp_role_default
         gp_role_found = False
         for dd in dropdowns:
             value = dd.get("value", "")
             # Check for both DE and EN values in case of fallback
-            if expected_value in value or "GPartner" in value or "General BP" in value:
+            if expected_value.contains(value) or "GPartner" in value or "General BP" in value:
                 gp_role_found = True
                 break

-        assert gp_role_found, f"Expected dropdown with '{expected_value}' default value"
+        assert gp_role_found, f"Expected dropdown with {expected_value.variants} default value"

-    def test_bp_create_person_gruppierung_dropdown_empty(
-        self, html_snapshots_path: Path, lang_strings: dict[str, str]
-    ) -> None:
+    def test_bp_create_person_gruppierung_dropdown_empty(self, html_snapshots_path: Path, ui_texts: UiTestPack) -> None:
         """Verify Gruppierung/Grouping dropdown exists and is empty by default."""
         snapshot_path = get_snapshot_path(html_snapshots_path, "bp_create_person")
         if not snapshot_path:
@@ -1287,18 +1285,18 @@
         # Note: Full German label is "Geschäftspartnergruppierung"
         dropdowns = soup.select('input[ct="CB"]')
         gruppierung_dropdown = None
-        grouping_label = lang_strings["grouping_label"]
+        grouping_label = ui_texts.bp.grouping_label
         for dd in dropdowns:
             title = dd.get("title", "").lower()
             # Check for partial match since full label is "Geschäftspartnergruppierung"
-            if grouping_label.lower() in title or "gruppieru" in title or "grouping" in title:
+            if grouping_label.contains(title) or "gruppieru" in title or "grouping" in title:
                 gruppierung_dropdown = dd
                 break

-        assert gruppierung_dropdown is not None, f"Expected {grouping_label} dropdown field"
+        assert gruppierung_dropdown is not None, f"Expected {grouping_label.variants} dropdown field"
         # Value should be empty
         value = gruppierung_dropdown.get("value", "")
-        assert value == "", f"{grouping_label} should be empty by default, got: {value}"
+        assert value == "", f"{grouping_label.variants} should be empty by default, got: {value}"

     def test_dropdown_detection_attributes(self, html_snapshots_path: Path) -> None:
         """Verify dropdown detection criteria work correctly."""
```

and `unittests/webgui/test_popup_integration.py`:

```diff
--- a/unittests/webgui/test_popup_integration.py
+++ b/unittests/webgui/test_popup_integration.py
@@ -20,6 +20,7 @@
     _wait_for_transaction_screen,
     capture_html_snapshot,
 )
+from .testdata.lang_test import UiTestPack


 @pytest.mark.anyio
@@ -141,7 +142,7 @@


 @pytest.mark.anyio
-async def test_se38_error_popup_with_body_message(sap_mcp_client: ClientSession, lang_strings: dict[str, str]) -> None:
+async def test_se38_error_popup_with_body_message(sap_mcp_client: ClientSession, ui_texts: UiTestPack) -> None:
     """
     Test popup detection with a detailed body message in SE38.

@@ -176,7 +177,7 @@
     assert fill_result.success, f"Fill program name failed: {fill_result.error}"

     # Click "Anlegen/Create" button - this triggers a popup
-    create_label = lang_strings["create"]
+    create_label = ui_texts.se38.create_button.variants[0]
     click_data = await call_tool_typed(
         sap_mcp_client,
         "browser_click",
```

- [ ] **Step 6: Run** — expected PASS, with the same three skips as on `main`
      (`settings_dialog` checkboxes, the `html.parser` login page, `bp_org_form` snapshot):

```bash
uv run --group tests python -m pytest unittests/webgui/test_lang_test_pack.py unittests/webgui/test_selectors.py -q -rs
uv run --group tests python -m pytest unittests/webgui/test_popup_integration.py --collect-only -q
```

(Prototype: 87 passed, 3 skipped; the live module collects 4 tests.) Run the first command on
`main` too and compare the skip reasons.

- [ ] **Step 7: Lint and type check.**

- [ ] **Step 8: Commit**

```bash
git add unittests/webgui/testdata/lang_test.py unittests/webgui/test_lang_test_pack.py unittests/webgui/conftest.py unittests/webgui/test_selectors.py unittests/webgui/test_popup_integration.py
git commit -m "test(webgui): test-only texts become a test pack checked against the registered languages (#1044)"
```

---

### Task 3: The no-literal scanner and its initial baseline

Spec §10 "No-literal scan". The module holds the scanner, the rule tests on small sources, the
guard tests over the code base and the `--prune` entry point. The guard tests need the baseline,
so this task seeds it from the scanner's own hits (before any `lang-ok`); Task 4 then exempts the
false positives, sweeps and re-seeds.

**Files:**

- Create: `unittests/test_no_ui_literals.py`
- Create: `unittests/lang_baseline.json` (generated)

- [ ] **Step 1: Write the scanner** — `unittests/test_no_ui_literals.py`:

```python
"""No SAP UI literal outside the language packs (#1044, spec section 10).

Scans ``src/sapguimcp/**/*.py`` (outside ``lang/``) and ``backend/webgui/js/*.js`` for string
literals that look like SAP screen text, with three rules:

1. **Sink rule** (AST): a literal passed to a UI sink (``click_button``, ``get_by_role(name=...)``,
   a local ``*_bilingual`` helper, a ``text=`` / ``has-text(...)`` / ``[title*=...]`` selector),
   compared with ``in`` / ``==`` / ``startswith`` / ``re.*`` against a name that looks like screen
   text (``title``, ``status``, ``label``, ...), or used as a key of ``row.get(...)`` / ``row[...]``.
2. **Value rule**: a literal that contains, as whole words and case-folded, a variant of five or
   more characters of any registered language pack. It skips the server's own messages (f-string
   parts, ``raise`` arguments, ``error=`` / ``message=`` values), identifiers, CSS selectors and
   prose of more than six words; the sink rule still applies to those.
3. **JS rule**: a string or regex literal used with ``includes``, ``===``, ``match``, ``test``,
   ``replace``, ..., or in a ``title*=`` / ``has-text`` selector, in ``.js`` files and in JS
   functions held in Python strings (``evaluate_javascript("() => {...}")``).

Skipped everywhere: docstrings, logging calls, ``description=`` keyword arguments, and literals that
are code (no letters, one character, ``snake_case``, ALL CAPS, only DOM/ARIA vocabulary).

Exemptions are keyed by file and literal, never by line:

- ``unittests/lang_baseline.json`` is shrink-only: ``{file: {literal: count}}``, where ``count`` is
  how many (not skipped, not ``lang-ok``) literals in that file have exactly that value. A new hit
  fails, and so does an entry whose count no longer matches. Phase-3 migrations only delete or lower
  entries; ``uv run python unittests/test_no_ui_literals.py --prune`` does that and never adds one.
- ``# lang-ok: <reason>`` (``// lang-ok: <reason>`` in JS) on any line of the literal is a permanent
  exemption for literals that are code identifiers or the server's own messages. A pack added later
  may need new ``lang-ok`` comments, never a baseline entry.
"""

import ast
import io
import json
import re
import sys
import textwrap
import tokenize
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pytest

from sapguimcp import lang
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.text import Template, Text

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "sapguimcp"
LANG_DIR = SRC / "lang"
JS_DIR = SRC / "backend" / "webgui" / "js"
BASELINE = Path(__file__).with_name("lang_baseline.json")

MIN_VALUE_LENGTH = 5
MAX_VALUE_WORDS = 6
"""Longer literals are prose (messages, docs); the value rule leaves them to the sink rule."""
MESSAGE_KEYWORDS = frozenset({"error", "message", "msg", "hint", "reason", "details", "suggestion"})
CSS_SELECTOR = re.compile(r"\s*(?:[.#\[]|[a-z]+[.#\[:])|.*\[(?:class|id|name|role|lsdata|ct|data-[\w-]+)[*^$|~]?=")
IDENTIFIER = re.compile(r"[a-z]+(?:-[a-z]+)*|[A-Za-z]:\\.*")
"""``active``, ``data-program``, a Windows path: code, not screen text."""

SINK_CALLS = frozenset(
    {
        "click_button",
        "click_tab",
        "fill_field",
        "fill_form",
        "set_checkbox",
        "select_dropdown",
        "get_by_text",
        "get_by_label",
        "get_by_title",
        "get_by_placeholder",
    }
)
"""Calls whose string arguments are screen texts (positional, keyword, or dict keys)."""
SINK_CALL_PATTERN = re.compile(r"bilingual|^_?click_\w*(?:button|tab)|^find_button")
"""Local helpers that click or set by label: ``_click_tab_bilingual``, ``_click_display_button``, ..."""
SINK_KEYWORDS = frozenset({"has_text", "has_not_text"})
"""``locator(..., has_text=...)``; ``name=`` counts only in ``get_by_role``."""
CONTEXT_NAME = re.compile(r"title|heading|snapshot|status|msg|message|text|label|header|kind|level", re.IGNORECASE)
ROW_NAME = re.compile(r"(?:^|_)rows?(?:$|_)", re.IGNORECASE)
STRING_METHODS = frozenset({"startswith", "endswith", "find", "rfind", "index", "count", "split", "partition"})
TRANSPARENT_METHODS = frozenset({"lower", "upper", "casefold", "strip", "lstrip", "rstrip"})
RE_FUNCTIONS = frozenset({"search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"})
LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})
LOG_RECEIVER = re.compile(r"^_?(?:log|logger|logging|LOGGER|LOG)$|_logger$|_log$")
SELECTOR = re.compile(
    r"""(?:(?<![\w.-])text=(?!=)|has-text\(|:text(?:-is)?\(|\[(?:title|aria-label|placeholder)[*^$|~]?=)\s*['"]?([^'"\])]*)"""
)
INLINE_JS = re.compile(r"\s*\(?\s*(?:async\s+)?(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>|\s*\(?\s*function\b")
"""A Python string holding a JS function for ``evaluate_javascript``; scanned with the JS rule."""
LANG_OK = re.compile(r"(?:#|//)\s*lang-ok:\s*\S")

TECHNICAL_WORDS = frozenset(
    " ".join(
        (
            # ARIA roles (snapshot syntax)
            "alert article banner button cell checkbox columnheader combobox dialog document generic grid",
            "gridcell group heading img link list listbox listitem main menu menubar menuitem navigation",
            "note option paragraph radio region row rowgroup rowheader separator status tab table tablist",
            "tabpanel textbox toolbar tooltip tree treeitem",
            # CSS values, tag names, input types, typeof results, event names, literals
            "block flex hidden inline none visible visibility collapse",
            "input select textarea span div form script style noscript iframe body",
            "text password submit reset file",
            "string number boolean object undefined function",
            "click dblclick change focus blur keydown keyup",
            "true false null",
        )
    ).split()
)
"""Lower-case DOM, ARIA and JS vocabulary; a literal made only of these words is code."""
_NOT_WORDS = re.compile(r"\\[A-Za-z]|\[(?![^\]]*=)[^\]]*\]|\{\w*\}")
"""Regex escapes (``\\s``), character classes (``[A-Z0-9_]``, not ``[title*=...]``), placeholders."""


@dataclass(frozen=True, order=True)
class Hit:
    """One flagged literal; ``rule`` names the rule that flagged it."""

    path: str
    line: int
    literal: str
    rule: str


# ---------------------------------------------------------------------------
# Shared filters
# ---------------------------------------------------------------------------


@cache
def pack_variants() -> tuple[str, ...]:
    """Case-folded variants of five or more characters from every registered pack (keys excluded)."""
    found: set[str] = set()
    for code in lang.supported_languages():
        for path, leaf in iter_leaves(lang.pack_for(code)):
            if path.startswith("keys."):
                continue  # canonical key names (Enter, Delete) are the press_key API, not screen text
            if isinstance(leaf, Text):
                found.update(leaf.variants)
            elif isinstance(leaf, Template):
                for variant in leaf.variants:
                    found.update(re.split(r"\{[A-Za-z_]\w*\}", variant))
    return tuple(sorted({v.strip().casefold() for v in found if len(v.strip()) >= MIN_VALUE_LENGTH}))


@cache
def _pack_pattern() -> re.Pattern[str]:
    body = "|".join(re.escape(v) for v in sorted(pack_variants(), key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)")


def matches_pack(literal: str) -> bool:
    """Value rule: a pack variant occurs in ``literal`` as whole words, case-folded."""
    if IDENTIFIER.fullmatch(literal) or CSS_SELECTOR.match(literal) or len(literal.split()) > MAX_VALUE_WORDS:
        return False  # identifiers ("active"), CSS selectors, prose; screen text there is a sink hit
    return _pack_pattern().search(literal.casefold()) is not None


def is_technical(literal: str) -> bool:
    """Code, not screen text: no letters, one character, an identifier, or only technical words."""
    words = re.findall(r"[^\W\d_]+", _NOT_WORDS.sub(" ", literal))
    if not words or len(literal.strip()) == 1:
        return True
    if re.fullmatch(r"\w+", literal) and "_" in literal:
        return True  # snake_case / CONSTANT_NAME
    return all(word.isupper() or word in TECHNICAL_WORDS for word in words)


def _header_like(literal: str) -> bool:
    """SAP column headers start with a capital letter (``Methode``, ``Parameter Name``)."""
    return literal[:1].isupper()


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------


def _identifier(node: ast.AST) -> str | None:
    """The name a context check looks at: ``title``, ``self.title``, ``title.lower()``, ``rows[0]``."""
    while True:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in TRANSPARENT_METHODS
        ):
            node = node.func.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        else:
            break
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_context(node: ast.AST) -> bool:
    name = _identifier(node)
    return name is not None and CONTEXT_NAME.search(name) is not None


def _literals(node: ast.AST) -> list[ast.Constant]:
    """String constants of a literal operand: ``"x"``, ``("x", "y")``, ``["x"]``, ``{"x"}``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node]
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return [elt for elt in node.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)]
    return []


def _all_strings(node: ast.AST) -> list[ast.Constant]:
    return [n for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _skipped(tree: ast.Module) -> set[int]:
    """ids of string constants in docstrings, logging calls and ``description=`` arguments."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            skipped.add(id(node.value))  # docstrings and other bare string statements
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in LOG_METHODS:
                receiver = _identifier(func.value)
                if receiver is not None and LOG_RECEIVER.search(receiver):
                    skipped.update(id(n) for n in _all_strings(node))
            for keyword in node.keywords:
                if keyword.arg == "description":
                    skipped.update(id(n) for n in _all_strings(keyword.value))
    return skipped


def _messages(tree: ast.Module) -> set[int]:
    """ids of the server's own messages, which the value rule skips.

    f-string parts, ``raise`` arguments, ``error=`` / ``message=`` / ... keyword values, the values
    of such keys in dict literals (``{"error": "..."}``) and ``.get("error", "...")`` defaults.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr | ast.Raise):
            found.update(id(n) for n in _all_strings(node))
        elif isinstance(node, ast.keyword) and node.arg in MESSAGE_KEYWORDS:
            found.update(id(n) for n in _all_strings(node.value))
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value in MESSAGE_KEYWORDS:
                    found.update(id(n) for n in _all_strings(value))
        elif isinstance(node, ast.Call) and _call_name(node) == "get" and len(node.args) == 2:
            key = node.args[0]
            if isinstance(key, ast.Constant) and key.value in MESSAGE_KEYWORDS:
                found.update(id(n) for n in _all_strings(node.args[1]))
    return found


class _Flag:
    """Collects ``id(constant) -> rule``; the first rule that flags a constant wins."""

    def __init__(self) -> None:
        self.hits: dict[int, str] = {}

    def __call__(self, nodes: list[ast.Constant], rule: str) -> None:
        for node in nodes:
            self.hits.setdefault(id(node), rule)


def _call_sinks(node: ast.Call, flag: _Flag) -> None:
    name = _call_name(node)
    func = node.func
    if name in SINK_CALLS or (name and SINK_CALL_PATTERN.search(name)):
        for value in [*node.args, *(keyword.value for keyword in node.keywords)]:
            flag(_literals(value), "sink-call")
            if isinstance(value, ast.Dict):  # fill_form({"Label": ...}), bilingual_target(fields_de={...})
                flag([k for k in value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)], "sink-call")
    for keyword in node.keywords:
        if keyword.arg in SINK_KEYWORDS or (keyword.arg == "name" and name == "get_by_role"):
            flag(_literals(keyword.value), "sink-keyword")
    if not isinstance(func, ast.Attribute):
        return
    if func.attr in STRING_METHODS and _is_context(func.value):
        for arg in node.args:
            flag(_literals(arg), "compare")
    is_re = isinstance(func.value, ast.Name) and func.value.id == "re" and func.attr in RE_FUNCTIONS
    if is_re and node.args and any(_is_context(arg) for arg in node.args[1:]):
        flag(_all_strings(node.args[0]), "regex")
    if func.attr == "get" and node.args and ROW_NAME.search(_identifier(func.value) or ""):
        flag([n for n in _literals(node.args[0]) if _header_like(n.value)], "row-key")


def _sink_hits(tree: ast.Module) -> dict[int, str]:
    """ids of string constants the sink rule flags, with the sub-rule that flagged them."""
    flag = _Flag()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _call_sinks(node, flag)
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for left, op, right in zip(operands, node.ops, operands[1:], strict=False):
                if isinstance(op, ast.In | ast.NotIn | ast.Eq | ast.NotEq):
                    if _is_context(right):
                        flag(_literals(left), "compare")
                    if _is_context(left):
                        flag(_literals(right), "compare")
        elif isinstance(node, ast.Subscript) and ROW_NAME.search(_identifier(node.value) or ""):
            flag([n for n in _literals(node.slice) if _header_like(n.value)], "row-key")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = SELECTOR.search(node.value)
            if match and match.group(1).strip() and "{" not in match.group(1):
                flag([node], "selector")
    return flag.hits


def _lang_ok_lines(source: str) -> set[int]:
    return {
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT and LANG_OK.match(token.string)
    }


def scan_python(path: Path, relative: str) -> tuple[list[Hit], Counter[str]]:
    return scan_python_source(path.read_text(encoding="utf-8"), relative)


def scan_python_source(source: str, relative: str) -> tuple[list[Hit], Counter[str]]:
    """Hits in Python source, and how often each literal occurs (skipped and lang-ok ones not counted)."""
    tree = ast.parse(source, filename=relative)
    skipped = _skipped(tree)
    sinks = _sink_hits(tree)
    messages = _messages(tree)
    ok_lines = _lang_ok_lines(source)
    counts: Counter[str] = Counter()
    hits: list[Hit] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or not node.value.strip():
            continue
        if id(node) in skipped or ok_lines & set(range(node.lineno, (node.end_lineno or node.lineno) + 1)):
            continue
        if INLINE_JS.match(node.value):
            inner_hits, inner_counts = scan_js_source(node.value, relative, node.lineno)
            hits.extend(inner_hits)
            counts.update(inner_counts)
            continue
        counts[node.value] += 1
        rule = sinks.get(id(node)) or ("value" if id(node) not in messages and matches_pack(node.value) else None)
        if rule is not None and not is_technical(node.value):
            hits.append(Hit(relative, node.lineno, node.value, rule))
    return hits, counts


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

_JS_TOKEN = re.compile(
    r"""
    (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<str>'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*")
  | (?P<tmpl>`(?:\\.|[^`\\])*`)
  | (?P<ident>[A-Za-z_$][\w$]*)
  | (?P<num>\d[\w.]*)
  | (?P<op>===|!==|==|!=|=>|\?\.|&&|\|\||[{}()\[\];,.<>+\-*%=!?:&|^~@\#])
  | (?P<slash>/)
  | (?P<ws>\s+)
    """,
    re.VERBOSE | re.DOTALL,
)
_REGEX_BODY = re.compile(r"/(?:\\.|\[(?:\\.|[^\]\\])*\]|[^/\\\n\[])+/[a-z]*")
_REGEX_AFTER = frozenset({"(", ",", "=", ":", "[", "!", "&&", "||", "?", "{", "}", ";", "return", "=>"})
JS_METHODS = frozenset(
    {"includes", "match", "matchAll", "test", "replace", "replaceAll", "indexOf", "startsWith", "endsWith", "search"}
)
JS_ARRAY_METHODS = JS_METHODS | {"some", "find", "filter", "every"}
JS_EQUALITY = frozenset({"===", "!==", "==", "!="})


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    line: int


def _js_tokens(source: str) -> tuple[list[_Tok], set[int]]:
    """Tokens of JS source and the lines that carry a ``// lang-ok: <reason>`` comment."""
    tokens: list[_Tok] = []
    ok_lines: set[int] = set()
    position, line = 0, 1
    while position < len(source):
        if source[position] == "/" and not source.startswith(("//", "/*"), position):
            previous = tokens[-1] if tokens else None
            if previous is None or previous.text in _REGEX_AFTER or previous.text in JS_EQUALITY:
                regex = _REGEX_BODY.match(source, position)
                if regex:
                    tokens.append(_Tok("regex", regex.group(), line))
                    position = regex.end()
                    continue
        match = _JS_TOKEN.match(source, position)
        if match is None:
            raise ValueError(f"cannot tokenize JS at line {line}: {source[position : position + 20]!r}")
        kind, text = match.lastgroup or "", match.group()
        if kind == "comment":
            if LANG_OK.match(text):
                ok_lines.add(line)
        elif kind != "ws":
            tokens.append(_Tok("op" if kind == "slash" else kind, text, line))
        line += text.count("\n")
        position = match.end()
    return tokens, ok_lines


def scan_js(path: Path, relative: str) -> tuple[list[Hit], Counter[str]]:
    return scan_js_source(path.read_text(encoding="utf-8"), relative)


def scan_js_source(source: str, relative: str, first_line: int = 1) -> tuple[list[Hit], Counter[str]]:
    """JS rule and value rule over JS source: a ``.js`` file or a JS function inside a Python string."""
    tokens, ok_lines = _js_tokens(source)
    counts: Counter[str] = Counter()
    hits: list[Hit] = []
    for index, token in enumerate(tokens):
        if token.kind not in {"str", "regex", "tmpl"} or token.line in ok_lines:
            continue
        value = token.text if token.kind == "regex" else token.text[1:-1]
        if not value.strip():
            continue
        counts[value] += 1
        rule = _js_rule(tokens, index, value)
        if rule is None and token.kind == "str" and not _js_message(tokens, index) and matches_pack(value):
            rule = "value"
        words = value[1 : value.rindex("/")] if token.kind == "regex" else value
        if rule is not None and not is_technical(words):
            hits.append(Hit(relative, first_line + token.line - 1, value, rule))
    return hits, counts


def _js_message(tokens: list[_Tok], index: int) -> bool:
    """``throw new Error('...')`` or ``{error: '...'}``: the script's own message."""
    before = [t.text for t in tokens[max(index - 2, 0) : index]]
    return before == ["Error", "("] or (len(before) == 2 and before[1] == ":" and before[0] in MESSAGE_KEYWORDS)


def _js_rule(tokens: list[_Tok], index: int, value: str) -> str | None:
    def text(offset: int) -> str:
        position = index + offset
        return tokens[position].text if 0 <= position < len(tokens) else ""

    match = SELECTOR.search(value)
    if match and match.group(1).strip() and "${" not in match.group(1):
        return "js-selector"
    if text(-1) in JS_EQUALITY or text(1) in JS_EQUALITY:
        return "js-equality"
    called = text(-1) == "(" and text(-2) in JS_METHODS and text(-3) in {".", "?."}
    if called or (text(1) in {".", "?."} and text(2) in JS_METHODS):
        return "js-method"
    return "js-array" if _in_array_receiver(tokens, index) else None


def _in_array_receiver(tokens: list[_Tok], index: int) -> bool:
    """The literal is an element of ``[...]`` that is the receiver of ``.includes()`` / ``.some()`` / ..."""
    depth = 0
    for position in range(index - 1, -1, -1):
        current = tokens[position].text
        if current in {"]", ")", "}"}:
            depth += 1
        elif current in {"(", "{"}:
            if depth == 0:
                return False
            depth -= 1
        elif current == "[":
            if depth:
                depth -= 1
                continue
            close, inner = position + 1, 1
            while close < len(tokens) and inner:
                inner += {"[": 1, "]": -1}.get(tokens[close].text, 0)
                close += 1
            follow = [t.text for t in tokens[close : close + 2]]
            return len(follow) == 2 and follow[0] in {".", "?."} and follow[1] in JS_ARRAY_METHODS
    return False


# ---------------------------------------------------------------------------
# The scan and the baseline
# ---------------------------------------------------------------------------


def scanned_files() -> list[Path]:
    python = [p for p in SRC.rglob("*.py") if not p.is_relative_to(LANG_DIR)]
    return sorted([*python, *JS_DIR.glob("*.js")])


def scan() -> tuple[list[Hit], dict[str, Counter[str]]]:
    """Every hit (sorted) and the literal counts per file, over all scanned files."""
    hits: list[Hit] = []
    counts: dict[str, Counter[str]] = {}
    for path in scanned_files():
        relative = path.relative_to(ROOT).as_posix()
        file_hits, file_counts = (scan_js if path.suffix == ".js" else scan_python)(path, relative)
        hits.extend(file_hits)
        counts[relative] = file_counts
    return sorted(hits), counts


def load_baseline() -> dict[str, dict[str, int]]:
    baseline: dict[str, dict[str, int]] = json.loads(BASELINE.read_text(encoding="utf-8"))
    return baseline


def canonical_json(baseline: dict[str, dict[str, int]]) -> str:
    """The one accepted spelling of the baseline: files and literals sorted, no empty files."""
    ordered = {path: dict(sorted(entries.items())) for path, entries in sorted(baseline.items()) if entries}
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def new_hits(hits: list[Hit], baseline: dict[str, dict[str, int]]) -> list[str]:
    return [
        f"{hit.path}:{hit.line}: {hit.literal!r} ({hit.rule}): move it into a language pack, or mark a code "
        "identifier or the server's own message with '# lang-ok: <reason>'"
        for hit in hits
        if hit.literal not in baseline.get(hit.path, {})
    ]


def stale_entries(counts: dict[str, Counter[str]], baseline: dict[str, dict[str, int]]) -> list[str]:
    found: list[str] = []
    for path, entries in sorted(baseline.items()):
        for literal, expected in sorted(entries.items()):
            actual = counts.get(path, Counter())[literal]
            if actual > expected:
                found.append(f"{path}: {literal!r} occurs {actual}x, the baseline allows {expected}x: a new site")
            elif actual < expected:
                found.append(
                    f"{path}: {literal!r} occurs {actual}x, the baseline says {expected}x: shrink the entry "
                    "(uv run python unittests/test_no_ui_literals.py --prune)"
                )
    return found


def prune(baseline: dict[str, dict[str, int]], counts: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    """Lower every count to what the code still has and drop zeros. Never adds an entry."""
    pruned = {
        path: {literal: min(count, counts.get(path, Counter())[literal]) for literal, count in entries.items()}
        for path, entries in baseline.items()
    }
    return {path: {literal: count for literal, count in entries.items() if count} for path, entries in pruned.items()}


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scanned() -> tuple[list[Hit], dict[str, Counter[str]]]:
    return scan()


def test_no_new_ui_literals(scanned: tuple[list[Hit], dict[str, Counter[str]]]) -> None:
    hits, _ = scanned
    found = new_hits(hits, load_baseline())
    assert not found, "\n".join(found)


def test_baseline_only_shrinks(scanned: tuple[list[Hit], dict[str, Counter[str]]]) -> None:
    _, counts = scanned
    found = stale_entries(counts, load_baseline())
    assert not found, "\n".join(found)


def test_baseline_is_canonical() -> None:
    assert BASELINE.read_text(encoding="utf-8") == canonical_json(load_baseline())


def test_breakpoint_tools_stays_on_the_baseline() -> None:
    """``breakpoint_tools.py`` is off-limits (spec, Goal): its literals stay exempt via the baseline."""
    assert "src/sapguimcp/tools/breakpoint_tools.py" in load_baseline()


def test_every_lang_ok_names_a_reason() -> None:
    bare = [
        f"{path.relative_to(ROOT).as_posix()}:{number}"
        for path in scanned_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if "lang-ok" in line and not LANG_OK.search(line)
    ]
    assert not bare, f"'lang-ok' needs a reason ('# lang-ok: <reason>'): {bare}"


# ---------------------------------------------------------------------------
# The rules, on small sources
# ---------------------------------------------------------------------------


def _python(source: str) -> list[tuple[str, str]]:
    hits, _ = scan_python_source(textwrap.dedent(source), "x.py")
    return [(hit.literal, hit.rule) for hit in hits]


def _js(source: str) -> list[tuple[str, str]]:
    hits, _ = scan_js_source(textwrap.dedent(source), "x.js")
    return [(hit.literal, hit.rule) for hit in hits]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('click_button(session, "Sichern")', [("Sichern", "sink-call")]),
        (
            'await _set_checkbox_bilingual(b, "Änderbar", "Modifiable", True)',
            [("Änderbar", "sink-call"), ("Modifiable", "sink-call")],
        ),
        ('page.get_by_role("button", name="Weiter")', [("Weiter", "sink-keyword")]),
        ('ok = "einstieg" in title.lower()', [("einstieg", "compare")]),
        ('ok = window_title.startswith(("Pflegen", "Maintain"))', [("Pflegen", "compare"), ("Maintain", "compare")]),
        ('m = re.search("Eintrag", status_text)', [("Eintrag", "regex")]),
        ('value = row.get("Methode", row.get("Method"))', [("Methode", "row-key"), ("Method", "row-key")]),
        ("SELECTOR = \"span[title*='Einstellungen']\"", [("span[title*='Einstellungen']", "selector")]),
        ('LABELS = ("Anzahl Treffer", "Number of Hits")', [("Anzahl Treffer", "value"), ("Number of Hits", "value")]),
    ],
)
def test_python_rules_flag_screen_text(source: str, expected: list[tuple[str, str]]) -> None:
    assert _python(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        '"""Anzahl Treffer is read from the SE16 screen."""',
        'logger.info("Number of Hits: %s", hits)',
        'x = Field(default=None, description="Number of Hits shown by SE16")',
        'raise ValueError("Number of Hits not found")',
        'result = Result(error=f"Program {name} not found")',
        'ok = "Sichern" in data',
        'ok = status == "E"',
        'ok = kind in ("button", "checkbox")',
        'value = row.get("time")',
        "selector = f\"[title*='{label}']\"",
        'key = "active"',
        'threading.Thread(target=run, name="sapgui-com-worker")',
        'click_button(session, "Sichern")  # lang-ok: test fixture text',
    ],
)
def test_python_rules_skip_code_and_messages(source: str) -> None:
    assert _python(source) == []


def test_lang_ok_needs_a_reason() -> None:
    assert _python('click_button(session, "Sichern")  # lang-ok') == [("Sichern", "sink-call")]


def test_lang_ok_covers_every_line_of_a_multiline_literal() -> None:
    source = 'click_button(s, """Sichern\nund Weiter""")  # lang-ok: test fixture text\n'
    assert _python(source) == []


def test_inline_javascript_in_python_uses_the_js_rule() -> None:
    source = 'JS = """() => {\n    return text === \'Anzeigen\';\n}"""\n'
    hits, counts = scan_python_source(source, "x.py")
    assert [(hit.literal, hit.rule, hit.line) for hit in hits] == [("Anzeigen", "js-equality", 2)]
    assert counts["Anzeigen"] == 1


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("if (['ja', 'nein'].includes(t)) {}", [("ja", "js-array"), ("nein", "js-array")]),
        ("if (/Meldungsleiste/.test(x)) {}", [("/Meldungsleiste/", "js-method")]),
        ("if (el.title === 'Schließen') {}", [("Schließen", "js-equality")]),
        ("const c = document.querySelector(\"[title*='Schlie']\");", [("[title*='Schlie']", "js-selector")]),
        ("const s = text.replace('Meldungsleiste', '');", [("Meldungsleiste", "js-method")]),
    ],
)
def test_js_rule_flags_screen_text(source: str, expected: list[tuple[str, str]]) -> None:
    assert _js(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        "if (el.tagName === 'INPUT') {}",
        "if (style.display === 'none') {}",
        r"const t = text.replace(/\s+/g, ' ');",
        "throw new Error('Program not found');",
        "return {error: 'Number of Hits not found'};",
        "// if (t === 'Anzeigen') {}",
        "if (t === 'Anzeigen') {}  // lang-ok: test fixture text",
    ],
)
def test_js_rule_skips_code_and_messages(source: str) -> None:
    assert _js(source) == []


def test_value_rule_matches_whole_words_only() -> None:
    assert matches_pack("Number of Hits")
    assert not matches_pack("Number of Hitsfoo")
    assert not matches_pack("SEOCLASS-CLSNAME")  # "class" inside a technical name


def test_baseline_reports_new_sites_and_shrinking() -> None:
    counts = {"a.py": Counter({"Sichern": 2, "Pflegen": 1})}
    baseline = {"a.py": {"Sichern": 1, "Pflegen": 2, "Weg": 1}}
    found = stale_entries(counts, baseline)
    assert len(found) == 3
    assert "a new site" in found[1]  # sorted: Pflegen, Sichern, Weg
    assert prune(baseline, counts) == {"a.py": {"Sichern": 1, "Pflegen": 1}}


def test_new_hits_ignores_baselined_literals() -> None:
    hits = [Hit("a.py", 3, "Sichern", "sink-call"), Hit("a.py", 4, "Pflegen", "sink-call")]
    assert len(new_hits(hits, {"a.py": {"Sichern": 1}})) == 1


if __name__ == "__main__":
    if sys.argv[1:] != ["--prune"]:
        raise SystemExit("usage: uv run python unittests/test_no_ui_literals.py --prune")
    BASELINE.write_text(canonical_json(prune(load_baseline(), scan()[1])), encoding="utf-8", newline="\n")
```

- [ ] **Step 2: Run the rule tests** — expected PASS (40 tests); the five guard tests are
      deselected because the baseline does not exist yet:

```bash
uv run --group tests python -m pytest unittests/test_no_ui_literals.py -q -k "not no_new and not only_shrinks and not canonical and not stays_on and not names_a_reason"
```

- [ ] **Step 3: Write the one-off seed script** to `"$tmp/seed_lang_baseline.py"` with
      `tmp="$(mktemp -d)"` (outside the repository, never committed):

```python
"""One-off for #1044 phase 2b, Tasks 3 and 4: write unittests/lang_baseline.json. Not committed.

Usage (from the repository root): uv run python <this file> [inventory.jsonl]

Every current scanner hit becomes an entry with the literal's count in its file. Each line of the
optional inventory file is a JSON array ``["src/sapguimcp/<file>", "<literal>"]`` for a site the
scanner does not flag (the manual sweep); its count is read from the same scan, and a literal
that is not a counted literal of that file (a typo, a docstring, an f-string with a placeholder)
stops the script.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "unittests"))
import test_no_ui_literals as scanner

hits, counts = scanner.scan()
baseline: dict[str, dict[str, int]] = {}
for hit in hits:
    baseline.setdefault(hit.path, {})[hit.literal] = counts[hit.path][hit.literal]
detected = sum(len(entries) for entries in baseline.values())

added = 0
if len(sys.argv) > 1:
    for number, line in enumerate(Path(sys.argv[1]).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        path, literal = json.loads(line)
        count = counts.get(path, {}).get(literal, 0)
        if not count:
            raise SystemExit(f"inventory line {number}: {literal!r} is not a counted literal of {path}")
        if literal not in baseline.setdefault(path, {}):
            baseline[path][literal] = count
            added += 1

scanner.BASELINE.write_text(scanner.canonical_json(baseline), encoding="utf-8", newline="\n")
print(f"{detected} detected entries + {added} inventory entries in {len(baseline)} files")
```

- [ ] **Step 4: Seed from the detected hits**

```bash
uv run python "$tmp/seed_lang_baseline.py"
```

Expected output on `7293c0d`: `266 detected entries + 0 inventory entries in 36 files`. A small
drift after other merges is fine; note the actual numbers in the commit message.

- [ ] **Step 5: Run the whole module** — expected PASS (45 tests, about 1 s):

`uv run --group tests python -m pytest unittests/test_no_ui_literals.py -q`

Then check determinism: run it a second time and `git diff --exit-code unittests/lang_baseline.json`
after `uv run python unittests/test_no_ui_literals.py --prune` (prune must be a no-op).

- [ ] **Step 6: Lint** (ruff check and format; mypy does not cover `unittests/`).

- [ ] **Step 7: Commit**

```bash
git add unittests/test_no_ui_literals.py unittests/lang_baseline.json
git commit -m "test(lang): no-literal scanner with a shrink-only baseline seeded from its hits (#1044)"
```

---

### Task 4: False positives, inventory sweep and the final baseline

Spec §10: the baseline is "seeded from the manual inventory of all ~175 sites, not only from what
the detector finds", and `lang-ok` absorbs the sink rule's false positives. Three steps: mark the
false positives, sweep for what the scanner misses, re-seed from both.

**Files:**

- Modify (comments only): `src/sapguimcp/backend/desktop/_tree_helpers.py`,
  `src/sapguimcp/backend/webgui/browser.py`, `src/sapguimcp/backend/webgui/js/discover_fields.js`,
  `src/sapguimcp/backend/webgui/js/extract_screen_info.js`,
  `src/sapguimcp/backend/webgui/js/find_field_utils.js`,
  `src/sapguimcp/backend/webgui/js/extract_status_bar.js`, `src/sapguimcp/tools/se09_tools.py`,
  `src/sapguimcp/tables/search.py`
- Modify (generated): `unittests/lang_baseline.json`

- [ ] **Step 1: Confirm the false positives.** Print the current hits:

```bash
uv run python -c "import sys; sys.path.insert(0, 'unittests'); import test_no_ui_literals as s; [print(f'{h.rule:12} {h.path}:{h.line} {h.literal!r}') for h in s.scan()[0]]" > "$tmp/hits.txt"
```

These 13 lines hold false positives only (code identifiers, the server's or the browser's own
texts) and get `lang-ok` in Step 2. Check each one in `hits.txt`; if a line moved, use the line that
holds the same literal:

| Line (on `7293c0d`)                                                         | Literal(s)                                  | Reason for `lang-ok`           |
| --------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------ |
| `src/sapguimcp/backend/desktop/_tree_helpers.py:126`                        | `GuiShell`                                  | COM type name                  |
| `src/sapguimcp/backend/webgui/browser.py:258`                               | `invalid url`                               | browser error text, not SAP    |
| `src/sapguimcp/backend/webgui/js/discover_fields.js:14`                     | `/(?:txt\|ctxt\|cmb\|chk)(…)/`              | lsdata id prefixes             |
| `src/sapguimcp/backend/webgui/js/extract_screen_info.js:35`                 | `/[?&](?:tcode\|transaction)=(…)/i`         | URL parameter names            |
| `src/sapguimcp/backend/webgui/js/find_field_utils.js:45`                    | `/txt([A-Z0-9_-]+)$/`                       | SID prefix                     |
| `src/sapguimcp/backend/webgui/js/extract_status_bar.js:104`, `:112`, `:120` | `error`, `warning`, `success` (class names) | CSS class name                 |
| `src/sapguimcp/tools/se09_tools.py:229`, `:230`                             | `all`, `modifiable`, `released`             | tool parameter values          |
| `src/sapguimcp/tables/search.py:70`, `:73`, `:76`                           | `table name exact/prefix/contains`          | match reason of our own search |

These false positives stay on the **baseline** instead, because their lines also hold screen text
(decision 8) or the file is off-limits (decision 11): `se09_tools.py` lines 564, 565, 570, 571
(`all`, `modifiable`, `released` next to the checkbox labels), `sm37_tools.py` lines 118-123 and
126-131 (`scheduled`, ... next to the status labels), and in `breakpoint_tools.py`
`Breakpoint menu not found in Hilfsmittel` and `Grid not found at wnd[1]/...`. Every other hit in
`hits.txt` is screen text; if you find another false positive, apply the same rule (own line:
`lang-ok`; shared line or `breakpoint_tools.py`: baseline) and list it in the commit message.

- [ ] **Step 2: Add the comments** with the one-off marking script (write it to
      `"$tmp/mark_false_positives.py"`):

```python
"""One-off for #1044 phase 2b, Task 4: append a lang-ok comment to the scanner's false positives.

Usage (from the repository root): uv run python <this file> <path>:<line>=<reason> ...

Python lines get "  # lang-ok: <reason>" (ruff), JS lines " // lang-ok: <reason>" (prettier).
Refuses a line that already has a comment, so a reviewer sees every exemption once.
"""

import sys
from pathlib import Path

for spec in sys.argv[1:]:
    location, reason = spec.split("=", 1)
    path_text, number_text = location.rsplit(":", 1)
    path, number = Path(path_text), int(number_text)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    line = lines[number - 1]
    marker, gap = ("//", " ") if path.suffix == ".js" else ("#", "  ")
    body = line.rstrip("\r\n")
    if f" {marker} " in body or body.lstrip().startswith(marker):
        raise SystemExit(f"{location} already has a comment: {body.strip()}")
    lines[number - 1] = f"{body}{gap}{marker} lang-ok: {reason}" + line[len(body) :]
    path.write_text("".join(lines), encoding="utf-8", newline="")
    print(f"{location}: {lines[number - 1].strip()}")
```

```bash
B=src/sapguimcp
uv run python "$tmp/mark_false_positives.py" \
  "$B/backend/desktop/_tree_helpers.py:126=COM type name" \
  "$B/backend/webgui/browser.py:258=browser error text, not SAP" \
  "$B/backend/webgui/js/discover_fields.js:14=lsdata id prefixes" \
  "$B/backend/webgui/js/extract_screen_info.js:35=URL parameter names" \
  "$B/backend/webgui/js/find_field_utils.js:45=SID prefix" \
  "$B/backend/webgui/js/extract_status_bar.js:104=CSS class name" \
  "$B/backend/webgui/js/extract_status_bar.js:112=CSS class name" \
  "$B/backend/webgui/js/extract_status_bar.js:120=CSS class name" \
  "$B/tools/se09_tools.py:229=tool parameter values" \
  "$B/tools/se09_tools.py:230=tool parameter values" \
  "$B/tables/search.py:70=match reason of our own search" \
  "$B/tables/search.py:73=match reason of our own search" \
  "$B/tables/search.py:76=match reason of our own search"
```

The script writes two spaces before `#` (ruff) and one before `//` (prettier). Check with
`git diff --stat` that only these 8 files changed, 13 lines in total.

- [ ] **Step 3: Sweep for what the scanner misses.** Write the one-off sweep helper to
      `"$tmp/sweep_candidates.py"` and run it:

```python
"""One-off for #1044 phase 2b, Task 4: list literals the scanner misses but that look like screen text.

Usage (from the repository root): uv run python <this file> > candidates.jsonl

Prints one JSON array ``["<file>", "<literal>", <line>]`` per candidate: a counted literal that is
not a hit, not technical, at most 200 characters, and

- looks German (umlaut or a common German UI word), or sits in the same tuple / list / set / dict
  keys / call arguments as such a literal (usually the EN counterpart), or
- (Python only, not the server's own messages) contains a pack variant as a plain case-folded
  substring: what the value rule finds before its whole-word and identifier filters.

Review every line; keep the real screen texts, drop the line number, and pass the file to
seed_lang_baseline.py.
"""

import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "unittests"))
import test_no_ui_literals as scanner

GERMAN = re.compile(
    r"[äöüÄÖÜß]|\b(?:nicht|kein|keine|anzeigen|ändern|einstieg|auftr|meldung|fehler|bitte|sichern|weiter"
    r"|zurück|abbrechen|pflegen|anlegen|ausführen|suche|benutzer|tabelle|sicht|programm|klasse|methode"
    r"|ja|nein|protokoll|eintr|liste|leer|aktiv|angemeldet|objekt)",
    re.IGNORECASE,
)

hits, counts = scanner.scan()
flagged = {(hit.path, hit.literal) for hit in hits}
variants = scanner.pack_variants()


def candidate(path: str, literal: str) -> bool:
    return (
        counts[path][literal] > 0
        and (path, literal) not in flagged
        and not scanner.is_technical(literal)
        and len(literal) <= 200
    )


def python_groups(tree: ast.Module) -> list[list[tuple[int, str]]]:
    groups: list[list[tuple[int, str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple | ast.List | ast.Set | ast.Dict | ast.Call):
            if isinstance(node, ast.Dict):
                children = [key for key in node.keys if key is not None]
            elif isinstance(node, ast.Call):
                children = node.args
            else:
                children = node.elts
            strings = [c for c in children if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            if strings:
                groups.append([(c.lineno, c.value) for c in strings])
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            groups.append([(node.lineno, node.value)])
    return groups


for file in scanner.scanned_files():
    path = file.relative_to(scanner.ROOT).as_posix()
    loose: list[tuple[int, str]] = []
    if file.suffix == ".js":
        tokens, _ = scanner._js_tokens(file.read_text(encoding="utf-8"))
        groups = [[(t.line, t.text[1:-1])] for t in tokens if t.kind == "str"]
    else:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        groups = python_groups(tree)
        quiet = scanner._skipped(tree) | scanner._messages(tree)
        loose = [
            (node.lineno, node.value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in quiet
            and not scanner.CSS_SELECTOR.match(node.value)
            and any(variant in node.value.casefold() for variant in variants)
        ]
    found = [pair for group in groups if any(GERMAN.search(value) for _, value in group) for pair in group]
    seen: set[str] = set()
    for line, value in sorted([*found, *loose]):
        if value not in seen and candidate(path, value):
            seen.add(value)
            print(json.dumps([path, value, line], ensure_ascii=False))
```

```bash
uv run python "$tmp/sweep_candidates.py" > "$tmp/candidates.jsonl"
wc -l < "$tmp/candidates.jsonl"   # 231 on 7293c0d
```

Review every candidate and write the real screen texts, without the line number, to
`"$tmp/inventory.jsonl"` (one `["<file>", "<literal>"]` per line). Of the 155 German-heuristic
candidates on `7293c0d`, five are the server's own messages (the two German `browser.py`
messages, `Anzeigen... item not found in Breakpoints submenu`,
`Could not find 'Methoden'/'Methods' tab`, `Could not find Anzeigen/Display button in SM30`);
the prototype kept the other 150. The 76 loose-value candidates are mostly identifiers and
canonical values (`public`, `program`, `class`, model names) and our own messages; keep the screen
texts among them (`aktiviert`, `deaktiv`, `inaktiv`, `inaktive objekte` / `inactive objects`,
`bereits angemeldet` / `already logged`, `aktive aufrufe`, the activation regex in
`backend/webgui/backend.py`, `abstrakt`, ...).

Then walk these **inventory categories** (spec "Today's ways" and the Problem list) and add what
neither the scanner nor the helper found. Use the greps as a start, not as the whole check:

| Category                                                 | Where to look                                                                                                                                 |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Module-level tuples of message fragments                 | `git grep -nE "^_?[A-Z_]+ = \(" -- src ':!src/sapguimcp/lang'` (activation, error keyword, "no entries" lists)                                |
| Inline regex alternations, `name_de` / `name_en` groups  | `git grep -nE "\(\?:[A-Za-zÄÖÜäöü]+\|[A-Za-z]+\)" -- src ':!src/sapguimcp/lang'`                                                              |
| Lower-case substring checks against other variable names | `git grep -nE '"[a-zäöü ]{4,}" in [a-z_]+(\.lower\(\))?' -- src ':!src/sapguimcp/lang'`                                                       |
| `if language == "DE"` branches                           | `git grep -nE "== \"(DE\|EN)\"\|language ==" -- src ':!src/sapguimcp/lang'`                                                                   |
| Column-header keys outside `row` names                   | `git grep -nE "\.get\(\"[A-ZÄÖÜ][a-zäöü]" -- src ':!src/sapguimcp/lang'`                                                                      |
| English-only screen texts (no German sibling)            | `git grep -nE "\"(Display\|Change\|Create\|Save\|Back\|Cancel\|Continue\|Execute\|Entry\|Information)\b" -- src ':!src/sapguimcp/lang'`       |
| Literals in JS files                                     | every `.js` file under `backend/webgui/js/` (`check_popup.js`, `extract_status_bar.js`, `discover_fields.js`, `read_se16n_selection_rows.js`) |
| Inline JS in Python                                      | `git grep -n "() =>" -- src/sapguimcp/tools src/sapguimcp/backend`                                                                            |
| Catalog DE column fallbacks                              | `src/sapguimcp/catalog/`, `src/sapguimcp/tables/`                                                                                             |
| `breakpoint_tools.py`                                    | the whole file (spec: ~10 sites); every screen literal goes on the baseline                                                                   |

Out of the scan by design (spec Goal): `data/*.json`, `skills/`, `prompts/`, `data/sap_knowledge.md`
and the browser and OS error texts in `backend/webgui/browser.py`.

- [ ] **Step 4: Re-seed from the hits and the inventory**

```bash
uv run python "$tmp/seed_lang_baseline.py" "$tmp/inventory.jsonl"
```

With only the 150 German-heuristic entries the prototype printed `257 detected entries + 150
inventory entries in 33 files` (407 entries, 26 of them in `breakpoint_tools.py`). The
loose-value candidates and Step 3's categories add more; that is expected. The script stops on an
inventory literal that is not a counted literal of its file (a typo, a docstring, an f-string
part that differs).

- [ ] **Step 5: Run** — expected PASS:

```bash
uv run --group tests python -m pytest unittests/test_no_ui_literals.py -q
uv run python unittests/test_no_ui_literals.py --prune && git diff --exit-code unittests/lang_baseline.json
```

- [ ] **Step 6: Lint**, plus prettier on the four JS files (see the testing rules about CRLF) and
      `uv run --group spell_check codespell --ignore-words=domain-specific-terms.txt src`.

- [ ] **Step 7: Commit**

```bash
git add unittests/lang_baseline.json src/sapguimcp/backend/desktop/_tree_helpers.py src/sapguimcp/backend/webgui/browser.py src/sapguimcp/backend/webgui/js/discover_fields.js src/sapguimcp/backend/webgui/js/extract_screen_info.js src/sapguimcp/backend/webgui/js/find_field_utils.js src/sapguimcp/backend/webgui/js/extract_status_bar.js src/sapguimcp/tools/se09_tools.py src/sapguimcp/tables/search.py
git commit -m "test(lang): exempt the scanner's false positives and seed the baseline from the inventory sweep (#1044)"
```

The commit message lists the detected / inventory / total entry counts and any false positive
added beyond the table in Step 1.

---

### Task 5: Final verification (controller)

- [ ] Lint, format and type check on the whole repository (commands in the testing rules), prettier
      on `src/**/*.js`, codespell on `src`.
- [ ] Every unit test touched by 2b, by path:

```bash
uv run --group tests python -m pytest unittests/lang/ unittests/test_sap_config_languages.py unittests/webgui/test_lang_test_pack.py unittests/webgui/test_selectors.py unittests/test_no_ui_literals.py -q -rs
uv run --group tests python -m pytest unittests/webgui/test_popup_integration.py --collect-only -q
```

Prototype: `416 passed, 3 skipped` for the first command (the three `test_selectors.py` skips
that `main` has too).

- [ ] Record the scanner's time from `pytest --durations=5 unittests/test_no_ui_literals.py` for
      the PR (decision 10).
- [ ] `git diff origin/main --stat -- src` lists only `lang/__init__.py` and the 8 files with
      `lang-ok` comments, and `git diff origin/main -- src | grep "^[+-][^+-]" | grep -v "lang-ok\|_register_for_tests\|_clear_caches"`
      shows only the helper's lines.
- [ ] Leak check of the diff before pushing (CLAUDE.md): grep for an internal domain suffix, a
      `<SID>K9…` transport number and a `/XXX/` namespace prefix; the baseline holds literals from
      `src/` only, which is already public.
- [ ] No live tests (decision 12); say so in the PR, with the reason.
- [ ] Continue with the branch's PR workflow (self-review, Copilot review, CI green, ask before
      merging).
