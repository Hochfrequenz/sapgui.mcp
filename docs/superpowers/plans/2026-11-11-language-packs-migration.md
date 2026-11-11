# Language packs, phase 3: migrate every call site — implementation plan (#1044)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax
> for tracking.

**Goal:** move every remaining SAP-language-dependent literal of `src/sapguimcp` into the DE/EN
packs (or delete it in favour of a technical ID, spec §7), one PR per area, until
`unittests/lang_baseline.json` holds nothing but the off-limits `breakpoint_tools.py`.

**Spec:** `docs/superpowers/specs/2026-11-10-language-packs-design.md` (rollout phase 3, §5, §7, §8,
model table). **Prerequisites:** phases 1, 2a, 2b and 2c are merged to `main`; read their
"Consequences for phase 3" sections (`2026-11-11-language-packs-core.md`,
`2026-11-11-language-packs-guards.md`, `2026-11-11-language-packs-sources.md`) once before the
first area.

**Out of scope, in every area:**

- `src/sapguimcp/tools/breakpoint_tools.py` stays untouched (off-limits, see #1025). Its 32
  baseline keys (37 occurrences) stay in `lang_baseline.json` after phase 3; phase 4 documents them
  as the one remaining exception.
- Popup handling behaviour stays identical. Popup texts move into the `popup` section of the packs
  (merge mode `all`), but which popups are detected, closed or confirmed, and in which order, must
  not change. No popup rework is proposed or accepted in review.
- Deleting `lang.py` / `_legacy.py`, `bilingual_pattern` and `bilingual_target` is phase 4. An
  area stops _using_ them; it does not delete them.

---

## Part 1 — Overview: the per-area recipe

Every area PR follows the same recipe. The detailed tasks of Part 2 are this recipe applied to the
pilot area; the short sections of Part 3 name what differs per area.

### R0. Branch

- [ ] `git fetch origin && git worktree add ../sapgui.mcp-<area> -b feat/1044-phase3-<area> origin/main`.
      One area per branch, always from a fresh `main` (the previous area merged first, so baseline
      prunes and pack additions never conflict).
- [ ] Read the area's files and its baseline entries:
      `python -c "import json;d=json.load(open('unittests/lang_baseline.json'));print(d['<path>'])"`.

### R1. Prefer no text (§7 first)

- [ ] For each literal, check for a language-independent alternative before moving it: technical
      field names (`GD-TAB`), `lsdata` / `ct` attributes, CSS classes, column `Name`, program and
      dynpro (`ScreenInfo.program` / `.dynpro`), T100 message IDs (`StatusBarInfo.message_id` /
      `.message_number`, as `sap_tools._TRANSACTION_NOT_FOUND_MESSAGE` does). Apply the area's rows
      of the spec §7 table.
- [ ] `ScreenInfo.program` / `.dynpro` are filled on the desktop only (`session.info`); the WebGUI
      `extract_screen_info.js` leaves them empty. A check that must work on both backends cannot rest
      on them; a desktop-only check can (the SE11 initial screen is `SAPLSD_ENTRY` / `1000` on both
      releases, so it needs no pack field).
- [ ] A message ID replaces a text only if it is the same on both systems **for every case the code
      handles**. SE11 "does not exist" is `E2` / `503` for a table on the S/4HANA system but `E2` / `007`
      on the ECC system (a structure: `E2` / `007` on both), so SE11 keeps the pack text. SE16N "No values
      found" is `WUSL` / `002` on both.
- [ ] A §7 deletion that the spec marks "needs a live check" is gated: read the technical value on
      **both** systems first (`sap_com_evaluate` on the desktop, a snapshot on WebGUI), write the
      observed values into the PR description, then code. If the values differ between releases or
      are missing on one system, keep a pack text instead and say so in the PR.

### R2. Move the texts into the packs

- [ ] Add fields to the area's section in `src/sapguimcp/lang/schema.py` (every field required,
      no defaults) and fill them in `de.py` and `en.py`. Reuse `common.*` where the text already
      exists there (spec: "Display" 5×, "not found" 6×); never add a second copy.
- [ ] Choose the type: `Text` for literals (clicking, filling, `contains` / `equals`,
      `first_key`), `RegexText` for real patterns (portable: no `\b`, `\w`, identity escapes;
      word boundaries via `Text(..., word=True)`), `Template` for titles with placeholders,
      canonical mappings (`canonical({Enum.X: Text(...)})`) for status maps.
- [ ] Add one `SOURCES` entry per new field in `src/sapguimcp/lang/sources.py` (`Message`,
      `DataElement`, `ScreenText`, `GuiFunction`, or `Manual("<reason>")`). Look texts up with the
      phase-2c recipe (ADT `run_query` on `T100`, `DD04T`, `D021T`, `RSMPTEXTS`, `DD07T`,
      `TSTCT` — development metadata only). Fix drifted texts the lookup reveals.
