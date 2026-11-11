# Language Pack Sources and JS Texts Implementation Plan (phase 2c of #1044)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The rest of phase 2 of spec §2, §8 and §9 exists and is tested. `Text.for_js()` /
`RegexText.for_js()` give every pack text a JavaScript form, and a Node guard proves that each
pack's JS form compiles and matches its own variants. WebGUI scripts take one object argument built
by `script_arg(...)`, piloted on `set_language_field.js`. WebGUI `_read_page_language` maps
`<html lang>` to an SAP key through the packs. Every pack field has an SAP source entry in
`lang/sources.py`, and `scripts/harvest_lang_texts.py --verify` reports drift between a pack and SAP.

**Architecture:** `lang/text.py` gets a second, JS-only builder next to the Python one: its own
escaper (only the JS syntax characters, because `u` mode rejects identity escapes such as `\ ` or
`\-`), Unicode word boundaries `(?<![\p{L}\p{N}_])…(?![\p{L}\p{N}_])` and the flags `iu` / `u`. A
small `unittests/lang/node_runner.py` runs JS checks in the Node runtime that Playwright already
bundles. `js_helpers.script_arg(texts, **values)` builds `{"texts": {name: for_js()}, **values}`.
`lang.language_for_html_lang(tag)` replaces the phase-1 ISO-equals-SAP shortcut. `lang/sources.py`
holds frozen source-key dataclasses and one `SOURCES` mapping keyed by `iter_leaves` path. The
harvest script turns each key into ABAP SQL on a development-metadata text table and reads it
through the ADT freestyle data preview with `httpx` and `systems.json` credentials.

