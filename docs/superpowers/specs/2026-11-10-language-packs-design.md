# Language packs: one place for every SAP-language-dependent text

Status: draft, reviewed twice · Related: #1041 (Italian logon language), #1042 (fast failure for
unsupported languages), #1043 (date input format)

## Problem

The server supports the SAP logon languages DE and EN. Language-dependent text sits at about 175
sites in 34 files, plus about 10 in the off-limits `breakpoint_tools.py`: screen titles, buttons,
labels, status messages, popup texts, column headers, tooltips, regexes and language branches.
`lang.py` holds 77 `X_DE`/`X_EN` pairs, but only around 25 sites use it, and its API
(`bilingual_pattern(de, en)`) hardcodes exactly two languages. Adding a third language today means
finding every site by hand.

Further findings of the inventory:

- **Duplicates:**
    - the inactive-objects phrase exists 3×;
    - local `_bilingual` helpers exist 3× (`_click_tab_bilingual` twice, `_set_checkbox_bilingual` once);
    - "Display" exists 5× and "not found" 6× in `lang.py`;
    - SM37 and ST22 tools and parsers use different "no entries" lists.
- **Single-language bugs:**
    - SE24 visibility/static/constant only match EN, so DE private methods come out public;
    - the desktop SM37 status is not normalised;
    - the SE16 hit count only accepts `.` as thousands separator;
    - the `extract_status_bar.js` noise filter and the `discover_fields.js` dropdown check are DE only;
    - `check_popup.js` lacks `yes`/`no`;
    - SE09 `region "Liste"` is DE only;
    - the abapGit EN initial-screen check (`"Entry"`) never matches.
- **Wrong texts:** a sample lookup in SAP's message table showed that `lang.py` expects an EN SLG1
  text that SAP does not show. `SLG1_NO_LOGS_FOUND_EN` is "No log could be found in the database",
  but message BL 208 in EN reads "No log found in the database". Hand-typed texts drift.
- **Wrong language source:** SLG1, SM37 and ST22 take the language from the _default_ system, not
  from the session's system.
- **Shortcut names:** `sap_tools.parse_shortcut_from_title` returns localized shortcut text (`Strg+S`) that
  the desktop key mapping does not accept.

### Today's ways of handling language, and what replaces each

| #   | Today                                                                     | Example                                                          | Replaced by                                         |
| --- | ------------------------------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------- |
| 1   | `X_DE` / `X_EN` constants in `lang.py`                                    | `SE16_HIT_COUNT_LABEL_DE`                                        | pack field `se16.hit_count_label`                   |
| 2   | `bilingual_pattern(de, en)`                                               | SE16/SE24 parsers                                                | `Text.alt` / `Text.pattern`                         |
| 3   | inline DE/EN tuples, `for label in (...)` loops, `bilingual_target` dicts | `("Datentyp", "Data type")`                                      | iterating a `Text`                                  |
| 4   | inline regex alternations, `name_de`/`name_en` groups                     | `(?:Eintrag\|Entry)\s+\d+\s+(?:von\|of)`                         | `Template` / `RegexText` / `alt_of`                 |
| 5   | lowercase substring checks                                                | `"einstieg" in title.lower()`                                    | `Text.contains`                                     |
| 6   | `if language == "DE"` branches                                            | job-log button, SLG1 labels                                      | iterating a `Text`                                  |
| 7   | DE/EN dict keys for column headers                                        | `row.get("Methode", row.get("Method"))`                          | `Text.first_key`                                    |
| 8   | local `_bilingual` helpers (3 copies)                                     | `_click_tab_bilingual`                                           | shared `click_tab` / `set_checkbox` taking a `Text` |
| 9   | literals inside JS files                                                  | `'Meldungsleiste'`, `[title*='Schlie']`                          | `for_js()` argument, or deleted (§7)                |
| 10  | language from the default system                                          | `sap_cfg.get_default().language`                                 | `lang.current()` via context variable               |
| 11  | `SapLanguage` Literal, `as_sap_language()`                                | `utils.py`, passed to `sap-mcp-config` by #1042                  | `lang.supported_languages()`                        |
| 12  | localized maps keyed by text                                              | `SM37_STATUS_MAP_DE`                                             | canonical mapping `JobStatus → Text`                |
| 13  | test-only DE/EN constants and `SAP_LANGUAGE` check                        | `unittests/webgui/testdata/lang_test.py`, `lang_strings` fixture | test pack using the same mechanism (§10)            |