- [ ] Right after adding the pack values run `uv run --group tests pytest unittests/test_no_ui_literals.py -q`.
      The value rule flags literals of **other** files that contain a new variant of five or more
      characters as a whole word (short values like `Table`, `Empty`, `entries` hit own messages such as
      `"label cannot be empty"`). Fix those hits right away: `# lang-ok: our own message` on the line of
      the literal (a trailing comment after the closing parenthesis of a wrapped call is moved there by
      `ruff format`; put it on the literal's own line), or, where the file is off-limits or the literal is
      real UI text of a later area, one baseline entry with a sentence in the PR.
- [ ] A pack field that no call site uses any more is deleted together with its `SOURCES` entry, its
      legacy constants in `_legacy.py` and the `LEGACY_PATHS` row of `unittests/lang/test_legacy_shim.py`
      (tests that used it as an arbitrary `RegexText` take another field).
- [ ] A screen label that the lookup shows with different texts per dynpro (SE16N `TEXTMAX`: `Max. Number of
Hits` on dynpro 0120/0220, `Maximum no. of hits` on dynpro 0100, which the ECC system shows) gets
      every variant into the pack; source: the field on the dynpro both releases have.
- [ ] Changed or added non-`Manual` fields must verify:
      `uv run python scripts/harvest_lang_texts.py DE --verify` and `... EN --verify` on both
      systems; paste the summary lines into the PR.

### R3. Rewrite the call sites

- [ ] Resolve the pack once per tool call in the caller: `t = lang.current("<tool name>")`, then
      use `t.<section>.<field>`. Never call `lang.current()` inside a COM worker closure; close
      over `t` (spec §5 convention).
- [ ] Thread `t` as an explicit parameter into every function that matches screen text, public parser
      functions included (`parse_se16_*`, `_parse_se11_*`), and update all callers, also those in other
      packages (`tables/scraper.py`). Resolve `t` **before** any `try` / `except Exception` that wraps the
      call (batch loops, best-effort helpers): `UnsupportedLanguageError` must reach the caller, not
      become a per-item error. Desktop paths that no longer match any text need no `t` at all.
- [ ] Popup, status-type, session-page and key-name checks use `lang.universal()` (session-free,
      works before login and on unsupported languages).
- [ ] Module-level compiled patterns that embed a text move into a function taking `t` and use
      `text.compiled(source)` (cached by source string).
- [ ] Inline JS that embeds a pack regex source groups the alternation:
      `'^(?:(?:' + params.texts.empty.source + ')\\\\s*)+$'` (a source with several variants is `a|b`;
      without the inner group the anchors bind to the first and last variant only). In a non-raw Python
      string `\\\\s` reaches JS as `\\s`, which the JS string turns into the regex `\s`.
- [ ] Replacement table (spec "Today's ways"):

    | Today                                            | After                                                           |
    | ------------------------------------------------ | --------------------------------------------------------------- |
    | `for label in [X_DE, X_EN]` / inline tuples      | `for label in t.sec.field`                                      |
    | `bilingual_pattern(X_DE, X_EN)`                  | `t.sec.field.alt`, several fields: `lang.alt_of(a, b)`          |
    | `"x" in s.lower() or "y" in s.lower()`           | `t.sec.field.contains(s)`                                       |
    | exact comparison `s in (X_DE, X_EN)`             | `t.sec.field.equals(s)`                                         |
    | `row.get("Methode", row.get("Method"))`          | `t.sec.field.first_key(row)`                                    |
    | `bilingual_target(radios_de=..., radios_en=...)` | `SelectionScreenState(radios=dict.fromkeys(t.sec.f, True))`     |
    | JS literal                                       | `script_arg({"name": t.sec.field}, ...)`, JS reads `texts.name` |
    | `if language == "DE":` branch                    | iterate the `Text`                                              |

- [ ] **Matching semantics:** `Text` defaults to `fold=True, word=False`, i.e. a case-insensitive
      substring test. Where the old code compared exactly (`==`, `in (tuple)`, dict lookup) use
      `.equals()`; where it anchored or needed a whole word, declare the field with `word=True`.
      A review checks every rewritten comparison for this.
- [ ] Merged views (`session_en`) append EN variants to the DE pack: a DE session also matches EN
      texts. That reproduces today's "try DE, then EN" loops; do not add EN fallbacks by hand.

### R4. Tests

- [ ] Every unit test that reaches a migrated function now needs a language: take the `lang_de` /
      `lang_en` fixtures from `unittests/conftest.py` (they yield the merged view), or
      `with lang.use("DE"):`. Without it the test fails with `UnsupportedLanguageError` — that is
      the intended behaviour, not a bug to work around.
- [ ] Parametrize parser/snapshot tests over both languages where DE and EN fixtures exist.
- [ ] Add a test per fixed single-language bug (written first, failing on `main`).
- [ ] Inline JS held in a Python string is tested without a browser: `unittests/lang/node_runner.run_node`
      with a fake `document` (grids and rows as plain objects with `querySelector` / `textContent`); see
      `test_grid_padding_rows_are_not_data_rows` in `unittests/lang/test_se11_se16_pack.py`.
- [ ] Fixtures named `*_en.yaml` are not always EN twins of the DE ones (`se11_t000_fields_en.yaml` is the
      initial screen). Check before parametrizing; otherwise relabel the DE snapshot in the test.
- [ ] Write non-ASCII separators in test data as `\u00a0` / `\u202f` escapes (ruff `RUF001`), and let a
      test that needs both languages take `lang_de` **and** `lang_en` (the EN session does not match DE
      texts: only the DE session merges EN in).
- [ ] Test-only texts go into the test pack (`UiTestPack`), DE and EN at once. Live tests touched
      by the area that still branch on `os.environ["SAP_LANGUAGE"]` move their texts there.

### R5. Prune the baseline

- [ ] `uv run --group tests python unittests/test_no_ui_literals.py --prune`, commit the shrunk
      `lang_baseline.json` with the migration. The area's files must leave the baseline entirely,
      except lines marked `# lang-ok: <reason>` (only for non-UI strings such as tool parameter
      values; never on a line that still holds screen text).
- [ ] The one allowed baseline addition: new pack variants make the value rule flag a literal in a
      file outside the area. Prefer `# lang-ok: our own message` (R2); move the literal if it is UI text;
      add that single entry with a sentence in the PR only for off-limits files and real UI text of a later
      area. Pilot: 2 entries (`breakpoint_tools.py`, the SM37 job log heading); the baseline went from
      491 / 636 to 446 / 576 (distinct / occurrences).
      Any other growth is a review finding.

### R6. Verify

- [ ] Unit tests by explicit path (`uv run pytest unittests/<files> -q`) plus the guards:
      `uv run pytest unittests/lang unittests/test_no_ui_literals.py -q`.
- [ ] `uv run mypy src`, `uv run pylint` on changed files, `uv run ruff check`, `npx prettier --check`
      on changed docs.
- [ ] Live tests of the area on **both** systems (S/4HANA and ECC), desktop and — where the area
      has a WebGUI path — WebGUI. One run at a time on the single SAP connection. Paste the literal
      pytest summary lines; explain every skip; rerun a failure alone and compare with `main`
      before treating it as real (spec "Risks").
- [ ] Live-test the area's single-language bug fixes in the language that was broken.

### R7. PR

- [ ] PR title `feat(lang): migrate <area> to the language packs (#1044)`; description lists moved
      fields, §7 deletions (with live evidence), fixed bugs, behaviour changes, baseline delta
      (entries before → after), verify summaries, live summaries.
- [ ] No internal data in the PR (CLAUDE.md): systems by type and release only, no aliases,
      hosts, transport numbers or partner namespaces. An independent agent checks the text before
      posting.
- [ ] Self-review → reviewer agent (model below) → Copilot review → CI green. **At most two
      review rounds**; anything left after round two becomes a follow-up issue linked in the PR.
      Merging needs a second human approver.

### Area order, size and models

Counts are from `unittests/lang_baseline.json` on the phase-2c branch: distinct literals /
occurrences.

| #   | Area                                                       | Files on baseline                                                                                                                                                                                         | Entries   | Implement | Review |
| --- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | --------- | ------ |
| 1   | SE11/SE16 (pilot, done: see Part 2)                        | `se11_tools.py` 24/29, `se16_tools.py` 16/26, `read_se16n_selection_rows.js` 7/7 (+ `se16_parser.py`, legacy imports only)                                                                                | 47 / 62   | sonnet    | opus   |
| 2   | status bar / popups / session pages / keys (backends + JS) | `desktop/__init__.py` 27/28, `_com_thread.py` 2/2, `webgui/backend.py` 24/24, `check_popup.js` 9/9, `discover_fields.js` 1/1, `extract_status_bar.js` 18/20, `field_helpers.py` 10/10, `sap_tools.py` 1/1 | 92 / 95   | opus      | fable  |
| 3   | SE24/SE37/SE38 (+ edit tools)                              | `se24_tools.py` 32/46, `se24_edit_tools.py` 15/21, `se37_tools.py` 17/19, `se37_edit_tools.py` 2/3, `se38_edit_tools.py` 9/14, `se24_parser.py` 4/5, `se37_parser.py` 2/2                                 | 81 / 110  | sonnet    | opus   |
| 4   | SE09/SE93                                                  | `se09_tools.py` 16/37, `se93_tools.py` 3/3, `se09_parser.py` 7/9, `se93_parser.py` 2/2                                                                                                                    | 28 / 51   | sonnet    | sonnet |
| 5   | SM30/SPRO                                                  | `sm30_parser.py` 9/9 (+ `sm30_tools.py`, `spro_tools.py`, `spro_parser.py`, legacy imports only)                                                                                                          | 9 / 9     | sonnet    | sonnet |
| 6   | SM37/SLG1/ST22                                             | `sm37_tools.py` 37/70, `slg1_tools.py` 20/35, `st22_tools.py` 44/46, `sm37_parser.py` 15/17, `slg1_parser.py` 3/3, `st22_parser.py` 21/21                                                                 | 140 / 192 | sonnet    | sonnet |
| 7   | abapGit / quick report                                     | `abapgit_tools.py` 43/61, `quick_report_tools.py` 12/12                                                                                                                                                   | 55 / 73   | sonnet    | sonnet |
| 8   | catalogs and data files                                    | `catalog/models.py` 3/3, `catalog/scraper.py` 3/3, `tables/scraper.py` 1/1 (+ `data/sap_field_registry.json`, not scanned)                                                                                | 7 / 7     | haiku     | sonnet |
| —   | `breakpoint_tools.py` (off-limits, stays)                  | 32/37                                                                                                                                                                                                     | —         | —         | —      |

Total today: 491 distinct / 636 occurrences in 35 files; after phase 3: 32 / 37 in one file.

Model rules (spec model table): running tests and collecting summaries is haiku; diagnosing a
failing live test is sonnet; §7 deletions that need a live check (popup close selectors, column
`Name`, T100 IDs) are sonnet with an opus review in whichever area they fall; an agent that fails
twice or a review that finds a design problem escalates the task one level. The leak and fact check
of every public PR text is opus.

**Why SE11/SE16 is the pilot, not the popup area:**

- It is the smallest area that still exercises every part of the recipe: a schema section that
  already exists, `common.*` reuse, a `bilingual_target` replacement, module-level regexes that
  move to call time, inline JS in Python (`_wait_for_grid_rows`), a JS file (`script_arg`), two
  §7 deletions (desktop label fallbacks, SE16N grid detection), one live-gated §7 deletion
  (column `Name`), a single-language bug (SE16 thousands separator) and both backends.
- Its blast radius is two tools. The popup / status-bar area touches every tool call of both
  backends and must keep popup behaviour bit-for-bit identical; it should run once the recipe,
  the fixtures and the review checklist have been validated on a low-risk area, and it gets the
  strongest models.
- SE11/SE16 has stable live tests on both backends (`unittests/{desktop,webgui}/test_se1{1,6}_integration.py`).
- Lessons from the pilot (recipe gaps, fixture friction, scanner false positives) are written
  back into Part 1 of this plan in the pilot PR, before area 2 starts.

Area 2 follows the pilot directly because every later area reads the status bar and closes popups
through it; migrating it early means later areas never touch its texts.

### Behaviour changes to call out (in the PR of the area that causes them)

- **SM37 / SLG1 / ST22 (area 6):** a tool call on a session whose language is unknown or has no
  pack now raises `UnsupportedLanguageError` instead of falling back to the default system's
  language (or collapsing to EN). Live-test both: a call without a known session language, and one
  on a session in a language without a pack (if no such system exists, a unit test with
  `lang.use("XX")` and a sentence in the PR).
- **Looser or stricter matching:** every site that moves from an exact comparison to
  `Text.contains` would match more; such sites use `.equals()` or `word=True` instead. Sites that
  were substring checks before stay `.contains()`. Each PR lists the sites where matching
  semantics changed on purpose.
- **Shared `common.*` texts can widen a match:** e.g. `common.does_not_exist` holds three DE
  variants where SE11/SE16 checked one. Each PR names such widenings; they are accepted when the
  extra variants are SAP messages with the same meaning.
- **Merged views:** a DE session also matches EN texts (secondary-language fallback). Where the
  old code checked DE only (the single-language bugs), this is the fix.
- **Desktop row keys (areas 1 and 3):** switching internal parsers to `Columns(c).Name` changes
  the keys of the internal row dicts; tool outputs must stay identical (asserted by the live
  tests).

### Single-language bugs per area (spec "Problem")

| Bug                                                                     | Area |
| ----------------------------------------------------------------------- | ---- |
| SE16 hit count accepts only `.` as thousands separator                  | 1    |
| `extract_status_bar.js` noise filter DE only                            | 2    |
| `discover_fields.js` dropdown check DE only (→ §7: `ct === 'CB'`)       | 2    |
| `check_popup.js` lacks `yes`/`no`                                       | 2    |
| `sap_tools.parse_shortcut_from_title` returns `Strg+S` (localized keys) | 2    |
| SE24 visibility / static / constant match EN only                       | 3    |
| SE09 `region "Liste"` DE only                                           | 4    |
| desktop SM37 status not normalised (→ canonical `JobStatus` mapping)    | 6    |
| SM37 and ST22 tools and parsers use different "no entries" lists        | 6    |
| `SLG1_NO_LOGS_FOUND_EN` drifted from message BL 208                     | 6    |
| abapGit EN initial-screen check `"Entry"` never matches                 | 7    |

---

## Part 2 — Area 1 in detail: SE11/SE16 (pilot)

**Files:**

- Modify: `src/sapguimcp/tools/se11_tools.py`, `src/sapguimcp/tools/se16_tools.py`,
  `src/sapguimcp/backend/webgui/parsers/se16_parser.py`,
  `src/sapguimcp/backend/webgui/js/read_se16n_selection_rows.js`,
  `src/sapguimcp/tools/table_helpers.py` (Task 3, only if the live check passes),
  `src/sapguimcp/lang/schema.py`, `de.py`, `en.py`, `sources.py`, `unittests/lang_baseline.json`
- Tests: `unittests/webgui/test_se11_parser.py`, `unittests/webgui/test_se16_parser.py`,
  `unittests/test_se11_readiness.py`, `unittests/test_se11_desktop_key_flags.py`,
  `unittests/test_se16_filter_scrolling.py`, `unittests/test_se16_filter_warnings.py`,
  `unittests/test_se16_webgui_filters.py`; new `unittests/lang/test_se11_se16_pack.py`
- Live: `unittests/desktop/test_se11_integration.py`, `unittests/desktop/test_se16_integration.py`,
  `unittests/webgui/test_se11_integration.py`, `unittests/webgui/test_se16_integration.py`

**Baseline entries removed** (all of them; the three files leave `lang_baseline.json`):

- `se11_tools.py` (24 keys / 29): `Data Type`, `Data type` ×2, `Database table`,
  `Datenbanktabelle`, `Datentyp` ×2, `Dec.Pl.`, `Decimal Places`, `Decimals`, `Dez.St.`,
  `DezStellen`, `Feld`, `Feldname`, `Field`, `Field Name`, `Field name`, `Key`,
  `Kurzbeschreibung`, `Length`, `Länge`, `Short Description`, `Short text`, `Table name` ×2,
  `einstieg` ×2, `initial` ×2
- `se16_tools.py` (16 keys / 26): `/^(Leer\s*)+$/`, `Max. Number of Hits` ×2,
  `Maximale Trefferzahl` ×2, `Tabelle` ×5, `Table` ×5, `does not exist`, `entries`,
  `existiert nicht`, `hits`, `input[title*='Tabelle'], input[aria-label*='Tabelle']`,
  `input[title*='Table'], input[aria-label*='Table']`, `keine einträge`, `keine werte`,
  `no entries`, `no values`, `treffer`
- `read_se16n_selection_rows.js` (7 / 7): `Feldname`, `Field Name`, `From Value`, `From-Value`,
  `Selection Criteria`, `Selektionskriterien`, `Von-Wert`

Additionally all `SE11_*` / `SE16_*` legacy imports in the three Python files go away (not on the
baseline because they are imports, but phase 4 can only delete `lang.py` once nobody imports it).

### Task 0: Branch and read

- [ ] R0 with `<area>` = `se11-se16`.
- [ ] Read the "Consequences for phase 3" sections of the 2a/2b/2c plans.
- [ ] Run the area's unit tests on the fresh branch and record the summary (baseline for later
      comparison): `uv run pytest unittests/webgui/test_se11_parser.py unittests/webgui/test_se16_parser.py unittests/test_se11_readiness.py unittests/test_se11_desktop_key_flags.py unittests/test_se16_filter_scrolling.py unittests/test_se16_filter_warnings.py unittests/test_se16_webgui_filters.py -q`.