**Tech Stack:** Python 3.11+, frozen slotted dataclasses, `TypedDict`, `httpx`, `xml.etree`,
Node.js (Playwright's driver), pytest.

Spec: `docs/superpowers/specs/2026-11-10-language-packs-design.md` §2 (rules, "JS"), §8, §9, §11.
Phase 2b (`docs/superpowers/plans/2026-11-11-language-packs-guards.md`) is merged to `main` before
this plan starts; Task 0 checks that. Every code block below was run on a scratch copy of the 2b
branch: ruff, `mypy --strict` and the new unit tests pass.

**Not in 2c:**

- **Phase 3:** moving any other JS literal into a pack. 2c migrates only the convention and one
  pilot script (`set_language_field.js`). The scalar-argument scripts (`check_field_type.js`,
  `get_dropdown_options.js`) and the inline JS in `se16_tools` / `se09_tools` move to the object
  form when their area migrates.
- **Draft mode** of the harvest script (`--draft`) is documented, not implemented: it is only
  useful for a language without a pack, and its output format follows the phase-3 schema.
- **`Template.for_js()`:** no script needs a template; spec §2 lists `for_js` only for `Text`
  and `RegexText`.
- **`lang/README.md`** (the spec §11 recipe) belongs to phase 4 with the `ARCHITECTURE.md` /
  `CONTRIBUTING.md` rule; 2c documents the harvest script in `scripts/README.md` only.
- **A complete `sources.py`.** Task 7 looks up what it can; `Manual("not yet looked up")` is a
  valid entry, and phase 3 refines it while it touches each area.

## Decisions made while planning

1. **The JS escaper escapes exactly `\ ^ $ . * + ? ( ) [ ] { } | /`.** In `u` mode every other
   escaped character is a syntax error (`\ `, `\-`, `\#`, `\&`, `\~`, `\"`), so `re.escape` output
   cannot be reused. `/` is escaped although `new RegExp` does not need it, so a source can also
   be pasted into a regex literal. Variant order and de-duplication match the Python `alt`
   (longest first, case-insensitive de-duplication when folding), so both sides prefer the same
   variant.
2. **No case group in JS.** `fold=True` gives the flags `iu`, `fold=False` gives `u`. Spec §2
   says "flags `iu`"; a case-sensitive text cannot carry `i`, so `u` alone is the only consistent
   reading. Composites that mix case sensitivity stay Python-only (spec §2), so there is no JS
   `alt_of`.
3. **`RegexText.for_js()` translates nothing, it refuses.** A pattern with Python-only or
   differently-behaving syntax (`\b \B \w \W \A \Z \z`, inline flags `(?i` / `(?i:`, `(?P`, `(?#`)
   raises `ValueError` when `for_js()` is called, so the author writes a portable pattern. The
   check runs lazily in `for_js()`, not in `__post_init__`: a Python-only pattern stays legal until
   a script needs it, and the Node guard calls `for_js()` on every pack text anyway. Constructs
   that compile in both engines but differ in detail (`\d`, `\s`) are allowed; SAP numbers and
   spaces behave the same in both.
4. **The guard runs in real Node, not in a Python approximation.** A Python check cannot know
   V8's `u`-mode escape rules (it would have missed the first real finding, decision 6).
   Playwright is a runtime dependency and ships Node with its driver
   (`playwright._impl._driver.compute_driver_executable()`), so the guard has a JS engine wherever
   the unit tests run, including the `unittests.yml` job, without a workflow change. `node` on
   `PATH` is the fallback if the private API moves; with neither, the test is skipped locally and
   **fails** when `CI` is set, so the guard cannot disappear silently. One Node process checks all
   texts (under half a second).
5. **The guard checks more than compiling:** each `Text`'s JS regex must match every one of its own
   variants, for every registered pack, every merged view and the universal view. That catches an
   escaper bug that compiles but matches nothing.
6. **First real finding, fixed in Task 2:** the DE `se11.row_select_full` pattern
   `r"Zum Auswählen[^\"]*Leertaste\."` uses `\"`, an identity escape that Python accepts and JS
   `u` mode rejects. Task 2 rewrites it as `r'Zum Auswählen[^"]*Leertaste\.'` (the same Python
   regex) in `de.py` and `_legacy.py`; the legacy shim test keeps the two equal.
7. **The object argument always has `texts`**, possibly empty, so every script can destructure
   `{ texts, ... }`. `script_arg(texts, **values)` maps the names the script reads to pack texts;
   plain values go next to it as keyword arguments, named as the script names them (camelCase,
   e.g. `dropdownText`). A second `texts` keyword is already a Python `TypeError`, so the helper has
   no check of its own. It returns the dict; callers keep calling
   `self._page.evaluate(load_js(...), arg)`, so no call site changes shape and unit tests keep
   mocking `evaluate`.
8. **The pilot passes `logon_dropdown` as a plain value, not as a `texts` entry.** Spec §8 says
   `set_language_field.js` gets `pack.logon_dropdown`, a `str` the script **writes** into the
   dropdown, not a text it matches; wrapping it in a `Text` only to read `variants[0]` would be
   misleading. The pilot proves the convention (object argument with `texts`, no UI literal left in
   the `.js`, baseline entries deleted); the first `texts` consumer arrives with phase 3. A
   language without a pack falls back to the key itself, as the script did before.
9. **`language_for_html_lang(tag)`** lives in `sapguimcp.lang` (it reads the registry). It matches
   the whole tag first (`zh-tw`, for a future pack whose `html_lang` needs the region), then the
   primary subtag, case-insensitively, with `_` read as `-`. A tag without a pack falls back to the
   upper-cased primary subtag (today's behaviour), so `UnsupportedLanguageError` still names the
   real language instead of silently using the requested one.
10. **Source keys are language-independent**, so there is one `SOURCES` mapping, not one per pack.
    It is keyed by the `iter_leaves` path, the path the completeness and untranslated-field guards
    use. Scalar pack fields (`code`, `html_lang`, `logon_dropdown`, `date_format`) are not leaves
    and have no entry.
11. **`relation`** on every SAP-backed key says whether the pack holds SAP's text (`"equal"`,
    default) or a part of it (`"fragment"`, e.g. `common.not_found` from a message
    `&1 nicht gefunden`). The SQL builders live in the script, not in `sources.py`, so `src/` holds
    no SQL.
12. **The harvest script has its own small ADT client.** The repository has no Python ADT client (it
    reaches SAP through SAP GUI and the WebGUI only), but `systems.json` already holds what the data
    preview needs: the HTTP `host` (sap-mcp-config requires `http://` / `https://`), `client`,
    `user`, `password`, `tls_skip_verify`. The client is about 40 lines on `httpx` (already a
    runtime dependency): CSRF token from `/sap/bc/adt/discovery`, then
    `POST /sap/bc/adt/datapreview/freestyle?rowNumber=100` with the SQL as `text/plain`. A pure
    agent recipe through the sap-adt MCP could not run in the live test suite, which spec §9
    requires for DE and EN. The recipe stays as the fallback for OAuth2 systems: `--print-sql` lists
    the queries, an agent runs them with `run_query` (purpose `development_metadata`) and passes the
    result with `--sap-texts`. The client is untested against SAP until Task 7 / Task 8; if the
    endpoint behaves differently, fix `AdtPreview` there and keep the recipe as the evidence path.
13. **Language filter by subquery:** `SPRSL IN ( SELECT SPRAS FROM T002 WHERE LAISO = 'DE' )`.
    The tables store the 1-character internal key and the data preview may apply the `ISOLA`
    conversion exit on output, so neither a literal `'D'` nor a value read back from `T002` is
    reliable; the subquery compares inside the database.
14. **Every technical ID is checked before it reaches SQL** (`^[A-Z0-9_/]{1,40}$`, language
    `^[A-Z0-9]{2}$`); `S608` is ignored for the script only, with that reason in `pyproject.toml`.
    All tables read are basis metadata (DD04T, D021T, RSMPTEXTS, T100, DD07T, TSTCT, T002), no
    business data, as the SAP API policy requires.
15. **Drift comparison:** `Text` + `equal` uses `Text.equals`; `Text` + `fragment` uses
    `Text.contains` on the SAP text with `&1`..`&4` / `&` blanked; `RegexText` searches; a
    `Template` searches the SAP text with every placeholder filled by a sentinel. A source may
    return several rows (several RSMPTEXTS text types, several D021T rows); one matching row is
    enough. Task 7 may tighten the RSMPTEXTS filter (`TEXTTYPE`) once it has seen real rows.
16. **Task 7 records only sources that verify.** A looked-up source whose SAP text does not match
    the pack is not recorded as drift on day one. It becomes `Manual("SAP text differs: <text>")`
    plus a line in the PR description, because changing a pack text is phase-3 work with fixtures.
    So the live verify test starts green, and later drift is a real signal.
17. **The live verify test is marked `integration` explicitly** (it uses no live SAP GUI fixture,
    so the automatic marker misses it) and skips without `systems.json` or for OAuth2 systems.
    `SAP_HARVEST_SYSTEM` picks a `systems.json` key, the default system otherwise. It opens no SAP
    GUI session, but it is still run only by the controller (live test rules).
18. **Model assignment** follows the controller's rule for this phase: haiku for mechanical work,
    sonnet by default, opus only for the review of the `for_js` escaper design (Task 1).

## Consequences for phase 3 (read before planning it)

- **Moving a JS literal:** put the text into the pack, pass it with
  `script_arg({"name": pack.section.field}, ...)`, read it in JS as
  `new RegExp(texts.name.source, texts.name.flags)` (matching) or `texts.name.variants`
  (clicking, filling), then `--prune` the baseline. Plain values (`language`, a label the caller
  already has) stay keyword arguments.
- **Scalar-argument scripts** (`check_field_type.js`, `get_dropdown_options.js`) switch to
  `(params) => { const { texts, label } = params; ... }` in the PR that gives them texts; change
  every `evaluate` call of that script at once.
- **Inline JS in Python** (`se16_tools`, `se09_tools`) follows the same rule: a function string
  that takes one object argument, called with `script_arg(...)`.
- **Write `RegexText` patterns portably.** `for_js()` refuses `\b` and `\w`, and the Node guard
  fails on identity escapes such as `\"` or `\-` outside a class. Python 3.11 `re` has no `\p{…}`,
  so a word boundary that both sides need is a `Text` with `word=True`, not a regex.
- **New pack fields need a `SOURCES` entry** in the same PR (the completeness test fails
  otherwise). Look the text up with the recipe of Task 7; `Manual("<reason>")` is fine when SAP
  has no source (composed titles, WebGUI framework texts, ST22 section headings).
- **A changed pack text** whose source is not `Manual` must still verify: run
  `uv run python scripts/harvest_lang_texts.py DE --verify` (and EN) and attach the summary line.
- **The `texts` key is reserved** in every script argument.

## Testing rules (read before running anything)

- Run unit tests **by explicit path** (`uv run --group tests python -m pytest unittests/<file> -q`).
  Never run the whole suite, never `-m integration`, never a live test; only the controller runs
  live tests (Task 8). Collecting a live module with `--collect-only` is allowed.
- **Lint and type check** at the end of every task: `uv run --group linting ruff check .`,
  `uv run --group linting ruff format --check .`,
  `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`. Tasks that touch JS
  also run `npx prettier --check "src/**/*.js"`; on a Windows checkout with CRLF line endings,
  prettier reports every file, so compare against an untouched file or check the LF content.
- The script and the new test modules also pass `mypy --strict` checked on their own
  (`MYPYPATH=src uv run --group type_check mypy --strict scripts/harvest_lang_texts.py ...`).
  `unittests/lang/synthetic_pack.py` has known `arg-type` findings from 2b when it is pulled in
  this way; ignore those, do not fix them here.
- Task 7 uses the sap-adt MCP `run_query` only on the development-metadata tables of decision 14,
  with purpose `development_metadata` or `ddic_inspection`. Never on business tables.
- **No internal data** in code, commits or the PR (`CLAUDE.md`): name systems by type and release,
  never by alias, host or client.
- Commit with explicit `git add <paths>`; `git commit -a` skips new files.

## File structure

| File                                                           | Responsibility                                                            |
| -------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Modify `src/sapguimcp/lang/text.py`                            | `JsPattern`, `JsText`, JS escaper and builders, `Text/RegexText.for_js()` |
| Create `unittests/lang/node_runner.py`                         | Node lookup, `run_node`, `check_patterns`                                 |
| Create `unittests/lang/test_text_js.py`                        | escaper rules, refusal of unportable patterns, behaviour in Node          |
| Create `unittests/lang/test_js_pack_guard.py`                  | every pack text compiles in Node and matches its own variants             |
| Modify `src/sapguimcp/lang/de.py`, `_legacy.py`                | portable DE `se11.row_select_full` (decision 6)                           |
| Modify `src/sapguimcp/lang/__init__.py`                        | `language_for_html_lang(tag)`                                             |
| Modify `src/sapguimcp/backend/webgui/js_helpers.py`            | `script_arg(texts, **values)`                                             |
| Modify `src/sapguimcp/backend/webgui/backend.py`               | `_read_page_language` via the packs, pilot call, `_logon_dropdown_text`   |
| Modify `src/sapguimcp/backend/webgui/js/set_language_field.js` | `dropdownText` instead of the `Deutsch` / `English` literals              |
| Modify `unittests/lang_baseline.json`                          | one file entry removed by `--prune`                                       |
| Create `unittests/test_webgui_lang_lookup.py`                  | lookup, `script_arg`, pilot call                                          |
| Create `src/sapguimcp/lang/sources.py`                         | source-key types and `SOURCES`                                            |
| Create `unittests/lang/test_sources.py`                        | completeness and shape of `SOURCES`                                       |
| Create `scripts/harvest_lang_texts.py`                         | `--verify`, `--print-sql`, `--sap-texts`; ADT data-preview client         |
| Create `unittests/lang/harvest_script.py`                      | imports the script for its tests                                          |
| Create `unittests/lang/test_harvest_lang_texts.py`             | SQL, drift, XML parsing, `verify`, CLI, without SAP                       |
| Create `unittests/lang/test_harvest_verify_integration.py`     | live: DE and EN packs match SAP                                           |
| Modify `pyproject.toml`, `scripts/README.md`                   | `S608` ignore for the script; script table row and usage                  |

## Model assignment and order

| Task                                                | Implement                                | Review | Depends on |
| --------------------------------------------------- | ---------------------------------------- | ------ | ---------- |
| 0 branch from `main`, check preconditions           | controller                               | -      | -          |
| 1 `for_js()` escaper and builder, Node runner       | sonnet                                   | opus   | 0          |
| 2 Node guard over every pack, portable DE pattern   | sonnet                                   | sonnet | 1          |
| 3 `language_for_html_lang` in `_read_page_language` | haiku                                    | sonnet | 0          |
| 4 `script_arg` convention and the pilot script      | sonnet                                   | sonnet | 1, 3       |
| 5 `sources.py` and its completeness test            | haiku                                    | sonnet | 0          |
| 6 `harvest_lang_texts.py` verify mode               | sonnet                                   | sonnet | 5          |
| 7 look up real sources for DE/EN (may stay partial) | sonnet                                   | sonnet | 6          |
| 8 final verification and live evidence              | controller (haiku may collect summaries) | -      | 1-7        |

Tasks run in order 0 -> 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8, one agent at a time in one working
tree. Task 4 needs `for_js()` (Task 1) and edits `backend.py` after Task 3. Tasks 5-7 touch other
files and could run in a second worktree, but one shared index makes parallel commits fragile, so
the default is sequential. Task 7 uses the sap-adt MCP and must not run while another agent uses
an SAP connection.

---

### Task 0: Branch from `main` and check the preconditions

Phase 2b is merged, so the work branches from `main`. Stop and report if a check fails.

- [ ] **Step 1: Branch**

```bash
git fetch origin
git switch -c feat/1044-phase2c-sources origin/main
```

- [ ] **Step 2: Check what phases 2a and 2b provide** — every command must succeed:

```bash
grep -n "^def _register_for_tests" src/sapguimcp/lang/__init__.py
grep -n "html_lang: str" src/sapguimcp/lang/schema.py
grep -n '"src/sapguimcp/backend/webgui/js/set_language_field.js"' unittests/lang_baseline.json
grep -c 'Leertaste' src/sapguimcp/lang/de.py src/sapguimcp/lang/_legacy.py   # 1 each, both with [^\"]
grep -n "def _read_page_language" src/sapguimcp/backend/webgui/backend.py
uv run python -c "from playwright._impl._driver import compute_driver_executable as c; print(c()[0])"
git grep -n "for_js\|script_arg\|language_for_html_lang" -- src unittests; test $? -eq 1
test ! -e src/sapguimcp/lang/sources.py
test ! -e scripts/harvest_lang_texts.py
```

If the Playwright line fails, check `node --version` instead and note it in the PR: the guard then
relies on `node` on `PATH` (present on GitHub's `ubuntu-latest` runners).

---

### Task 1: `for_js()` escaper and builder, Node runner

**Files:** modify `src/sapguimcp/lang/text.py`; create `unittests/lang/node_runner.py`,
`unittests/lang/test_text_js.py`.

- [ ] **Step 1: Write the failing tests** — create `unittests/lang/node_runner.py`:

```python
"""Run JavaScript checks in Node for the language-pack guards (#1044, phase 2c).

Prefers the Node runtime that Playwright ships with its driver (always installed: Playwright is a
runtime dependency), then ``node`` on ``PATH``. Without either, the calling test is skipped
locally and fails in CI, so the JS guard cannot vanish silently.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

CHECK_PATTERNS_JS = """
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const results = items.map(({ path, source, flags, matches = [], rejects = [] }) => {
    try {
        const re = new RegExp(source, flags);
        return {
            path,
            error: null,
            missed: matches.filter((s) => !re.test(s)),
            wrongly_matched: rejects.filter((s) => re.test(s)),
        };
    } catch (e) {
        return { path, error: String(e.message), missed: [], wrongly_matched: [] };
    }
});
process.stdout.write(JSON.stringify(results));
"""
"""Reads ``[{path, source, flags, matches, rejects}]`` from stdin, writes one result per item."""


def node_executable() -> str | None:
    """Playwright's bundled Node, else ``node`` on ``PATH``, else ``None``."""
    try:
        from playwright._impl._driver import compute_driver_executable  # noqa: PLC0415  # private API

        node = Path(compute_driver_executable()[0])
        if node.is_file():
            return str(node)
    except (ImportError, AttributeError, IndexError, TypeError):
        pass
    return shutil.which("node")


def run_node(script: str, payload: object) -> Any:
    """Run ``script`` with ``payload`` as JSON on stdin and return its JSON stdout."""
    node = node_executable()
    if node is None:
        if os.environ.get("CI"):
            pytest.fail("no Node.js runtime found; the JS guards must run in CI")
        pytest.skip("no Node.js runtime found")
    result = subprocess.run(  # noqa: S603  # fixed script, our own executable lookup
        [node, "-e", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def check_patterns(items: list[dict[str, object]]) -> list[dict[str, Any]]:
    """Compile each item's ``source``/``flags`` in Node; return only the items with a problem."""
    results: list[dict[str, Any]] = run_node(CHECK_PATTERNS_JS, items)
    return [r for r in results if r["error"] or r["missed"] or r["wrongly_matched"]]
```

and `unittests/lang/test_text_js.py`:

```python
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
```

The last test documents decision 6 with today's DE pattern inline: it must fail in Node. It stays
as the regression test of why the escaper exists after Task 2 fixes the pack.

- [ ] **Step 2: Run them, expect failures** (`AttributeError: 'Text' object has no attribute 'for_js'`):

```bash
uv run --group tests python -m pytest unittests/lang/test_text_js.py -q
```

- [ ] **Step 3: Implement** — apply this diff to `src/sapguimcp/lang/text.py`:

```diff
--- a/src/sapguimcp/lang/text.py
+++ b/src/sapguimcp/lang/text.py
@@ -5,8 +5,11 @@ All three are frozen and slotted. Slotted dataclasses have no ``__dict__``, so d
 sources and compiled patterns come from module-level ``functools.cache`` builders keyed by the
 value's fields.

-Python only. The JavaScript builder (``for_js()``) arrives with the JS object-argument
-convention in phase 2c.
+``Text.for_js()`` and ``RegexText.for_js()`` build the JavaScript form (phase 2c): a plain
+source for ``new RegExp(source, flags)``, Unicode-aware word boundaries and the flags ``iu``.
+Python's ``re.escape`` output is not valid in JS ``u`` mode, JS ``\\b`` is ASCII-only and scoped
+``(?i:…)`` is not portable, so the JS form has its own escaper and builder. ``Template`` has no
+JS form.
 """

 from __future__ import annotations
@@ -14,7 +17,7 @@ from __future__ import annotations
 import re
 from dataclasses import dataclass
 from functools import cache
-from typing import TYPE_CHECKING, Protocol, TypeVar
+from typing import TYPE_CHECKING, Protocol, TypedDict, TypeVar

 if TYPE_CHECKING:
     from collections.abc import Iterator, Mapping
@@ -27,6 +30,26 @@ _DEFAULT_GROUP = r".+?"
 _TRAILING_GROUP = r'[^"\n]+'  # stops at an ARIA snapshot's closing quote
 """A placeholder that ends a variant captures the whole rest of the line, not a lazy fragment."""

+_JS_SYNTAX = re.compile(r"[\\^$.*+?()[\]{}|/]")
+"""Characters to escape in a JS ``u``-mode regex. Escaping anything else (space, ``-``, ``#``) is an error."""
+_JS_WORD = r"[\p{L}\p{N}_]"
+"""A JS word character. JS ``\\w`` and ``\\b`` are ASCII-only even with the ``u`` flag."""
+_JS_UNPORTABLE = re.compile(r"(?<!\\)(?:\\\\)*(?:\\[AZzbBwW]|\(\?[aiLmsux-]|\(\?P|\(\?#)")
+"""Python regex syntax that JS rejects or reads differently: anchors, ASCII-only classes, inline flags."""
+
+
+class JsPattern(TypedDict):
+    """The JS form of a pattern: ``new RegExp(source, flags)``."""
+
+    source: str
+    flags: str
+
+
+class JsText(JsPattern):
+    """The JS form of a :class:`Text`: the pattern plus the literal variants for clicking or filling."""
+
+    variants: list[str]
+

 class HasAlt(Protocol):
     """Anything that renders as a regex alternation group to embed into a larger regex.
@@ -103,6 +126,31 @@ def compiled(source: str) -> re.Pattern[str]:
     return re.compile(source)


+def _js_flags(fold: bool) -> str:
+    return "iu" if fold else "u"
+
+
+@cache
+def js_literal_source(variants: tuple[str, ...], fold: bool, word: bool) -> str:
+    """JS regex source of literal variants: same order as :func:`literal_alt`, no case group."""
+    ordered = sorted(_unique(variants, fold), key=len, reverse=True)
+    body = "|".join(_JS_SYNTAX.sub(r"\\\g<0>", variant) for variant in ordered)
+    if word:
+        return f"(?<!{_JS_WORD})(?:{body})(?!{_JS_WORD})"
+    return body
+
+
+@cache
+def js_regex_source(patterns: tuple[str, ...]) -> str:
+    """JS regex source of raw patterns; ``ValueError`` for Python-only syntax."""
+    for pattern in patterns:
+        if _JS_UNPORTABLE.search(pattern):
+            raise ValueError(
+                f"pattern is not portable to JavaScript (\\b, \\w, \\A, \\Z, inline flags, (?P, (?#): {pattern!r}"
+            )
+    return "|".join(f"(?:{pattern})" for pattern in _unique(patterns, fold=False))
+
+
 def _literal_source(literal: str, fold: bool) -> str:
     """Scoped regex for one literal part of a template; whitespace runs match any whitespace."""
     if not literal:
@@ -201,6 +249,14 @@ class Text:
         """Compiled :attr:`alt`."""
         return compiled(self.alt)

+    def for_js(self) -> JsText:
+        """JS form for a script's ``texts`` argument: ``new RegExp(t.source, t.flags)``, ``t.variants``."""
+        return {
+            "source": js_literal_source(self.variants, self.fold, self.word),
+            "flags": _js_flags(self.fold),
+            "variants": list(self.variants),
+        }
+

 @dataclass(frozen=True, slots=True)
 class RegexText:
@@ -233,6 +289,10 @@ class RegexText:
         """Compiled :attr:`alt`."""
         return compiled(self.alt)

+    def for_js(self) -> JsPattern:
+        """JS form for a script's ``texts`` argument; ``ValueError`` for Python-only syntax."""
+        return {"source": js_regex_source(self.patterns), "flags": _js_flags(self.fold)}
+

 @dataclass(frozen=True, slots=True)
 class Template:
```

- [ ] **Step 4: Run the tests, expect them to pass**, plus the 2a value-type tests:

```bash
uv run --group tests python -m pytest unittests/lang/test_text_js.py unittests/lang/test_text.py -q
```

- [ ] **Step 5: Lint, type check, commit**

```bash
git add src/sapguimcp/lang/text.py unittests/lang/node_runner.py unittests/lang/test_text_js.py
git commit -m "feat(lang): Text.for_js() and RegexText.for_js() with a JS escaper, checked in Node (#1044)"
```

**Review focus (opus):** the escaper set against the ECMAScript `u`-mode grammar
(`SyntaxCharacter` plus `/`), the unportable-syntax regex (even and odd backslash runs), word
boundaries for variants that start or end with punctuation, and whether `i`+`u` case folding
differs from Python `lower()` in a way the packs would hit (`ß`/`ẞ`, Turkish dotless i).

---

### Task 2: Node guard over every pack, portable DE pattern

**Files:** create `unittests/lang/test_js_pack_guard.py`; modify `src/sapguimcp/lang/de.py`,
`src/sapguimcp/lang/_legacy.py`.

- [ ] **Step 1: Write the guard** — `unittests/lang/test_js_pack_guard.py`:

```python
"""Guard: every pack text has a JS form that compiles in Node and matches its own variants (#1044, 2c)."""

from sapguimcp import lang
from sapguimcp.lang.schema import PackLike, iter_leaves
from sapguimcp.lang.text import RegexText, Text
from unittests.lang.node_runner import check_patterns


def _items() -> list[dict[str, object]]:
    views: list[tuple[str, PackLike]] = [(code, lang.pack_for(code)) for code in lang.supported_languages()]
    views += [(f"{code} view", lang.view_for(code)) for code in lang.supported_languages()]
    views.append(("universal", lang.universal()))
    items: list[dict[str, object]] = []
    for name, pack in views:
        for path, leaf in iter_leaves(pack):
            if isinstance(leaf, Text):
                items.append({**leaf.for_js(), "path": f"{name}: {path}", "matches": list(leaf.variants)})
            elif isinstance(leaf, RegexText):
                items.append({**leaf.for_js(), "path": f"{name}: {path}"})
    return items


def test_every_pack_text_compiles_in_javascript() -> None:
    assert check_patterns(_items()) == []
```

- [ ] **Step 2: Run it, expect exactly two findings**, `DE: se11.row_select_full` and
      `DE view: se11.row_select_full`, both `Invalid escape`:

```bash
uv run --group tests python -m pytest unittests/lang/test_js_pack_guard.py -q
```

Any other finding: stop and report it with the Node error; do not loosen the guard.

- [ ] **Step 3: Fix the pattern** — in `src/sapguimcp/lang/de.py` (`row_select_full=`) and in
      `src/sapguimcp/lang/_legacy.py` (`SE11_ROW_SELECT_FULL_DE`), replace
      `r"Zum Auswählen[^\"]*Leertaste\."` with `r'Zum Auswählen[^"]*Leertaste\.'`. Python reads
      both as the same regex; JS accepts only the second.

- [ ] **Step 4: Run the guard, the legacy shim and the pack tests**:

```bash
uv run --group tests python -m pytest unittests/lang/test_js_pack_guard.py unittests/lang/test_legacy_shim.py unittests/lang/test_packs.py -q
```

- [ ] **Step 5: Lint, type check, commit**

```bash
git add unittests/lang/test_js_pack_guard.py src/sapguimcp/lang/de.py src/sapguimcp/lang/_legacy.py
git commit -m "test(lang): every pack text compiles in JavaScript; portable DE row-select pattern (#1044)"
```

---

### Task 3: `language_for_html_lang` in `_read_page_language`

**Files:** modify `src/sapguimcp/lang/__init__.py`, `src/sapguimcp/backend/webgui/backend.py`
(only `_read_page_language` and its imports); create `unittests/test_webgui_lang_lookup.py` with
the lookup tests.

- [ ] **Step 1: Write the failing tests** — create `unittests/test_webgui_lang_lookup.py` with the
      module docstring, the imports `pytest`, `from sapguimcp import lang` and
      `from unittests.lang.synthetic_pack import synthetic_pack`, and the two
      `test_language_for_html_lang*` tests of the final file shown in Task 4, Step 1. Run it; expect
      `AttributeError: module 'sapguimcp.lang' has no attribute 'language_for_html_lang'`.

- [ ] **Step 2: Implement** — apply to `src/sapguimcp/lang/__init__.py`:

```diff
--- a/src/sapguimcp/lang/__init__.py
+++ b/src/sapguimcp/lang/__init__.py
@@ -9,6 +9,7 @@ Public API:
 - :data:`INVARIANT` - texts that are the same in every logon language (an :class:`Invariant`).
 - :func:`use` / :func:`set_session_language` - set the session language (tests, login).
 - :func:`pack_for`, :func:`supported_languages` - the registry.
+- :func:`language_for_html_lang` - the SAP language key for a page's ``<html lang>``.
 - ``_register_for_tests`` - registers an extra pack inside a ``with`` block (tests only).

 The ``X_DE`` / ``X_EN`` constants and ``bilingual_pattern`` of the former ``lang.py`` module are
@@ -50,6 +51,7 @@ __all__ = [
     "UnsupportedLanguageError",
     "alt_of",
     "current",
+    "language_for_html_lang",
     "pack_for",
     "set_session_language",
     "supported_languages",
@@ -99,6 +101,22 @@ def pack_for(code: str) -> LanguagePack:
     return pack


+def language_for_html_lang(tag: str) -> str | None:
+    """SAP language key for an HTML language tag (``"de-DE"`` -> ``"DE"``).
+
+    Matches the registered packs' ``html_lang``: the whole tag first (``zh-tw``), then the primary
+    subtag (``de``), case-insensitively, ``_`` read as ``-``. A tag without a pack falls back to
+    its upper-cased primary subtag, so an unsupported language is still reported by name; an empty
+    tag gives ``None``.
+    """
+    normalized = tag.strip().lower().replace("_", "-")
+    if not normalized:
+        return None
+    primary = normalized.split("-", 1)[0]
+    by_html_lang = {pack.html_lang.lower(): pack.code for pack in _PACKS.values()}
+    return by_html_lang.get(normalized) or by_html_lang.get(primary) or normalize_language(primary)
+
+
 def _build_view(code: str) -> LanguagePack:
     """Merge each section per its ``MERGE`` mode; scalar pack fields come from the session pack."""
     session = _PACKS[code]
```

In `backend.py`: the last line of `_read_page_language` becomes
`return language_for_html_lang(value)`, its docstring becomes
`"""SAP logon language from the page's ``<html lang>``, mapped through the packs' ``html_lang``."""`,
`language_for_html_lang` is imported from `sapguimcp.lang`, and the now unused
`normalize_language` import goes. (Task 4, Step 3 shows the complete `backend.py` diff of both
tasks.)

- [ ] **Step 3: Run the new tests and the existing page-language tests**:

```bash
uv run --group tests python -m pytest unittests/test_webgui_lang_lookup.py unittests/test_webgui_session_language.py unittests/lang/test_registry.py -q
```

`test_read_page_language_maps_iso_code_to_sap_key` (`de-DE` -> `DE`) must pass unchanged.

- [ ] **Step 4: Lint, type check, commit**

```bash
git add src/sapguimcp/lang/__init__.py src/sapguimcp/backend/webgui/backend.py unittests/test_webgui_lang_lookup.py
git commit -m "feat(webgui): map <html lang> to the SAP language key through the language packs (#1044)"
```

---

### Task 4: `script_arg` convention and the pilot script

**Files:** modify `src/sapguimcp/backend/webgui/js_helpers.py`,
`src/sapguimcp/backend/webgui/backend.py`, `src/sapguimcp/backend/webgui/js/set_language_field.js`,
`unittests/lang_baseline.json`, `unittests/test_webgui_lang_lookup.py`.

- [ ] **Step 1: Write the failing tests** — `unittests/test_webgui_lang_lookup.py` becomes:

```python
"""``<html lang>`` lookup and the script argument convention for the WebGUI (#1044, phase 2c)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sapguimcp import lang
from sapguimcp.backend.webgui.backend import WebGuiBackend, _logon_dropdown_text
from sapguimcp.backend.webgui.js_helpers import load_js, script_arg
from sapguimcp.lang.text import RegexText, Text
from unittests.lang.synthetic_pack import synthetic_pack


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("de", "DE"), ("de-DE", "DE"), ("EN_us", "EN"), (" en ", "EN"), ("fr-FR", "FR"), ("", None), ("  ", None)],
)
def test_language_for_html_lang(tag: str, expected: str | None) -> None:
    assert lang.language_for_html_lang(tag) == expected


def test_language_for_html_lang_uses_registered_packs() -> None:
    pack = synthetic_pack()
    with lang._register_for_tests(pack):
        assert lang.language_for_html_lang(f"{pack.html_lang}-YY") == pack.code


def test_script_arg_converts_texts_and_keeps_values() -> None:
    arg = script_arg({"hint": Text(("Hinweis",)), "row": RegexText(("a+",))}, label="Feld", count=2)
    assert arg == {
        "texts": {
            "hint": {"source": "Hinweis", "flags": "iu", "variants": ["Hinweis"]},
            "row": {"source": "(?:a+)", "flags": "iu"},
        },
        "label": "Feld",
        "count": 2,
    }


def test_script_arg_always_has_texts() -> None:
    assert script_arg(language="DE") == {"texts": {}, "language": "DE"}


def test_logon_dropdown_text_comes_from_the_pack() -> None:
    assert _logon_dropdown_text("DE") == "Deutsch"
    assert _logon_dropdown_text("EN") == "English"
    assert _logon_dropdown_text("FR") == "FR"


def test_set_language_field_has_no_ui_literal() -> None:
    script = load_js("set_language_field.js")
    assert "Deutsch" not in script
    assert "English" not in script
    assert "dropdownText" in script


@pytest.mark.anyio
async def test_login_passes_the_dropdown_text_to_the_script() -> None:
    page = MagicMock()
    for name in ("goto", "wait_for_load_state", "query_selector", "wait_for_selector", "fill", "evaluate", "click"):
        setattr(page, name, AsyncMock(return_value=object()))
    backend = WebGuiBackend.__new__(WebGuiBackend)
    backend._page = page
    with (
        patch.object(WebGuiBackend, "_find_okcode_field", new=AsyncMock(return_value=None)),
        patch.object(WebGuiBackend, "_post_login_setup", new=AsyncMock()),
    ):
        await backend.login("https://sap.example", "u", "p", "100", "DE")
    script, arg = page.evaluate.await_args_list[0].args
    assert script == load_js("set_language_field.js")
    assert arg == {"texts": {}, "language": "DE", "dropdownText": "Deutsch"}
```

Run it; expect `ImportError: cannot import name 'script_arg'`.

- [ ] **Step 2: Implement the helper** — `src/sapguimcp/backend/webgui/js_helpers.py` becomes:

```python
"""JavaScript file loading helpers for the WebGUI backend.

Every script takes one object argument (Playwright ``evaluate`` accepts exactly one). Build it with
:func:`script_arg`: language-dependent texts go under ``texts`` in their JS form, plain values next
to it (#1044, spec section 8).
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sapguimcp.lang.text import JsPattern, RegexText, Text


@lru_cache(maxsize=16)
def load_js(filename: str) -> str:
    """Load a JavaScript file from the sapguimcp.backend.webgui.js package."""
    return resources.files("sapguimcp.backend.webgui.js").joinpath(filename).read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def load_js_with_field_utils(filename: str) -> str:
    """Load a JS file with find_field_utils.js prepended."""
    utils = load_js("find_field_utils.js")
    tool = load_js(filename)
    return utils + "\n" + tool


def script_arg(texts: Mapping[str, Text | RegexText] | None = None, **values: object) -> dict[str, object]:
    """The single object argument of a WebGUI script: ``{"texts": {...}, **values}``.

    ``texts`` maps the names the script reads (``texts.<name>.source`` / ``.flags`` /
    ``.variants``) to pack texts; each is converted with ``for_js()``. ``texts`` is always present,
    possibly empty, so every script can destructure ``{ texts, ... }``.
    """
    js_texts: dict[str, JsPattern] = {name: text.for_js() for name, text in (texts or {}).items()}
    return {"texts": js_texts, **values}
```

- [ ] **Step 3: Use it in the backend** — the complete `backend.py` diff of Tasks 3 and 4; apply
      the part Task 3 has not applied yet:

```diff
--- a/src/sapguimcp/backend/webgui/backend.py
+++ b/src/sapguimcp/backend/webgui/backend.py
@@ -17,9 +17,10 @@ from urllib.parse import urlparse
 from playwright.async_api import Error as PlaywrightError

 from sapguimcp.backend.webgui.browser import get_browser_manager
-from sapguimcp.backend.webgui.js_helpers import load_js, load_js_with_field_utils
+from sapguimcp.backend.webgui.js_helpers import load_js, load_js_with_field_utils, script_arg
 from sapguimcp.backend.webgui.types import AriaSnapshot
 from sapguimcp.backend.webgui.utils import escape_css_selector, is_sap_shortcut
+from sapguimcp.lang import UnsupportedLanguageError, language_for_html_lang, pack_for
 from sapguimcp.middleware.logging import set_sap_identity
 from sapguimcp.models.alv_models import AlvCellInfo, AlvMetadata, TableCellClickResult
 from sapguimcp.models.base import CheckActivateResult, PopupButton, PopupInfo
@@ -46,7 +47,7 @@ from sapguimcp.models.sap_results import (
     TableRow,
     TransactionResult,
 )
-from sapguimcp.session_language import normalize_language, set_session_language
+from sapguimcp.session_language import set_session_language

 if TYPE_CHECKING:
     from playwright.async_api import Page
@@ -103,6 +104,14 @@ def _parse_toolbar_note(snapshot_text: str) -> tuple[bool, str]:
 # ---------------------------------------------------------------------------


+def _logon_dropdown_text(language: str) -> str:
+    """Text of the logon page's language dropdown for ``language``; the key itself without a pack."""
+    try:
+        return pack_for(language).logon_dropdown
+    except UnsupportedLanguageError:
+        return language
+
+
 class WebGuiBackend:  # pylint: disable=too-many-public-methods
     """WebGUI backend using Playwright browser automation.

@@ -247,11 +256,7 @@ class WebGuiBackend:  # pylint: disable=too-many-public-methods
         await self._capture_sap_identity(effective_url, mandant, session_id)

     async def _read_page_language(self) -> str | None:
-        """SAP logon language from the page's ``<html lang>`` (ISO code, e.g. ``de``).
-
-        Phase 1 of #1044: ISO and SAP keys coincide for DE and EN. Phase 2 maps ISO codes to SAP
-        keys through the language packs' ``html_lang``.
-        """
+        """SAP logon language from the page's ``<html lang>``, mapped through the packs' ``html_lang``."""
         try:
             value = await self._page.evaluate("() => document.documentElement.lang || ''")
         except Exception:  # pylint: disable=broad-exception-caught
@@ -259,7 +264,7 @@ class WebGuiBackend:  # pylint: disable=too-many-public-methods
             return None
         if not isinstance(value, str):  # e.g. a mocked page
             return None
-        return normalize_language(value.split("-")[0])
+        return language_for_html_lang(value)

     async def login(  # pylint: disable=too-many-arguments,too-many-positional-arguments,unused-argument
         self,
@@ -321,7 +326,7 @@ class WebGuiBackend:  # pylint: disable=too-many-public-methods
             try:
                 await self._page.evaluate(
                     load_js("set_language_field.js"),
-                    {"language": language},
+                    script_arg(language=language, dropdownText=_logon_dropdown_text(language)),
                 )
                 logger.debug("Set language field", extra={"language": language})
             except Exception as lang_err:  # pylint: disable=broad-exception-caught
```

- [ ] **Step 4: Migrate the pilot script** — `src/sapguimcp/backend/webgui/js/set_language_field.js`
      becomes:

```javascript
(params) => {
    const { language, dropdownText } = params;

    // Set hidden language input
    const hiddenField = document.querySelector('#sap-language, input[name="sap-language"]');
    if (hiddenField) {
        hiddenField.value = language;
        hiddenField.dispatchEvent(new Event('input', { bubbles: true }));
        hiddenField.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // Also update the visible dropdown display; the text comes from the language pack
    const dropdown = document.querySelector('#sap-language-dropdown');
    if (dropdown) {
        dropdown.value = dropdownText;
    }
};
```

- [ ] **Step 5: Shrink the baseline** — the scanner finds neither literal in the file any more:

```bash
uv run python unittests/test_no_ui_literals.py --prune
git diff unittests/lang_baseline.json   # exactly the set_language_field.js entry removed (4 lines)
```

- [ ] **Step 6: Run the tests**:

```bash
uv run --group tests python -m pytest unittests/test_webgui_lang_lookup.py unittests/test_webgui_session_language.py unittests/test_no_ui_literals.py -q
npx prettier --check src/sapguimcp/backend/webgui/js/set_language_field.js
```

- [ ] **Step 7: Lint, type check, commit**

```bash
git add src/sapguimcp/backend/webgui/js_helpers.py src/sapguimcp/backend/webgui/backend.py \
  src/sapguimcp/backend/webgui/js/set_language_field.js unittests/lang_baseline.json unittests/test_webgui_lang_lookup.py
git commit -m "feat(webgui): one object argument per script via script_arg; set_language_field.js reads the pack (#1044)"
```

---

### Task 5: `sources.py` and its completeness test

**Files:** create `src/sapguimcp/lang/sources.py`, `unittests/lang/test_sources.py`.

- [ ] **Step 1: Write the test** — `unittests/lang/test_sources.py`:

```python
"""``lang/sources.py``: one SAP source per pack field (#1044, phase 2c)."""

import dataclasses

import pytest

from sapguimcp import lang
from sapguimcp.lang.schema import iter_leaves
from sapguimcp.lang.sources import SOURCES, Manual, Message
from sapguimcp.lang.text import Template


def _paths(code: str) -> set[str]:
    return {path for path, _leaf in iter_leaves(lang.pack_for(code))}


@pytest.mark.parametrize("code", lang.supported_languages())
def test_every_pack_field_has_exactly_one_source(code: str) -> None:
    paths = _paths(code)
    assert sorted(paths - set(SOURCES)) == [], "add a source (or Manual) for these fields"
    assert sorted(set(SOURCES) - paths) == [], "these sources name fields that do not exist"


def test_every_manual_source_names_a_reason() -> None:
    assert [path for path, source in SOURCES.items() if isinstance(source, Manual) and not source.reason.strip()] == []


def test_sourced_keys_are_upper_case_technical_ids() -> None:
    for path, source in SOURCES.items():
        if isinstance(source, Manual):
            continue
        for field in dataclasses.fields(source):
            value = getattr(source, field.name)
            if field.name not in {"length", "relation"}:
                assert value == value.strip().upper(), f"{path}: {field.name}={value!r}"


def test_templates_come_from_messages_or_are_manual() -> None:
    en = dict(iter_leaves(lang.pack_for("EN")))
    for path, leaf in en.items():
        if isinstance(leaf, Template):
            assert isinstance(SOURCES[path], Message | Manual), path
```

Run it; expect `ModuleNotFoundError: No module named 'sapguimcp.lang.sources'`.

- [ ] **Step 2: Create `sources.py`** exactly as below. The mapping lists **every** path of
      `iter_leaves(EN)` in that order (78 on today's schema), each as `NOT_LOOKED_UP`. Generate
      the entry lines with this command from the repository root; they replace the `"common.display"` line
      and the comment line after it. Commit no generator:

```bash
uv run python -c "from sapguimcp.lang import EN; from sapguimcp.lang.schema import iter_leaves; print(''.join(f'        \"{p}\": NOT_LOOKED_UP,\n' for p, _ in iter_leaves(EN)), end='')"
```

```python
"""Where each pack text comes from in SAP (#1044, spec section 9).

Every field of a language pack (every path of :func:`sapguimcp.lang.schema.iter_leaves`) has one
entry in :data:`SOURCES`. The key names a technical ID in one of SAP's development-metadata text
tables; the text itself differs per logon language, the key does not, so one mapping serves every
pack. ``scripts/harvest_lang_texts.py`` reads the keys to compare a pack with SAP (verify) or to
draft a new pack (draft).

A text without an SAP source is :class:`Manual` with a reason: composed titles, WebGUI framework
texts, texts nobody has looked up yet.

``relation`` says how the pack text relates to SAP's text: ``"equal"`` (the pack holds SAP's text)
or ``"fragment"`` (the pack holds a part of it, e.g. "not found" of a message "&1 not found").
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

Relation = Literal["equal", "fragment"]
DataElementLength = Literal["short", "medium", "long", "heading"]


@dataclass(frozen=True, slots=True)
class DataElement:
    """Data element text (``DD04T``): field labels, column headers."""

    name: str
    length: DataElementLength
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class ScreenText:
    """Screen element text (``D021T``): screen texts, tabs, radio button and checkbox texts."""

    program: str
    screen: str
    field: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class GuiFunction:
    """GUI status function text (``RSMPTEXTS``): buttons, menu entries."""

    program: str
    fcode: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class Message:
    """Message text (``T100``): status-bar messages. ``&1`` .. ``&4`` and ``&`` are placeholders."""

    message_class: str
    number: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class DomainValue:
    """Domain fixed-value text (``DD07T``), e.g. a job status."""

    domain: str
    value: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class Transaction:
    """Transaction title (``TSTCT``)."""

    tcode: str
    relation: Relation = "equal"


@dataclass(frozen=True, slots=True)
class Manual:
    """No SAP source; the reason says why (or "not yet looked up")."""

    reason: str


Source = DataElement | ScreenText | GuiFunction | Message | DomainValue | Transaction | Manual

NOT_LOOKED_UP = Manual("not yet looked up")

SOURCES: Mapping[str, Source] = MappingProxyType(
    {
        "common.display": NOT_LOOKED_UP,
        # ... one line per remaining iter_leaves(EN) path, in order ...
    }
)
"""Source of every pack field, keyed by its :func:`~sapguimcp.lang.schema.iter_leaves` path."""
```

- [ ] **Step 3: Run the test, expect it to pass**, plus the synthetic-language guards:

```bash
uv run --group tests python -m pytest unittests/lang/test_sources.py unittests/lang/test_synthetic_language.py -q
```

- [ ] **Step 4: Lint, type check, commit**

```bash
git add src/sapguimcp/lang/sources.py unittests/lang/test_sources.py
git commit -m "feat(lang): sources.py records the SAP source of every pack field (#1044)"
```

---

### Task 6: `harvest_lang_texts.py` verify mode

**Files:** create `scripts/harvest_lang_texts.py`, `unittests/lang/harvest_script.py`,
`unittests/lang/test_harvest_lang_texts.py`, `unittests/lang/test_harvest_verify_integration.py`;
modify `pyproject.toml`, `scripts/README.md`.

- [ ] **Step 1: Write the tests** — `unittests/lang/harvest_script.py`:

```python
"""Imports ``scripts/harvest_lang_texts.py`` (not a package) for its tests (#1044, phase 2c)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "harvest_lang_texts.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("harvest_lang_texts", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


harvest = _load()
```

`unittests/lang/test_harvest_lang_texts.py`:

```python
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
```

and the live test `unittests/lang/test_harvest_verify_integration.py` (collected, not run, in
this task):

```python
"""Live: the DE and EN packs match SAP's texts for every sourced field (#1044, spec section 9).

Reads development-metadata text tables through ADT data preview (no SAP GUI session). Marked
``integration`` explicitly: it uses no live SAP GUI fixture, so the automatic marker misses it.
``SAP_HARVEST_SYSTEM`` selects a ``systems.json`` key; the default system otherwise.
"""

import os

import pytest
from sap_mcp_config import load_default

from sapguimcp.lang import supported_languages
from unittests.lang.harvest_script import harvest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("language", ["DE", "EN"])
def test_pack_matches_sap(language: str) -> None:
    try:
        config = load_default(supported_languages=supported_languages())
    except Exception as exc:  # no systems.json on this machine
        pytest.skip(f"no SAP configuration: {exc}")
    system = config.systems[os.environ.get("SAP_HARVEST_SYSTEM") or config.default_system]
    if system.is_oauth2:
        pytest.skip("OAuth2 system: run the --print-sql / --sap-texts recipe instead")
    preview = harvest.AdtPreview.for_system(system)
    findings = harvest.verify(language, lambda _path, source: preview.query(harvest.sql_for(source, language)))
    assert findings == {}
```

Run the unit tests; expect `FileNotFoundError` for the script.

- [ ] **Step 2: Write the script** — `scripts/harvest_lang_texts.py`:

```python
"""Compare a language pack with SAP's own texts (#1044, spec section 9). DEVELOPMENT USE ONLY.

Usage::

    uv run python scripts/harvest_lang_texts.py DE --verify [--system <key>]
    uv run python scripts/harvest_lang_texts.py DE --verify --sap-texts texts.json
    uv run python scripts/harvest_lang_texts.py DE --print-sql

``--verify`` reads every non-``Manual`` source of ``sapguimcp.lang.sources.SOURCES`` for the
language and reports each pack field whose text no longer matches SAP ("drift"). It reads only
development-metadata text tables (DD04T, D021T, RSMPTEXTS, T100, DD07T, TSTCT, T002) through the
ADT data-preview endpoint ``/sap/bc/adt/datapreview/freestyle``, as the SAP API policy allows for
development tooling. Credentials come from ``systems.json`` (sap-mcp-config); OAuth2 systems are
not supported here. For them, ``--print-sql`` lists one query per field: run each through the
sap-adt MCP ``run_query`` tool (purpose ``development_metadata``), save ``{path: [text, ...]}`` as
JSON and pass it with ``--sap-texts``.

Draft mode (``--draft``, writing a new ``<lang>.py``) is specified in spec section 9 and not
implemented yet. Exit code: 0 without drift, 1 with drift, 2 on usage errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sap_mcp_config import load_default

from sapguimcp.lang import pack_for, supported_languages
from sapguimcp.lang.schema import Leaf, iter_leaves
from sapguimcp.lang.sources import (
    SOURCES,
    DataElement,
    DomainValue,
    GuiFunction,
    Manual,
    Message,
    ScreenText,
    Source,
    Transaction,
)
from sapguimcp.lang.text import RegexText, Template

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from sap_mcp_config.models import SAPSystem

_TECHNICAL_ID = re.compile(r"^[A-Z0-9_/]{1,40}$")
_LANGUAGE_KEY = re.compile(r"^[A-Z0-9]{2}$")
_T100_PLACEHOLDER = re.compile(r"&\d?")
_PLACEHOLDER_FILL = "ZZPLACEHOLDER"
_DD04T_COLUMN = {"short": "SCRTEXT_S", "medium": "SCRTEXT_M", "long": "SCRTEXT_L", "heading": "REPTEXT"}
_PREVIEW_PATH = "/sap/bc/adt/datapreview/freestyle"
_PREVIEW_NS = "{http://www.sap.com/adt/dataPreview}"


def _id(value: str) -> str:
    """A technical ID, checked before it goes into a SQL literal."""
    if not _TECHNICAL_ID.match(value):
        raise ValueError(f"not a technical ID: {value!r}")
    return value


def sql_for(source: Source, language: str) -> str:
    """ABAP SQL that returns the source's text(s) in ``language`` (a 2-character SAP key)."""
    if not _LANGUAGE_KEY.match(language):
        raise ValueError(f"not an SAP language key: {language!r}")
    lang = f"IN ( SELECT SPRAS FROM T002 WHERE LAISO = '{language}' )"
    match source:
        case DataElement(name=name, length=length):
            return (
                f"SELECT {_DD04T_COLUMN[length]} FROM DD04T WHERE ROLLNAME = '{_id(name)}'"
                f" AND AS4LOCAL = 'A' AND DDLANGUAGE {lang}"
            )
        case ScreenText(program=program, screen=screen, field=field):
            return (
                f"SELECT DTXT FROM D021T WHERE PROG = '{_id(program)}' AND DYNR = '{_id(screen)}'"
                f" AND FLDN = '{_id(field)}' AND LANG {lang}"
            )
        case GuiFunction(program=program, fcode=fcode):
            return (
                f"SELECT TEXT FROM RSMPTEXTS WHERE PROGNAME = '{_id(program)}' AND OBJ_TYPE = 'F'"
                f" AND OBJ_CODE = '{_id(fcode)}' AND SPRSL {lang}"
            )
        case Message(message_class=message_class, number=number):
            return (
                f"SELECT TEXT FROM T100 WHERE ARBGB = '{_id(message_class)}' AND MSGNR = '{_id(number)}'"
                f" AND SPRSL {lang}"
            )
        case DomainValue(domain=domain, value=value):
            return (
                f"SELECT DDTEXT FROM DD07T WHERE DOMNAME = '{_id(domain)}' AND DOMVALUE_L = '{_id(value)}'"
                f" AND AS4LOCAL = 'A' AND DDLANGUAGE {lang}"
            )
        case Transaction(tcode=tcode):
            return f"SELECT TTEXT FROM TSTCT WHERE TCODE = '{_id(tcode)}' AND SPRSL {lang}"
        case Manual():
            raise ValueError("a Manual source has no SQL")


def drift(leaf: Leaf, source: Source, sap_texts: Sequence[str]) -> str | None:
    """``None`` if one of SAP's texts matches the pack text, else a one-line finding."""
    if isinstance(source, Manual):
        return None
    texts = [text.strip() for text in sap_texts if text.strip()]
    if not texts:
        return "SAP has no text for this source"
    for text in texts:
        if isinstance(leaf, Template):
            matched = leaf.search(_T100_PLACEHOLDER.sub(_PLACEHOLDER_FILL, text)) is not None
        elif isinstance(leaf, RegexText):
            matched = leaf.pattern.search(text) is not None
        elif source.relation == "fragment":
            matched = leaf.contains(_T100_PLACEHOLDER.sub(" ", text))
        else:
            matched = leaf.equals(text)
        if matched:
            return None
    return f"SAP says {texts!r}"


def parse_preview(xml_text: str) -> list[str]:
    """First-column values of an ADT data-preview response, one per row."""
    root = ET.fromstring(xml_text)  # noqa: S314  # response of the configured SAP system
    columns = root.findall(f"{_PREVIEW_NS}columns")
    if not columns:
        return []
    return [data.text or "" for data in columns[0].iter(f"{_PREVIEW_NS}data")]


@dataclass
class AdtPreview:
    """Minimal client for the ADT freestyle data preview (development-metadata tables only)."""

    client: httpx.Client
    csrf_token: str = ""

    @classmethod
    def for_system(cls, system: SAPSystem) -> AdtPreview:
        if system.is_oauth2:
            raise SystemExit("OAuth2 systems are not supported; use --print-sql and --sap-texts")
        client = httpx.Client(
            base_url=system.host,
            auth=(system.user, system.password.get_secret_value()),
            params={"sap-client": system.client},
            verify=not system.tls_skip_verify,
            timeout=60,
        )
        return cls(client)

    def query(self, sql: str) -> list[str]:
        if not self.csrf_token:
            response = self.client.get("/sap/bc/adt/discovery", headers={"x-csrf-token": "fetch"})
            response.raise_for_status()
            self.csrf_token = response.headers.get("x-csrf-token", "")
        response = self.client.post(
            _PREVIEW_PATH,
            params={"rowNumber": "100"},
            content=sql.encode("utf-8"),
            headers={
                "x-csrf-token": self.csrf_token,
                "Content-Type": "text/plain",
                "Accept": "application/xml, application/vnd.sap.adt.datapreview.table.v1+xml",
            },
        )
        response.raise_for_status()
        return parse_preview(response.text)


def verify(language: str, fetch: Callable[[str, Source], Sequence[str]]) -> dict[str, str]:
    """Drift findings by field path for ``language``; ``fetch(path, source)`` returns SAP's texts."""
    pack = pack_for(language)
    findings: dict[str, str] = {}
    for path, leaf in iter_leaves(pack):
        source = SOURCES[path]
        if isinstance(source, Manual):
            continue
        finding = drift(leaf, source, fetch(path, source))
        if finding is not None:
            findings[path] = finding
    return findings


def _fetch_from_file(texts: Mapping[str, Sequence[str]]) -> Callable[[str, Source], Sequence[str]]:
    return lambda path, _source: texts.get(path, ())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("language", type=str.upper)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true")
    mode.add_argument("--print-sql", action="store_true")
    mode.add_argument("--draft", action="store_true")
    parser.add_argument("--system", help="systems.json key (default: default_system)")
    parser.add_argument("--sap-texts", type=Path, help="JSON {path: [text, ...]} collected via run_query")
    args = parser.parse_args(argv)
    if args.draft:
        parser.error("--draft is not implemented yet (spec section 9)")
    if args.print_sql:
        for path, source in SOURCES.items():
            if not isinstance(source, Manual):
                print(f"{path}\t{sql_for(source, args.language)}")
        return 0
    if args.sap_texts is not None:
        fetch = _fetch_from_file(json.loads(args.sap_texts.read_text(encoding="utf-8")))
    else:
        config = load_default(supported_languages=supported_languages())
        preview = AdtPreview.for_system(config.systems[args.system or config.default_system])
        fetch = lambda _path, source: preview.query(sql_for(source, args.language))  # noqa: E731
    findings = verify(args.language, fetch)
    for path, finding in findings.items():
        print(f"DRIFT {path}: {finding}")
    checked = sum(not isinstance(source, Manual) for source in SOURCES.values())
    print(f"{args.language}: {checked} sourced fields checked, {len(findings)} drifted")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: `pyproject.toml`** — add after the `"scripts/explore_issue_717.py"` line of
      `[tool.ruff.lint.per-file-ignores]`:

```toml
"scripts/harvest_lang_texts.py" = ["S608"] # hardcoded-sql-expression: every value is checked against a technical-ID regex first
```

- [ ] **Step 4: `scripts/README.md`** — add a row to the overview table
      (`harvest_lang_texts.py` | Compare a language pack with SAP's own texts | After an SAP
      upgrade, after changing a sourced pack text, before adding a language) and a short section
      with the three usages from the script docstring, the OAuth2 recipe and the note that
      `--draft` is specified in spec §9 but not implemented.

- [ ] **Step 5: Run the unit tests and collect the live test**:

```bash
uv run --group tests python -m pytest unittests/lang/test_harvest_lang_texts.py -q
uv run --group tests python -m pytest unittests/lang/test_harvest_verify_integration.py --collect-only -q   # 2 tests
uv run --group tests python -m pytest unittests/lang/test_harvest_verify_integration.py --collect-only -q -m "not integration"   # 0 selected
uv run python scripts/harvest_lang_texts.py DE --print-sql   # prints nothing yet: every source is Manual
MYPYPATH=src uv run --group type_check mypy --strict scripts/harvest_lang_texts.py unittests/lang/harvest_script.py unittests/lang/test_harvest_lang_texts.py
```

- [ ] **Step 6: Lint, type check, commit**

```bash
git add scripts/harvest_lang_texts.py scripts/README.md pyproject.toml unittests/lang/harvest_script.py \
  unittests/lang/test_harvest_lang_texts.py unittests/lang/test_harvest_verify_integration.py
git commit -m "feat(scripts): harvest_lang_texts.py --verify compares a pack with SAP's text tables (#1044)"
```

---

### Task 7: Look up real sources for the DE/EN fields (may stay partial)

**Files:** modify `src/sapguimcp/lang/sources.py` (entries only; `sql_for` only if Step 1 requires
it). Tools: the sap-adt MCP `run_query` (purpose `development_metadata` or `ddic_inspection`),
`get_table_fields` to confirm columns, `select_system` to switch systems. Budget: about one hour of
agent time; stop when it runs out and leave the rest as `NOT_LOOKED_UP`.

- [ ] **Step 1: Confirm the columns** with `get_table_fields` for DD04T, D021T, RSMPTEXTS, T100,
      DD07T, TSTCT. If a column differs from `sql_for` (e.g. RSMPTEXTS needs a `TEXTTYPE` filter),
      fix `sql_for` and its test first, in a separate commit.

- [ ] **Step 2: Look up field by field, cheapest first:** `sm37.status[*]` (`DomainValue` on the
      job-status domain, confirmed in DD07T), the `*.initial_screen` and other transaction titles
      (`Transaction`), field labels and column headers (`DataElement`: search DD04T by the EN
      text, e.g. `SELECT ROLLNAME, SCRTEXT_M FROM DD04T WHERE DDLANGUAGE = 'E' AND SCRTEXT_M =
  'Table Name'`, then confirm that the DE text of the same `ROLLNAME` is the DE pack variant),
      status-bar texts (`Message`: search T100 by text), then screen texts and buttons
      (`ScreenText`, `GuiFunction`) for the screens the tools read. Search by the pack text, do
      not guess IDs.

- [ ] **Step 3: Record only what verifies** (decision 16). Keep an entry when both the DE and the
      EN pack match SAP under `drift()` on both systems. If SAP's text differs, record
      `Manual("SAP text differs: <SAP text>")` and add a line to the PR description. Texts with no
      SAP source get a specific reason: `Manual("WebGUI framework text")`,
      `Manual("composed title")`, `Manual("ST22 section heading, generated")`. Use
      `relation="fragment"` where the pack holds only a part of SAP's text.

- [ ] **Step 4: Verify through the script's recipe** (the sap-adt MCP may use OAuth2):

```bash
uv run python scripts/harvest_lang_texts.py DE --print-sql > <tmp>/de.sql   # <tmp> outside the repository
```

Run each query with `run_query`, write `{path: [text, ...]}` to `<tmp>/de.json`, then:

```bash
uv run python scripts/harvest_lang_texts.py DE --verify --sap-texts <tmp>/de.json   # expect "0 drifted"
```

Same for EN, on both systems (the S/4HANA and the ECC system). Report the summary lines and how
many fields are still `NOT_LOOKED_UP`.

- [ ] **Step 5: Run the unit tests, lint, type check, commit**

```bash
uv run --group tests python -m pytest unittests/lang/test_sources.py unittests/lang/test_harvest_lang_texts.py -q
git add src/sapguimcp/lang/sources.py
git commit -m "feat(lang): SAP sources for the DE/EN pack fields that verify on both systems (#1044)"
```

---

### Task 8: Final verification (controller)

- [ ] **Step 1: Unit tests of everything 2c touches**, by path:

```bash
uv run --group tests python -m pytest unittests/lang/ unittests/test_webgui_lang_lookup.py \
  unittests/test_webgui_session_language.py unittests/test_no_ui_literals.py unittests/test_sap_config_languages.py \
  unittests/webgui/test_lang_test_pack.py -q -m "not integration"
```

- [ ] **Step 2: Lint, format, type check, prettier** (commands in "Testing rules"), and confirm
      that the baseline diff against `main` is removals only:

```bash
git diff origin/main -- unittests/lang_baseline.json | grep '^+ ' ; test $? -eq 1
```

- [ ] **Step 3: Live evidence on both systems** (VPN up, nobody else on SAP), each with
      `SAP_LANGUAGE=DE` and `SAP_LANGUAGE=EN`:

```bash
uv run --group tests python -m pytest unittests/webgui/test_login_integration.py -q -k "test_sap_login or test_page_reports_the_logon_language"
uv run --group tests python -m pytest unittests/lang/test_harvest_verify_integration.py -q   # SAP_HARVEST_SYSTEM per system
```

Paste the literal pytest summary lines into the PR and explain every skip (the harvest test skips
on an OAuth2 system; attach the Task 7, Step 4 recipe output instead).

- [ ] **Step 4: Before pushing**, grep the diff for an internal domain suffix, a `<SID>K9…`
      transport number and a `/XXX/` namespace prefix (`CLAUDE.md`); the PR names systems by type
      and release only.

- [ ] **Step 5: Open the PR** with the decisions to check (decisions 2, 3, 4, 8, 12 and 16), the
      Task 7 coverage (`sourced / 78`), the `SAP text differs` list and the live evidence.
      Self-review, Copilot review, CI green, then ask before merging.