The guard tests (§10) make sure none of the old mechanisms comes back.

## Goal

Adding a language is: add one pack file, register it, add fixtures, run the live tests. Nothing in
tools, parsers, backends, JS or tests needs to change, and tests fail if anything was missed —
including an untranslated field. Most of the pack can be harvested from SAP's own text tables
(§9), so the texts are SAP's exact wording, not translations.

Explicit exceptions and non-goals:

- No new language is shipped. Italian (#1041) and others come later, using the recipe (§11).

- `breakpoint_tools.py` is off-limits. It stays DE/EN-only and raises a clear "not supported in
  language X" error in other languages; the add-a-language recipe says so.
- Popup handling behaviour does not change: popup texts match all registered languages (§4).
- The date input format is unchanged, only moved into the pack as the language default. Reading the
  user's actual format, and tolerant date/time parsing, are tracked in #1043.
- German descriptions in `data/*.json` catalogs and the model-facing guidance in `skills/`,
  `prompts/` and `data/sap_knowledge.md` are not translated. They are documentation for the model.
- Browser and OS error phrases in `backend/webgui/browser.py` are not SAP language.

## Design

### 1. Package layout

```
src/sapguimcp/lang/
  __init__.py   # public API + registry: current, universal, use, set_session_language, pack_for,
                # supported_languages, UnsupportedLanguageError, alt_of, click_tab, set_checkbox
  text.py       # Text, RegexText, Template, HasAlt protocol, Python and JS regex builders
  schema.py     # frozen dataclasses: LanguagePack, its sections, merge declarations
  sources.py    # SAP source key per pack field (§9)
  invariant.py  # texts that are the same in every logon language (abapGit UI, our Z report)
  de.py         # DE = LanguagePack(...)
  en.py         # EN = LanguagePack(...)
  README.md     # "How to add a language" recipe
scripts/harvest_lang_texts.py  # draft/verify a pack from SAP text tables (§9)
```

`lang/` must not import `sapguimcp.models.config`. The #1042 wiring imports from `lang/`, not the
other way round, to avoid an import cycle.

`lang.py` becomes a re-export shim during the migration and is deleted at the end. A unit test fails
while the shim still exists after its last importer is gone.

### 2. Three text types

Every leaf of a pack is one of three frozen value types. They are siblings, not subclasses, so mypy
catches misuse such as clicking a regex or a template.

```python
@dataclass(frozen=True, slots=True)
class Text:                                   # literal variants; the common case
    variants: tuple[str, ...]                 # ("Methoden",) or ("Source Code", "Source text")
    fold: bool = True                         # case-insensitive (lower() on both sides)
    word: bool = False                        # require word boundaries ("Line", "Alt", "ja")

    def contains(self, s: str) -> bool
    def equals(self, s: str) -> bool
    def first_key(self, row: Mapping[str, T]) -> T | None   # column header lookup in dict rows
    def __iter__(self) -> Iterator[str]       # click/fill/tab candidates, in order
    @property
    def alt(self) -> str                      # escaped alternation for embedding, e.g. "(?i:Anzahl Treffer|Number of Hits)"
    @property
    def pattern(self) -> re.Pattern[str]      # compiled alt
    def for_js(self) -> JsText                # {"variants": [...], "source": "...", "flags": "iu"}

@dataclass(frozen=True, slots=True)
class RegexText:                              # irregular patterns only; raw strings
    patterns: tuple[str, ...]
    fold: bool = True
    alt, pattern, for_js                      # no contains/iteration/selectors

@dataclass(frozen=True, slots=True)
class Template:                               # language-dependent word order
    variants: tuple[str, ...]                 # ("{name} anzeigen",) / ("Display {name}",)
    fold: bool = True
    def search(self, s: str, **groups: str | HasAlt) -> re.Match[str] | None
    def match(self, s: str, **groups: str | HasAlt) -> re.Match[str] | None
    def format(self, **values: str) -> str
```

Rules:

- **Templates compile one pattern per variant.** `search`/`match` return the first hit.
    - Python `re` rejects duplicate group names across alternatives. That is why today's code has
      `name_de`/`name_en`.
    - Every variant uses the same group names, so callers read `m["name"]` regardless of language.
- **Caching:** frozen, slotted dataclasses have no `__dict__`, so `cached_property` does not work.
  `alt` and `pattern` go through module-level `@lru_cache` builders keyed by
  `(variants, fold, word)`.
- **Variant order inside `alt`:** variants are de-duplicated case-insensitively and sorted
  longest-first. Otherwise a short variant shadows a longer one: `Programm|Programmname` captures
  `name ZFOO`.
- **Case:** `alt` carries its own case flag as a scoped group `(?i:…)`. It can therefore be embedded
  into regexes that are deliberately case-sensitive elsewhere, such as the ST22 captures of
  `[A-Z][A-Z0-9_/]+`. `contains`/`equals` use `lower()`, the same folding as `IGNORECASE`.
- **Word boundaries:** `word=True` is explicit. It emits `(?<!\w)…(?!\w)`, not `\b`, so variants
  that start or end with punctuation (`Ext. Identif.`) still match.
- **Composing:** `alt_of(*texts)` joins several `HasAlt` values into one group, e.g.
  `Class|Klasse|Interface` or `(Success|Error)\s+(Message Bar)`.
- **JS:** `for_js()` has its own JS escaper and builder. Python's `re.escape` output is invalid in
  JS `u` mode, JS `\b` is ASCII-only, and scoped `(?i:…)` is not portable. It therefore emits:
    - a plain source;
    - `(?<![\p{L}\p{N}_])…(?![\p{L}\p{N}_])` for word boundaries;
    - flags `iu`.

    Composites that mix case sensitivity are Python-only.

- **Playwright:** `text=` selectors and `get_by_role(name=…)` take candidates by iteration or
  `name=text.pattern`. No selector helpers on `Text` until a second call site needs one.

### 3. Schema and packs

`LanguagePack` is a frozen, slotted dataclass with required fields only — no defaults. A pack that
omits a field fails mypy and fails at import. Packs and the merged runtime view share this one
type, so autocomplete and type checking work at every call site. The field-wise merge is a generic
`merge(packs: Sequence[S]) -> S` over `dataclasses.fields`.

Sections:

- `common`: shared vocabulary — display/change, not found / does not exist, initial screen,
  row-select hint, OK/cancel/yes/no, "Table", "User", "Program".
- `status`: activation/syntax keywords, message-bar noise.
- `status_type`: keywords that infer a message's type (error/warning/success).
- `popup`: inactive objects, original language, already logged on, close, continue.
- `session_pages`: login, logoff and timeout page texts.
- `keys`: canonical keyboard modifiers (`Ctrl`, `Shift`, `Enter`, `Delete`, …) → localized `Text`.
- one section per transaction area, for text only that area uses: `se09`, `se11`, `se16`, `se24`,
  `se37`, `se38`, `se93`, `sm30`, `sm37`, `slg1`, `st22`, `spro`, `abapgit`, `quick_report`.

Pack-level fields:

- `code`: SAP language key (`"DE"`).
- `html_lang`: the ISO code the WebGUI page reports (`"de"`). SAP keys and ISO codes differ for some
  languages.
- `logon_dropdown`: the WebGUI logon dropdown text.
- `date_format`: the default input pattern, see #1043.
- `same_as_en`: a `frozenset` of field paths (§10).

Non-`Text` fields in a merged view always come from the session pack.

Field rules:

- **Variants:** all variants of one text are flat variants of one `Text`. That covers variants that
  differ by SAP release (ECC vs S/4HANA titles, "Sourcecode"/"Source Code"/"Source text") and by
  truncation ("Ext. Identif.", "Job-Erstelle"). There is no release tagging.
- **Canonical mappings:** classification and normalisation use mappings keyed by an enum, for
  example:
    - `sm37.status: Mapping[JobStatus, Text]`, wrapped in `MappingProxyType`;
    - SE09 status, SE24 visibility/level, ST22 section, activation result.

    The completeness test checks that every enum member has a `Text`. A collision test checks that no
    variant maps to two members in any merged view.

- **Shared vs invariant texts:** SAP-translated texts that happen to coincide in DE and EN
  (`Interface`, `Workbench`, `Customizing`) stay in the packs, because a third language may differ.
  Only text that is fixed in every logon language goes to `invariant.py`: abapGit's English UI,
  `p_trkorr`, our Z report's output. Lists that mix both today
  (`abapgit_tools.ERROR_KEYWORDS`/`ERROR_PATTERNS`) are split.

### 4. Merging: which languages a check matches

The merge mode is declared per section as a `ClassVar` in the class body. It is not a class keyword
argument, because `@dataclass(slots=True)` re-creates the class and silently drops it. A guard test
asserts which sections are `all`.

| Merge                  | Packs used, in order  | Sections                                        |
| ---------------------- | --------------------- | ----------------------------------------------- |
| `session_en` (default) | session pack, then EN | every section not listed below                  |
| `all`                  | every registered pack | `popup`, `status_type`, `session_pages`, `keys` |

Two accessors:

- **`lang.universal()`** returns the `all` sections. It is a module-level merged constant, built
  once and independent of any session. Popup classification, status-type inference, login and logoff
  pages and shortcut parsing use it, so they work in every situation: no session, an unsupported
  session language, or explicit `session_id` paths that bypass the context variable.
- **`lang.current()`** returns the session's `session_en` view. If the session language has no
  pack, it raises `UnsupportedLanguageError`, e.g. "SE24 lookup needs a language pack; supported:
  DE, EN".

`invariant.py` is merged into both. Merged views are cached in a plain `dict[str, LanguagePack]`.
The packs are not hashable once they contain mappings, so `lru_cache` keyed on a pack does not work.

Why `session_en`: standard SAP UI texts that are not translated are shown in the system's secondary
language, usually EN, where language supplementation was run. Matching every registered language
for parsing would widen every regex with each new language.

Why `all` for these four sections:

- It keeps today's behaviour: an EN session still recognizes a German popup, for example one raised
  in an object's original language.
- Login, logoff and timeout pages appear in the browser's or the requested logon language.
- Shortcut names come from the agent. `parse_shortcut_from_title` returns canonical English key names,
  which the desktop key mapping accepts.

### 5. Which language is active: a context variable

`lang.current()` reads a **backend-neutral context variable** that holds the language code of the
session the current tool call works on. It is set only through
`lang.set_session_language(code | None)`, at these sites:

- **`backend/manager.get_or_create`**: it resolves the session for every tool call; today it sets
  `_current_session_id` for the desktop only.
- **Both `login()` implementations**: after the new session is registered. `get_or_create` ran
  before that session existed.
- **`_recover_desktop_if_dead`**: it resets the variable together with `_current_session_id`.

Where the language comes from:

- **Desktop:**
    - Login already reads `session.info.user` on the COM thread right after registration. The same
      call returns `(user, session.info.language)`, so no extra COM call is needed.
    - The language is cached on the registry entry. Child sessions copy their parent's language.
    - Sessions registered through the legacy `_session` setter have no language and get only
      `universal()`; no production code uses that setter. There is no lazy COM read, which would block
      every tool call on a wedged session.
    - When attached-session registration lands, its language read uses the probe's timeout with no
      retries.
- **WebGUI:**
    - Read `document.documentElement.lang` in `_post_login_setup`, which all three login success paths
      call, and map it to the SAP key via the packs' `html_lang`.
    - Store it in a new `SessionRegistry._languages: dict[str, str]`, cleared in `unregister` /
      `_on_page_closed`.
    - Tabs auto-registered via `/o` inherit it in `_register_new_window_session`.

**COM worker thread**: `ComThread.run` enqueues each call for a plain worker thread, which does not
see the caller's context variables; only `com_call_target` is copied by hand. A closure calling
`lang.current()` on the worker would get the primary session's language without any error.

- **Fix:** in `run()`, take `ctx = contextvars.copy_context()` per call, on the caller's task. Never
  store it on `self`. Enqueue `functools.partial(ctx.run, fn)`. Keep the hand-carried target in the
  tuple, because the watchdog reads it from another thread.
- **Safety:**
    - `run()` is async, so a worker closure cannot nest it.
    - There is one worker thread.
    - Retries run one after another; each one enters and exits the copy.
    - `wait_for_condition` polls issue separate `run()` calls.
    - Context-variable writes on the worker are discarded.
- **Convention:** resolve the pack in the caller (`t = lang.current()`) and close over `t`.

**Tests**: `with lang.use("DE"):` sets the variable. One fixture runs against several packs without
signature changes.

Parsers keep their signatures and call `lang.current()`. This removes the
`sap_cfg.get_default().language` reads in SLG1, SM37 and ST22.

### 6. Supported languages (builds on #1042)

#1042 moves to `sap-mcp-config` v2, where the server passes the languages it supports. An
unsupported language in `systems.json` is a loud config error.

- `lang.supported_languages()`, derived from the registered packs, replaces `SapLanguage` as that
  list. A new pack automatically becomes an accepted config language. `as_sap_language()` goes away.
- A session in a language without a pack is still possible when the server attaches to a session
  the user opened. `universal()` keeps working there, and `current()` raises
  `UnsupportedLanguageError`.
- `sap_get_capabilities` reports the session language and whether a pack exists.

### 7. Prefer no text at all

Before a literal is moved into a pack, check for a language-independent alternative. Where one
exists, the literal is deleted. Already identified:

| Site                                                                      | Replace with                                                                                                                          | Note                                                                    |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `discover_fields.js` `'Dropdown-Listenfeld'`                              | the `ct === 'CB'` attribute (as `check_field_type.js` does)                                                                           |                                                                         |
| `read_se16n_selection_rows.js` grid detection by headers                  | `[lsdata*="GS_SELFIELDS-"]` (same file)                                                                                               |                                                                         |
| `backend.py` `span[title*='Einstellungen'/'Settings']`                    | `[lsdata*='SETTINGS']` (next line)                                                                                                    |                                                                         |
| `extract_status_bar.js` classes `fehler`/`warnung`/`erfolg`               | delete: CSS class names are not translated                                                                                            |                                                                         |
| `backend/webgui/parsers/se09_parser.py` `Transport Organizer: Auftr/Requ` | contains `Transport Organizer:`                                                                                                       | as `se09_tools.py` already does                                         |
| `se24_tools.py` `"interface"` in title (desktop)                          | the header read in `_read_se24_header`                                                                                                | WebGUI parser keeps a pack text                                         |
| abapGit "transaction not found" (desktop)                                 | message ID `("S#", "343")`, as `sap_tools.py` does                                                                                    |                                                                         |
| desktop label fallbacks in SM37/ST22/SE16/SE09                            | the technical names already tried first (`BTCH2170-*`, `S_UNAME-LOW`, `S_DATUM-LOW`, `GD-TAB`, `GD-MAX_LINES`, `TRDYSE01CM-USERNAME`) |                                                                         |
| catalog DE column fallbacks                                               | `TCODE` / `PGMNA` / `DESSION` / `TABNAME`                                                                                             |                                                                         |
| `data/sap_field_registry.json` `title*='Ausführen'`                       | `#EXECUTE_BTN`                                                                                                                        |                                                                         |
| `sap_tools.SELECTORS["settings_button"]` text entries                     | delete (test-only; id/gear entries remain)                                                                                            |                                                                         |
| `check_popup.js` `[title*='Close'/'Schlie']`                              | the `close` class/id selectors in the same list                                                                                       | popup detection: only with fixture or live evidence, else `popup.close` |
| desktop column titles in internal parsers (SE11, SE24 edit)               | `Columns(c).Name` instead of `Title`                                                                                                  | changes row keys; needs a live check                                    |
| desktop activation confirmation keywords                                  | T100 message ID from the status bar                                                                                                   | needs a live check for the IDs                                          |

New code follows the same rule (documented in `ARCHITECTURE.md`).

### 8. JavaScript (WebGUI)

Every JS file takes a single object argument, e.g. `{"texts": {...}, "label": ...}`, because
Playwright `evaluate` accepts exactly one. Scripts that take a scalar today (`check_field_type.js`,
`get_dropdown_options.js`) migrate to the object form. `texts` is built in Python with `for_js()`,
and JS builds `new RegExp(t.source, t.flags)`. No UI literals remain in `.js`. Inline JS strings in
Python (`se16_tools`, `se09_tools`) follow the same rule. `set_language_field.js` gets
`pack.logon_dropdown`.

### 9. SAP as the source of the texts

Most texts in a pack exist in SAP's own text tables, keyed by technical ID and language. During the
migration every text is looked at anyway, so its source key is recorded in `lang/sources.py`:

| Kind of text                             | SAP source                                              | Source key type                      |
| ---------------------------------------- | ------------------------------------------------------- | ------------------------------------ |
| field labels, column headers             | data element texts (`DD04T`: short/medium/long/heading) | `DataElement(name, length)`          |
| screen texts, tabs, radio/checkbox texts | screen texts (`D021T`)                                  | `ScreenText(program, screen, field)` |
| buttons, menu entries, function texts    | GUI status texts (`RSMPTEXTS`)                          | `GuiFunction(program, fcode)`        |
| status-bar messages                      | messages (`T100`)                                       | `Message(class, number)`             |
| fixed values (e.g. job status)           | domain fixed values (`DD07T`)                           | `DomainValue(domain, value)`         |
| transaction titles                       | `TSTCT`                                                 | `Transaction(tcode)`                 |

A field without an SAP source is recorded as `Manual(reason)`. Examples: composed titles, WebGUI
framework texts such as "Message Bar", and ST22 dump section headings.

`scripts/harvest_lang_texts.py <lang>` reads every source for a language through ADT data preview
on these development-metadata tables, as allowed by the SAP API policy. It has two modes:

- **draft**: writes a draft `<lang>.py`. Harvested fields hold SAP's exact text, including
  abbreviations. `Manual` fields are left as `TODO` for an agent or a person, who logs on in that
  language, walks the transactions and records the fixtures (needed for the parser tests anyway).
- **verify**: compares an existing pack with SAP and reports drift, for example after an upgrade or
  for wrong texts like the SLG1 one above. It runs in the live test suite for DE and EN.

Placeholders in T100 texts (`&1`) map to template placeholders. A `sources.py` completeness test
requires every pack field to have a source entry.

The new language must be installed on the system (`T002C.LAINST`). If ours lacks it, the harvesting
runs on a system that has it, e.g. the #1041 reporter's.

### 10. Guard tests

**Completeness and translation**

- Every registered pack constructs, and every `Text` has at least one non-empty variant.
- Every canonical mapping covers every enum member, and no variant collides across members in any
  merged view.
- Every regex compiles in Python, and every `for_js()` source compiles in JS: one Node check over
  all packs in CI.
- `fold`/`word` flags and the field kind are identical for one field across packs.
- Templates and regexes have the same placeholders and named groups across packs.
- The merge-mode test asserts the four `all` sections.
- Untranslated-field check: in every non-EN pack, a field whose value equals the EN value must be
  listed in that pack's `same_as_en`. Each entry must resolve to a field and still equal EN, so a
  copied `en.py` fails and stale entries fail too.
- **A synthetic third language** is registered in tests. It exercises the N-language merge, group
  naming, flag consistency and the `UnsupportedLanguageError` path before a real third language
  exists.

**No-literal scan** (`unittests/test_no_ui_literals.py`), over `src/**/*.py` outside `lang/` and
over `backend/webgui/js/*.js`:

1. **Sink rule (primary)**, an AST check that flags a string constant which is:
    - an argument to a UI sink: `click_button`, `click_tab`, `fill_field`, `fill_form` keys,
      `set_checkbox`, `select_dropdown`, `get_by_role(name=…)`, `text=` / `has-text(...)` /
      `[title*=…]` selectors;
    - an operand of `in` / `==` / `startswith` / `endswith` / `re.*` where the other side is a name
      matching `title|heading|snapshot|status|msg|message|text|label|header|kind|level`;
    - a key in `row.get(...)` / `row[...]`.
2. **Value rule (secondary)**: case-folded substring match against the variants of 5 or more
   characters in every registered pack.
3. **JS rule**: string and regex literals used in `includes`, `===`, `match`, `test`, `replace`,
   `title*=` or `has-text`.

Skipped: docstrings, logging calls, `description=` keyword arguments.

Exemptions, keyed by _file + literal_, not by line:

- `unittests/lang_baseline.json` is **shrink-only**. It is seeded from the manual inventory of all
  ~175 sites, not only from what the detector finds. A new hit fails, and so does an entry that no
  longer occurs. `breakpoint_tools.py` stays on it.
- An inline `# lang-ok: <reason>` is a **permanent** allowlist entry for literals that collide with
  code identifiers or are the server's own messages. Adding a pack never needs a baseline edit.

**COM-thread test**: `lang.current()` inside a `com.run` closure returns the caller's language.

**Pseudo-locale test**, added once the baseline is nearly empty:

- Rewrite the DE fixtures, replacing pack variants with markers (`⟦se24.tab_methods⟧`) only in text
  nodes and `title`/`aria-label` values. Blind replacement of short variants would corrupt ids and
  lsdata.
- Build a pseudo pack with the same markers, disable the EN merge, and run every parser test. A
  parser that still depends on a hardcoded literal fails.

**Language in the test suite**:

- The integration tests run in one language per run: `SAP_LANGUAGE` for WebGUI, the system's
  configured language for desktop. Snapshots are named `*_<lang>.html`.
- The test-only constants (`unittests/webgui/testdata/lang_test.py`, the `lang_strings` fixture)
  become a test pack with the same `Text` type, sections and completeness test. The `("DE", "EN")`
  check becomes `supported_languages()`.
- Parser snapshot tests are parametrized over the languages that have fixtures. Every parser has at
  least DE and EN fixtures; today several areas only have DE.

### 11. Adding a language (recipe in `lang/README.md`)

1. Run `scripts/harvest_lang_texts.py <lang> --draft` on a system with the language installed.
2. Fill the `Manual` fields: an agent logs on in the language, walks the transactions, records
   fixtures and fills the remaining texts. mypy, the completeness test and the untranslated-field
   check show the gaps; confirm deliberate equals in `same_as_en`. Fill the test pack too.
3. Register the pack in `lang/__init__.py`. It becomes an accepted `systems.json` language at once.
4. Run the parser tests on the new fixtures, and the pseudo-locale test.
5. Run the live tests logged on in the new language, including `harvest --verify`, and attach the
   evidence to the PR.
6. State the known limitation: `breakpoint_tools` stays DE/EN.

## Rollout

Phased. Each PR is live-tested on both systems.

1. **Session language plumbing**:
    - the language context variable, `set_session_language` at the three sites;
    - the desktop language read in the existing login COM call;
    - the WebGUI read in `_post_login_setup`;
    - `copy_context` in `ComThread.run` with its guard test;
    - SLG1/SM37/ST22 stop reading the default system.

    This fixes a real bug before any pack exists.

2. **Foundation**:
    - the `lang/` package with the three text types, schema, merging, `current()`/`universal()`,
      `invariant.py`;
    - DE/EN packs (today's `lang.py` content, regrouped);
    - `supported_languages()` in the #1042 wiring;
    - `UnsupportedLanguageError`;
    - the JS object-argument convention;
    - `sources.py` and `harvest_lang_texts.py` (verify mode);
    - the test pack;
    - guard tests with the seeded baseline and the synthetic third language;
    - the `lang.py` shim.
3. **Migration per area**, one PR each. Each PR applies the §7 deletions first, records every
   moved text's source, shrinks the baseline and fixes that area's single-language bugs and drifted
   texts. Areas:
    - status bar / popups / session pages / keys (backends + JS)
    - SE11/SE16
    - SE24/SE37/SE38 (+ edit tools)
    - SE09/SE93
    - SM30/SPRO
    - SM37/SLG1/ST22
    - abapGit / quick report
    - catalogs and data files
4. **Cleanup**: delete `lang.py`, add the pseudo-locale test, and document the rule in
   `ARCHITECTURE.md` / `CONTRIBUTING.md`.
   Not part of this work: shipping Italian or any other new language. This work only records where
   every DE/EN text comes from in SAP (`sources.py`) and provides the harvest script. A later language
   then follows the recipe in §11: run the draft mode on a system with that language installed, then
   an agent pass for the manual fields.

## Model assignment per task

Each task gets the cheapest model that does it without loss of quality. The rule: concurrency, type
design and behaviour-preserving changes to central paths go to the strongest models. Mechanical
moves, lookups and test runs go to the cheap ones. A task is escalated one level if its agent fails
twice or its review finds a design problem, never downgraded mid-task. A failing live test is not an
agent failure until it is shown to be real (see the flakiness note under Risks).

| Phase | Task                                                                                                                      | Implement | Review                                                             |
| ----- | ------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------------------------------------------------ |
| 1     | `copy_context` in `ComThread.run`, context variable, `set_session_language` sites incl. recovery                          | opus      | fable                                                              |
| 1     | desktop language in the login COM call, WebGUI read in `_post_login_setup`, registry storage, `/o` inheritance            | sonnet    | opus                                                               |
| 1     | SLG1/SM37/ST22 switch from default system to `lang.current()`                                                             | sonnet    | sonnet                                                             |
| 2     | `Text`/`RegexText`/`Template`, Python and JS regex builders, escaper, word boundaries                                     | opus      | fable                                                              |
| 2     | schema, generic merge, `current()`/`universal()`, merge-mode declaration, caching                                         | opus      | fable                                                              |
| 2     | DE/EN packs: regroup today's `lang.py` content into sections                                                              | sonnet    | sonnet                                                             |
| 2     | `sources.py`: find each DE/EN text's SAP source via ADT queries (`T100`, `DD04T`, `D021T`, `RSMPTEXTS`, `DD07T`, `TSTCT`) | sonnet    | sonnet spot check                                                  |
| 2     | `harvest_lang_texts.py` (verify mode)                                                                                     | sonnet    | opus                                                               |
| 2     | no-literal scanner (AST sink rule, value rule, JS rule)                                                                   | sonnet    | opus                                                               |
| 2     | seed `lang_baseline.json` from the inventory                                                                              | haiku     | sonnet spot check                                                  |
| 2     | completeness, collision, flag, merge-mode, untranslated-field tests; synthetic third language                             | sonnet    | opus                                                               |
| 2     | test pack from `lang_test.py` / `lang_strings`; JS object-argument convention                                             | sonnet    | sonnet                                                             |
| 3     | migration: status bar / popups / session pages / keys (backends + JS); popup behaviour must stay identical                | opus      | fable                                                              |
| 3     | migration: SE24/SE37/SE38 (template-heavy, single-language bugs)                                                          | sonnet    | opus                                                               |
| 3     | migration: SE11/SE16, SE09/SE93, SM30/SPRO, SM37/SLG1/ST22, abapGit / quick report                                        | sonnet    | opus (first area), sonnet (later areas following the same pattern) |
| 3     | migration: catalogs and data files (§7 deletions, technical names)                                                        | haiku     | sonnet                                                             |
| 3     | §7 deletions that need a live check (popup close selectors, column `Name`, T100 activation IDs)                           | sonnet    | opus                                                               |
| 4     | delete `lang.py`, docs in `ARCHITECTURE.md` / `CONTRIBUTING.md`, `lang/README.md` recipe                                  | haiku     | sonnet                                                             |
| 4     | pseudo-locale test (fixture rewriting limited to text nodes and attributes)                                               | sonnet    | opus                                                               |
| all   | running unit and live tests, collecting literal pytest summaries                                                          | haiku     | —                                                                  |
| all   | diagnosing a failing live test                                                                                            | sonnet    | —                                                                  |
| all   | leak and fact check of every public issue/PR text before posting                                                          | opus      | —                                                                  |

Reviews follow the existing PR workflow (self-review, Copilot review, CI). The review column is the
additional agent review per PR.

## Risks

- **`copy_context` in `ComThread.run`** changes a central code path. It is covered by the guard
  test and the existing COM-thread tests.
- **The sink rule** has false positives on code-identifier strings; `# lang-ok` absorbs them. Its
  false negatives are covered by the seeded baseline and the pseudo-locale test.
- **The EN merge** could hide a missing translation. The untranslated-field check and per-language
  fixtures cover this.
- **Harvested texts** may differ from what the screen shows when a screen composes or truncates
  them. Verify mode and the fixtures catch this; such fields become `Manual`.
- **A third language** needs a system with it installed, for both harvesting and live tests.
- **Flaky integration tests**: the live tests may turn out to be flaky (timing, session state, a
  shared SAP connection), which would make a migration PR look broken when it is not. Mitigations:
    - run only the tests relevant to the area, one PR at a time on the single SAP connection;
    - rerun a failed test on its own before treating the failure as real;
    - compare against the same test on `main`: a test that also fails there is pre-existing and gets
      its own issue instead of blocking the PR;
    - report every flaky test in the PR with its literal pytest output.

    The unit-level guards (completeness, scanner, parser snapshot tests) are deterministic and carry
    the main weight, so flaky live tests slow the rollout down but do not weaken the guarantee.