### Task 1: Live lookups for the §7 deletions (sonnet, before any code)

**Result of the pilot (S/4HANA system = SAP S/4HANA 2025, ECC system = SAP ERP 6.0 EHP8):**

| Lookup                                      | S/4HANA system                                                                                                                                                                | ECC system                                     | Decision                                        |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- | ----------------------------------------------- |
| SE11 initial screen, `session.info`         | `SAPLSD_ENTRY` / `1000`                                                                                                                                                       | `SAPLSD_ENTRY` / `1000`                        | technical value; no `initial_screen`            |
| SE11 display screen                         | `SAPLSD41` / `2200`                                                                                                                                                           | `SAPLSD41` / `2200`                            | (not needed)                                    |
| WebGUI `get_screen_info()` program / dynpro | empty (`extract_screen_info.js`)                                                                                                                                              | empty                                          | desktop-only check                              |
| SE11 field list `Columns(c).Name`           | `DD03D-FIELDNAME`, `DD03P-KEYFLAG`, `DD03D-DATATYPE`, `DD03P-LENG`, `DD03P-DECIMALS`, `DD03P-DDTEXT` (+ `DD03P-NOTNULL`, `DD03D-ROLLNAME`, `DD03P-SRS_ID`, `DD03P-GROUPNAME`) | the same six (no `SRS_ID`)                     | technical names, `column_keys="name"`           |
| SE11 not found after F7, table              | `E2` / `503`, type S                                                                                                                                                          | `E2` / `007`, type S                           | differs: keep the pack text                     |
| SE11 not found after F7, structure          | `E2` / `007`                                                                                                                                                                  | `E2` / `007`                                   | (same text path as the table)                   |
| SE16N no hits after F8                      | `WUSL` / `002`, type E                                                                                                                                                        | `WUSL` / `002`, type E                         | message ID                                      |
| SE16N selection grid `Columns(c).Name`      | `GS_SELFIELDS-SCRTEXT_M`, `OPTION`, `GS_SELFIELDS-LOW`, `GS_SELFIELDS-HIGH`, `PUSH`, `GS_SELFIELDS-MARK`, `GS_SELFIELDS-FIELDNAME`                                            | the same                                       | (WebGUI detection stays text-based, see Task 5) |
| SE16N program / dynpro                      | `SAPLSE16N` / `0120` (table at `subTAB_SUB:SAPLSE16N:0121`)                                                                                                                   | `SAPLSE16N` / `0100` (table directly in `usr`) | differs; not used                               |
| SE16N label fields in `D021T`               | `SEARCHTAB`, `TEXTMAX` on 0100 and 0120                                                                                                                                       | `SEARCHTAB`, `TEXTMAX` on 0100                 | source `ScreenText(.., "0100", ..)`             |
| SE11 data-type name input `title` (WebGUI)  | `Name des Dictionary Typs` / `Name of Dictionary Type` (snapshots)                                                                                                            | confirmed by the live tests                    | `se11.data_type_name_label`                     |

`GD-TAB` is not a `D021T` label: the table label is `SEARCHTAB`, the max-hits label `TEXTMAX`.

Read on **both** systems, desktop, and note the values for the PR:

- [ ] SE11 data-type name input on WebGUI: its exact `title` attribute (see Task 4,
      `_fill_structure_name_field`).
- [ ] SE11 initial screen: `session.info.program` / `session.info.screen_number` on the initial
      screen and on the display screen (expected `SAPLSD_ENTRY` / `1000` on the initial screen;
      confirm on ECC). Also check whether WebGUI `get_screen_info()` fills `program` / `dynpro`.
- [ ] SE11 field list table control: `Columns(c).Name` for every column (expected technical names
      of the `DD03P`-style structure: field name, data element/type, length, decimals, short text,
      key flag — record the exact strings, they may differ between the two releases).
- [ ] SE11 "object does not exist" after F7 and SE16N "no values found" after F8:
      `StatusBarInfo.message_id` / `.message_number` (via `sap_read_status_bar`) on both systems.

Decision rule: a technical value replaces the text only if it exists and is identical on both
systems. Otherwise the text goes into the pack (Task 2 lists the fallback fields).

### Task 2: Pack fields and sources (sonnet)

- [ ] Extend the sections in `src/sapguimcp/lang/schema.py`:

```python
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
    initial_screen: Text  # new: title fragment of the initial screen (WebGUI; desktop uses program/dynpro)


@dataclass(frozen=True, slots=True)
class Se16Section:
    MERGE: ClassVar[MergeMode] = "session_en"
    hit_count_label: Text
    column_selection: Text
    no_values_found: Text
    table_label: Text  # new: label of the table-name input (WebGUI)
    max_hits_label: Text  # new: label of the max-hits input (WebGUI)
    empty_cell: Text  # new: placeholder text of empty grid rows (WebGUI)
    no_entries_status: Text  # new: status bar fragments "nothing found" (fallback if no message ID)
    results_title: Text  # new: title fragments of the SE16N result list
```

Fallback fields, added only if Task 1 shows the technical value is not usable:
`Se11Section.columns: Mapping[Se11Column, Text]` with a new `Se11Column` StrEnum
(`FIELD_NAME`, `DATA_TYPE`, `LENGTH`, `DECIMALS`, `SHORT_DESCRIPTION`, `KEY`) filled with
today's tuples. **Not needed in the pilot** (Task 1: the column names are identical).

**What the pilot actually added** (the schema block above is the plan's first draft; the review
corrected it): `se11.data_type_name_label`; `se16.table_label`, `max_hits_label`, `empty_cell`
(EN `Empty`, see Task 5), `table_not_found` (narrow: the check scans a whole snapshot, so it must
not use `common.does_not_exist`), `selection_columns` (the four headers only the selection grid has;
a language-free detection does not exist on the ARIA snapshot), `results_title`. **Not added:**
`se11.initial_screen` (program and dynpro are usable), `se16.no_entries_status` (message ID), and
`se11.dictionary_type` is deleted (unused).

- [ ] Fill `de.py` / `en.py` with today's literals — no new spellings except where SAP lookup
      proves one:

| Field                    | DE                                        | EN                                                                                     | Source (Task 2 lookup)                                                           |
| ------------------------ | ----------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `se11.initial_screen`    | `Text(("Einstieg",))`                     | `Text(("Initial",))`                                                                   | title of SAPLSD_ENTRY (`RSMPTEXTS` title) or `Manual("composed title fragment")` |
| `se16.table_label`       | `Text(("Tabelle",))`                      | `Text(("Table",))`                                                                     | `ScreenText("SAPLSE16N", "0100", "SEARCHTAB")`                                   |
| `se16.max_hits_label`    | `Text(("Maximale Trefferzahl",))`         | `Text(("Max. Number of Hits", "Maximum no. of hits"))` (dynpro 0100 of the ECC system) | `ScreenText("SAPLSE16N", "0100", "TEXTMAX")`                                     |
| `se16.empty_cell`        | `Text(("Leer",))`                         | `Text(("Empty",))` (`se16n_initial_en.yaml` shows `row "Empty Empty"`)                 | `Manual("WebGUI framework text")`                                                |
| `se16.no_entries_status` | `Text(("keine werte", "keine einträge"))` | `Text(("no values", "no entries"))`                                                    | `Message(<class>, <no>, relation="fragment")` from Task 1                        |
| `se16.results_title`     | `Text(("Treffer",))`                      | `Text(("hits", "entries"))`                                                            | `Manual("composed title fragment")`                                              |

Reused, not duplicated: `common.display` (SE11 Display button), `common.does_not_exist` and
`common.not_found` (SE11/SE16 not-found), `common.row_select_hint` (SE11 row split prefix and
SE16 row start), `se11.table_name` (the extra `"Table name"` literal in `se11_tools.py` is the
EN pack value already — delete it).

- [ ] Add the `SOURCES` entries in `src/sapguimcp/lang/sources.py` and resolve the existing
      `NOT_LOOKED_UP` entries of `se11.*` / `se16.*` / `common.row_select_hint` where the lookup
      finds them.
- [ ] `uv run pytest unittests/lang -q` (completeness, collision, untranslated-field tests) and
      `harvest_lang_texts.py DE --verify` / `EN --verify` on both systems.

### Task 3: §7 deletions (sonnet, review opus)

- [ ] **SE16N desktop label fallbacks** (`_execute_se16_query_desktop`, done): delete `"Table"`,
      `"Tabelle"`, `"Max. Number of Hits"`, `"Maximale Trefferzahl"` from the `focus_and_type`
      loops and the `fill_field` last-resort block; only `GD-TAB` and `GD-MAX_LINES` remain.
      If `GD-TAB` fails, return the existing "could not fill" failure.
- [ ] **SE16N grid detection** (`read_se16n_selection_rows.js`): delete the header-text test
      (lines with `Feldname` … `Selection Criteria`); detect the grid only by
      `grid.querySelector('[lsdata*="GS_SELFIELDS-"]')`, which the same file already uses.
      Check the error branch still returns `'Selection criteria grid not found'`.
- [ ] **SE11 initial-screen check on the desktop** (`_se11_display_screen_reached`, and the title
      check after F7): if Task 1 confirmed `SAPLSD_ENTRY`/`1000` on both systems:

```python
_SE11_INITIAL_SCREEN = ("SAPLSD_ENTRY", "1000")  # program / dynpro, language-independent


def _on_se11_initial_screen(session: Any) -> bool:
    info = session.info
    return (str(info.program), str(info.screen_number)) == _SE11_INITIAL_SCREEN
```

The backend-neutral post-F7 check (`screen = await backend.get_screen_info()`) uses
`(screen.program, screen.dynpro) == _SE11_INITIAL_SCREEN` when `screen.program` is set, else
`t.se11.initial_screen.contains(screen.title)` (WebGUI).

- [ ] **SE11 desktop column titles → `Columns(c).Name`** (live-gated by Task 1): add a keyword
      `column_keys: Literal["title", "name"] = "title"` in `table_helpers._find_table_control_info`
      (that is where the column keys are built), threaded through `read_table_control` and
      `read_table_control_all_rows` (the page readers take the already built keys); SE24 keeps
      `"title"` (area 3 decides there).
      SE11 passes `"name"` and maps the technical names recorded in Task 1:

```python
# Column names of the SE11 field list (Columns(c).Name, identical on both releases per Task 1)
_COL_FIELD_NAME = "<name from Task 1>"
_COL_DATA_TYPE = "<name from Task 1>"
_COL_LENGTH = "<name from Task 1>"
_COL_DECIMALS = "<name from Task 1>"
_COL_SHORT_DESC = "<name from Task 1>"
_COL_KEY = "<name from Task 1>"


def _parse_se11_table_rows(rows: list[dict[str, str]]) -> list[SE11Field]:
    ...  # unchanged, but _get_col(row, _COL_X) becomes row.get(_COL_X, "")
```

If Task 1 shows differing names, use the fallback `t.se11.columns[Se11Column.X].first_key(row)`
instead and keep `column_keys="title"`.

- [ ] **SE11 not-found / SE16N no-entries on the desktop:** only SE16N has a stable ID
      (`WUSL` / `002`); SE11 keeps the pack text (Task 1). The SE16N check
      `(sbar.message_id, sbar.message_number) == ("WUSL", "002")` stays in the branch after the
      `sbar.type == "E"` check, which is where the old keyword check sat. **Open point for review:** the
      message is of type `E` on both systems, so that branch never fires for it and a query without
      hits returns "SE16N error: ..." instead of an empty result, as before the migration. Reordering
      is a behaviour change and was left out of the pilot; it is a candidate follow-up. The old
      keywords `no entries` / `keine einträge` are covered by `common.no_entries`.

### Task 4: SE11 call sites (sonnet)

- [ ] Replace the legacy import block and the module-level regexes with call-time builders:

```python
from sapguimcp import lang
from sapguimcp.lang.schema import LanguagePack
from sapguimcp.lang.text import compiled
from sapguimcp.tools.screen_state_helpers import SelectionScreenState


def _row_split_pattern(t: LanguagePack) -> re.Pattern[str]:
    return compiled(rf'(?=- row "{t.common.row_select_hint.alt})')


def _field_name_pattern(t: LanguagePack) -> re.Pattern[str]:
    return compiled(rf'row "{t.se11.row_select_full.alt}\s+(?P<field_name>[A-Z_0-9/]+)')


def _row_data_pattern(t: LanguagePack) -> re.Pattern[str]:
    return compiled(rf'(?m)row "{t.se11.row_select_full.alt}\s+(?P<row_data>[^"]+)"')
```

- [ ] `_parse_se11_yaml`: the two-step DE-then-EN name search collapses into one search (the merged
      view holds both languages):

```python
t = lang.current("sap_se11_lookup")
name_match = compiled(
    rf'textbox "{lang.alt_of(t.se11.transparent_table, t.se11.structure)}":\s*(?P<name>\S+)'
).search(yaml_content)
desc_match = compiled(
    rf'textbox "{t.se11.short_description.alt}":\s*(?P<description>.+?)(?:\n|$)'
).search(yaml_content)
```

`_parse_se11_fields` takes `t` (or calls `lang.current`) and uses the three builders above.

- [ ] `_wait_for_se11_table_screen` / `_wait_for_se11_structure_screen`:

```python
t = lang.current("sap_se11_lookup")
...
if t.se11.database_table.contains(snapshot):
    break
...
target = SelectionScreenState(radios=dict.fromkeys(t.se11.database_table, True))
```

(structure: `t.se11.data_type`). The error texts lose the "supports DE and EN" sentence; say
"Could not find the database-table radio button" — the language list lives in the packs now.
These were substring checks before, so `.contains` keeps semantics.

- [ ] `_fill_table_name_field`: `labels = list(t.se11.table_name)`.
- [ ] `_fill_structure_name_field` — **latent bug found while planning:** it passes the regex
      sources `Dictionary.*Typ` / `Dictionary.*type` as labels, but `fill_field_with_keyboard`
      compares the input's `title` attribute exactly (`!== label`), so these labels can never
      match and the call always fell back to "first usable input". Add `se11.data_type_name_label:
Text` (`Name des Dictionary Typs` / `Name of Dictionary Type`, from the snapshots, `Manual`
      source) and pass `list(t.se11.data_type_name_label)`; `se11.dictionary_type` was unused and is
      deleted. **Behaviour change:** the structure name is now filled by title match, the "first usable
      input" fallback only remains as the safety net. (`_fill_table_name_field` keeps working through
      that fallback: the real title is `Tabellenname, 16-stellig`, the label `Tabellenname`.)
      `field_helpers.py` belongs to area 2: do not change its signature here.
- [ ] `_click_display_button`: `for label in t.common.display:` (merged DE view yields
      `Anzeigen`, `Display` — same order as today).
- [ ] `_check_object_not_found`: message-ID check from Task 3 if available, then
      `t.common.does_not_exist.contains(status_text) or t.common.not_found.contains(status_text)`.
      Widening: DE `does_not_exist` also holds "ist noch nicht vorhanden" / "nicht vorhanden";
      list in the PR.
- [ ] `_SE11_TABLE_FIELD_LABELS` / `_SE11_STRUCTURE_FIELD_LABELS` were unused: deleted.

### Task 5: SE16 call sites (sonnet)

- [ ] `se16_parser.py` (public functions take `t: LanguagePack` after the snapshot), including the
      **thousands-separator fix**:

```python
def _hit_count_pattern(t: LanguagePack) -> re.Pattern[str]:
    # Group separators differ per user setting: "5.000", "5,000", "5 000" (NBSP / thin space), "5'000"
    return compiled(rf'textbox "{t.se16.hit_count_label.alt}": "(?P<count>\d[\d.,\s\']*)"')


def _row_start_pattern(t: LanguagePack) -> re.Pattern[str]:
    return compiled(rf"- '?row \"{t.common.row_select_hint.alt}")

...
match = _hit_count_pattern(t).search(snapshot)
if match:
    return int(re.sub(r"\D", "", match.group("count")))
```

The four `snapshot.find(...)` calls for the first data row become one
`_row_start_pattern(t).search(snapshot, grid_start)` (**widening:** `common.row_select_hint` also holds
the prefixes `Zum Auswählen` / `To select`, the old `find` calls only knew the full hints; the
`unittests/webgui/testdata/se16_exploration` fixtures parse to the same rows); `col_name not in (...)` becomes
`not t.se16.column_selection.equals(col_name)` (it was an exact comparison).
A hit count is an integer, so stripping every non-digit is safe; the test covers
`5.000`, `5,000`, `5 000`, `5 000`, `5'000` in both languages.

- [ ] `se16_tools.py`, WebGUI paths:
    - `_fill_se16n_table_name`, `_type_table_name_with_validation`: iterate
      `t.se16.table_label` instead of `"Table"` / `"Tabelle"` (the two `fill_field` tries become one
      loop; `fill_main_input(table.upper(), list(t.se16.table_label))`; error message names the
      field, not the labels).
    - `_fill_se16n_max_hits`: loop over `t.se16.max_hits_label`.
    - Table-input selector:

```python
selector = ", ".join(f"input[title*='{v}'], input[aria-label*='{v}']" for v in t.se16.table_label)
clicked = await backend.click_element(selector)
```

    - `_wait_for_grid_rows` inline JS takes one object argument (spec §8):

```python
_GRID_HAS_ROWS_JS = """
(params) => {
    const empty = new RegExp('^(?:(?:' + params.texts.empty.source + ')\\\\s*)+$', params.texts.empty.flags);
    for (const grid of document.querySelectorAll('[role="grid"]')) {
        for (const row of grid.querySelectorAll('[role="row"]')) {
            if (row.querySelector('[role="columnheader"]')) continue;
            const text = row.textContent?.trim() || '';
            if (text && !empty.test(text)) return true;
        }
    }
    return false;
}
"""
...
result = await backend.evaluate_javascript(_GRID_HAS_ROWS_JS, script_arg({"empty": t.se16.empty_cell}))
```

      `WebGuiBackend.evaluate_javascript(script, arg=None)` already forwards the argument. Check
      the escaping of `\s` (the Python string holds `\\\\s`, JS receives `'\\s'`, the regex sees
      `\s`) against the Node guard from phase 2c.

    - `_check_table_not_found`: `t.se16.table_not_found.contains(snapshot)`. **Not**
      `common.does_not_exist`: this check scans the whole snapshot, and the DE variant `nicht
      vorhanden` of the common text would hit result data.
    - `_check_selection_screen_columns`: `sum(t.se16.selection_columns.equals(c) for c in columns) >= 2`
      (no language-free detection exists on the ARIA snapshot).
    - `_fill_se16n_max_hits`, `_collect_rows_with_pagination`, `_get_field_order_from_se11` take `t`;
      `_execute_se16_query` resolves it once at its start (both backends).
    - `_check_no_entries_found`: `t.se16.no_values_found.contains(snapshot)`.

- [ ] `se16_tools.py`, desktop path: `_SE16N_NO_ENTRIES_KEYWORDS` →
      message-ID check (Task 3) else `t.se16.no_entries_status.contains(sbar.message)`; the title
      check `["treffer", "hits", "entries"]` → `t.se16.results_title.contains(title)`. Resolve
      `t` at the start of `_execute_se16_query_desktop`, outside any `com.run` closure.
- [ ] `read_se16n_selection_rows.js` keeps no literal after Task 3; its call sites need no
      `texts` argument.

### Task 6: Tests (sonnet)

- [ ] Add the `lang_de` / `lang_en` fixture (or parametrize over both) to every test in the seven
      unit-test files that reaches a migrated function; run them, expect no other change.
- [ ] New tests, written first and failing on `main`:
    - `test_se16_parser.py::test_hit_count_group_separators` — parametrized over language and
      `5.000`, `5,000`, `5 000`, `5 000`, `5'000` → `5000`.
    - `test_se11_parser.py` — DE and EN snapshot each parse to the same `SE11Entry` (name,
      description, fields) through the single merged-view search.
    - `test_se11_desktop_key_flags.py` — rows keyed by column `Name` (if Task 3 switched) give the
      same `SE11Field` list as today's title-keyed rows.
    - `unittests/lang/test_se11_se16_pack.py` — `se16.no_entries_status`, `se16.results_title`,
      `se11.initial_screen` match the strings the old code matched (old literals as test data,
      in the test pack if the scanner flags them).
- [ ] `uv run pytest unittests/lang unittests/test_no_ui_literals.py -q`.

### Task 7: Prune, verify, live (haiku runs, sonnet diagnoses)

- [ ] R5: `--prune`; confirm the three files are gone from `lang_baseline.json` and nothing was
      added (`git diff --stat unittests/lang_baseline.json` shows only deletions).
- [ ] R6 static checks.
- [ ] Live, one at a time, both systems:
      `uv run pytest unittests/desktop/test_se11_integration.py unittests/desktop/test_se16_integration.py -v`
      and `uv run pytest unittests/webgui/test_se11_integration.py unittests/webgui/test_se16_integration.py -v`.
      Include at least one SE16 query with more than 999 hits (thousands separator) per language.
- [ ] Same live tests on `main` for any failure before calling it real.

### Task 8: Write back and PR

- [ ] Update Part 1 of this plan with whatever the pilot taught (recipe gaps, scanner false
      positives, fixture patterns) in the same PR.
- [ ] R7. Behaviour changes for this PR: `common.does_not_exist` / `not_found` widening in SE11
      (DE `ist noch nicht vorhanden`, `nicht vorhanden`); `common.row_select_hint` widening for the SE16
      row start and the SE11 row split; SE16N desktop no longer tries localized labels after `GD-TAB` /
      `GD-MAX_LINES`; SE16N grid detection by SELFIELDS cells only; SE11 desktop initial-screen check by
      program and dynpro; SE11 internal row keys (`Columns(c).Name`); SE11 structure name filled by
      title match; a DE session no longer needs a DE-only code path for EN texts; SE16 hit count
      accepts every group separator; EN `max_hits_label` also knows `Maximum no. of hits`.
- [ ] **Bugs fixed in the pilot** (each with a test): SE16 hit count with `,` / space / NBSP / `'`
      separators; EN SE16N grid wait ended at once on padding rows (`Leer` was the only placeholder
      text, EN shows `Empty`); `_fill_structure_name_field` could never match by title.
- [ ] **Review corrections folded into this plan** (from the pilot review): the grouped alternation in
      `_GRID_HAS_ROWS_JS` plus a Node test (`Leer Leer`, `Empty Empty`, data row); the
      `_check_selection_screen_columns` and `_check_table_not_found` call sites the first draft
      missed; threading `t` through the public parser functions and all callers; the `except Exception`
      in `_get_field_order_from_se11` and the batch loop of `sap_se11_lookup` (`t` resolved before them);
      `tables/scraper.py` as a second caller of `_lookup_object_on_initial_screen`; running the literal
      guard right after adding the pack values; `column_keys` in `_find_table_control_info`;
      `SelectionScreenState` from `sapguimcp.models.screen_state`; the readiness-test fakes need
      `session.info`.

---

## Part 3 — Remaining areas (expand with the recipe in their own session)

Each section names what differs from the pilot. Before starting an area, expand its section into
tasks like Part 2 (an opus plan is not needed; sonnet expands, the area's reviewer reviews).

### Area 2: status bar / popups / session pages / keys (backends + JS) — opus / fable

- **Files:** `backend/desktop/__init__.py` (27/28), `backend/desktop/_com_thread.py` (2/2),
  `backend/webgui/backend.py` (24/24), `js/check_popup.js` (9/9), `js/discover_fields.js` (1/1),
  `js/extract_status_bar.js` (18/20), `tools/field_helpers.py` (10/10), `tools/sap_tools.py` (1/1);
  also `set_language_field.js` (`pack.logon_dropdown`), `check_field_type.js` /
  `get_dropdown_options.js` (scalar → object argument, all `evaluate` calls at once).
- **Sections:** `popup`, `status_type`, `session_pages`, `keys` (merge mode `all`, read via
  `lang.universal()`); `PopupSection` is empty today and gets its fields here.
- **§7 deletions:** `discover_fields.js` dropdown → `ct === 'CB'`; `backend.py`
  `span[title*='Einstellungen'/'Settings']` → `[lsdata*='SETTINGS']`; `extract_status_bar.js`
  classes `fehler`/`warnung`/`erfolg` deleted; `sap_tools.SELECTORS["settings_button"]` text
  entries deleted; `check_popup.js` `[title*='Close'/'Schlie']` → the `close` class/id selectors
  **only with fixture or live evidence**, else `popup.close`.
- **Bugs:** status-bar noise filter DE only, dropdown check DE only, `check_popup.js` lacks
  `yes`/`no`, localized shortcut names from `parse_shortcut_from_title`.
- **Risks:** central path of every tool call. Popup behaviour must stay identical: record the
  popup detection result for every popup fixture under `unittests/webgui/testdata` before and
  after and diff them; adding `yes`/`no` must not make a popup that was ignored before get
  confirmed (review checks each such popup). `_com_thread.py` entries are messages around the COM
  worker — do not touch the `copy_context` logic. Live: login, popup, status bar and keyboard
  tests on both backends, both systems.

### Area 3: SE24/SE37/SE38 (+ edit tools) — sonnet / opus

- **Files:** `se24_tools.py` (32/46), `se24_edit_tools.py` (15/21), `se37_tools.py` (17/19),
  `se37_edit_tools.py` (2/3), `se38_edit_tools.py` (9/14), `parsers/se24_parser.py` (4/5),
  `parsers/se37_parser.py` (2/2).
- **Template-heavy:** `se24.display_title` and similar titles are `Template`s; use explicit
  `name=` groups where a trailing placeholder would capture too much.
- **§7 deletions:** desktop `"interface"` in title → `_read_se24_header` (WebGUI parser keeps the
  pack text); SE24 edit desktop column titles → `Columns(c).Name` (live-gated, uses the
  `column_keys` option from area 1); desktop activation confirmation keywords → T100 message ID
  (live-gated).
- **Bug:** visibility / static / constant EN only (DE private methods come out public) → canonical
  `Visibility` mapping, test with a DE class that has private, protected, static and constant
  components.
- **Risks:** edit tools write to SAP; live tests use the throwaway test objects from
  `docs/SAP_TEST_PREREQUISITES.md` only.

### Area 4: SE09/SE93 — sonnet / sonnet

- **Files:** `se09_tools.py` (16/37), `se93_tools.py` (3/3), `parsers/se09_parser.py` (7/9),
  `parsers/se93_parser.py` (2/2).
- **§7 deletions:** `se09_parser.py` `Transport Organizer: Auftr/Requ` → contains
  `Transport Organizer:` (as `se09_tools.py` does); desktop label fallback
  `TRDYSE01CM-USERNAME` only.
- **Bug:** `region "Liste"` DE only.
- **Scanner:** tool-parameter literals (`all`, `modifiable`, `released`) share lines with checkbox
  labels; once the labels move, mark the parameter checks `# lang-ok: tool parameter value`.
  Inline JS in `se09_tools.py` takes one object argument.
- **Risks:** public texts mention `<request>` / `<task>` only, never real numbers.

### Area 5: SM30/SPRO — sonnet / sonnet

- **Files:** `parsers/sm30_parser.py` (9/9); legacy imports in `sm30_tools.py`, `spro_tools.py`,
  `parsers/spro_parser.py`.
- Smallest area; mostly `bilingual_pattern` → `.alt` and the `sm30` / `spro` sections that exist.
- **Risks:** SM30 maintenance writes customizing; live tests read only.

### Area 6: SM37/SLG1/ST22 — sonnet / sonnet

- **Files:** `sm37_tools.py` (37/70), `slg1_tools.py` (20/35), `st22_tools.py` (44/46),
  `parsers/sm37_parser.py` (15/17), `parsers/slg1_parser.py` (3/3), `parsers/st22_parser.py`
  (21/21). Largest area; may be split into SM37 and SLG1/ST22 PRs if review rounds get long.
- **Behaviour change:** `session_sap_language()` disappears; unknown or pack-less session language
  → `UnsupportedLanguageError` (see Part 1). Live-test it.
- **§7 deletions:** desktop label fallbacks → `BTCH2170-*`, `S_UNAME-LOW`, `S_DATUM-LOW`.
- **Bugs:** desktop SM37 status not normalised (canonical `JobStatus` mapping for both backends);
  one shared "no entries" text for tools and parsers; `slg1.no_logs_found` must equal message
  BL 208 (verify mode); `if language == "DE"` branches (job-log button, SLG1 labels) become `Text`
  iteration.
- **Sources:** ST22 section headings are `Manual` (spec §9); canonical `DumpSection` mapping.
- **Scanner:** SM37 parameter literals (`scheduled`, `released`, ...) get `# lang-ok`.

### Area 7: abapGit / quick report — sonnet / sonnet

- **Files:** `abapgit_tools.py` (43/61), `quick_report_tools.py` (12/12).
- **§7 deletion:** desktop "transaction not found" → message ID `("S#", "343")` (reuse
  `sap_tools._TRANSACTION_NOT_FOUND_MESSAGE`).
- **Bug:** EN initial-screen check `"Entry"` never matches — find the real EN title live.
- **Risks:** abapGit pulls only in the client the prerequisites name; any write-protect popup
  stops the run (do not work around it). abapGit UI texts are mostly abapGit's own (HTML), not
  SAP's: sources are `Manual("abapGit UI text")`.

### Area 8: catalogs and data files — haiku / sonnet

- **Files:** `catalog/models.py` (3/3), `catalog/scraper.py` (3/3), `tables/scraper.py` (1/1);
  `data/sap_field_registry.json` (not scanned).
- **§7 deletions only:** DE column fallbacks → `TCODE` / `PGMNA` / `DESSION` / `TABNAME`;
  `sap_field_registry.json` `title*='Ausführen'` → `#EXECUTE_BTN`. No new pack fields expected.
- **Risks:** catalog JSON files are generated; regenerate only if the scraper output changes, and
  diff the result.

---

## After phase 3

The baseline holds only `breakpoint_tools.py`. Phase 4 deletes `lang.py` / `_legacy.py`,
`bilingual_pattern`, `bilingual_target`, adds the pseudo-locale test and documents the rule in
`ARCHITECTURE.md` / `CONTRIBUTING.md`.
