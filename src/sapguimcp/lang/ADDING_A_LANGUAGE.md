# Adding a login language

This guide explains how to support a new SAP logon language (for example Italian, `IT`; see #1041).
Every text the server reads from or types into an SAP screen lives in this package, one pack per
language. A new language is "more of the same": one new pack module, one registration, then
verification. Design and rationale: `docs/superpowers/specs/2026-11-10-language-packs-design.md`
(#1044).

## How the packs work (two minutes)

- `schema.py` defines the shape: a `LanguagePack` with one section per transaction or concern
  (`se11`, `sm37`, `popup`, ...). Every field is required, so a pack that misses a text does not
  type-check.
- `de.py` / `en.py` fill that shape. Each field is a `Text` (literal variants), `RegexText`
  (patterns), `Template` (texts with placeholders such as `{name}`) or a canonical mapping
  (`canonical({JobStatus.FINISHED: Text(...)})`).
- At login the session language is stored per session. `lang.current()` returns the merged view
  for it: the session pack first, then EN (`MERGE = "session_en"`). Sections with
  `MERGE = "all"` (`popup`, `status_type`, `session_pages`, `keys`) are merged over every
  registered pack and read through `lang.universal()`. Popups are therefore detected in every
  language, also before login and on sessions without a pack.
- `sources.py` records where SAP keeps each text (data element, screen text, message, domain
  value, GUI function, transaction title), or `Manual("<reason>")` when there is no SAP source.
  `scripts/harvest_lang_texts.py` reads these sources to compare a pack with SAP.
- `INVARIANT` (`invariant.py`) holds texts that are the same in every logon language (our own
  report output, abapGit's English-only messages). A new language never touches it.

## Core first (optional)

A full pack takes a lot of work. A language can start with a _core pack_ instead: a `CorePack`
(`schema.py`) holds only the four sections that `lang.universal()` reads (`popup`, `status_type`,
`session_pages`, `keys`). With a core pack registered:

- the language is accepted as `language` in `systems.json` (`lang.logon_languages()`), and
  `sap_login` reports `language_support: "core"`;
- popups, activation messages and key names in that language are recognised in every session;
- the transaction tools (everything that calls `lang.current()`) fail before they touch SAP, with an
  `UnsupportedLanguageError` that says the language has only a core pack.

Steps:

1. Create `lang/<xx>.py` with `XX = CorePack(code="XX", popup=..., status_type=...,
session_pages=..., keys=...)`, modelled on the same sections of `en.py` (same kinds and flags).
2. Register it in `__init__.py` in `_CORE_PACKS`, not in `_PACKS`.
3. Settle every text live on SAP GUI for Windows, logged on in the new language. Apart from
   `popup.maintain_in_original` (a screen text), every core field is `Manual` in `sources.py`, so
   `harvest_lang_texts.py` cannot help: read the popup titles (error, information, confirmation,
   "Inactive Objects", the original-language popup and its button), the activation messages in the
   status bar, the debugger window title and the key names in button tooltips. abapGit's own
   messages are English only; keep the EN values there, as `it.py` does.
4. Run the guards: `uv run --group tests pytest unittests/lang -q`.
   `unittests/lang/test_core_pack.py` checks that no keyword of the new language changes how the
   EN and DE popup and status texts of the tests are classified. These keywords are matched as
   substrings in every session, so a short word ("No", "Info") can turn a German popup into a
   different type.

To turn a core pack into a full pack later, follow the procedure below; the core sections carry
over, and the pack moves from `_CORE_PACKS` to `_PACKS`.

Other MCP servers that read the same `systems.json` check the language against their own list, so
they may reject a language that this server accepts.

## Procedure

1. **Draft the pack.** Run
   `uv run python scripts/harvest_lang_texts.py IT --draft [--system "<key>"] --out src/sapguimcp/lang/it.py`
   on a system that has the language installed with its texts (`T002`, and texts in `DD04T`; a
   system that only lists the language yields no SAP text). The draft is a copy of `en.py`:
   sourced `Text` fields hold SAP's text; `Manual`, fragment and `Template` / `RegexText` fields
   keep the EN value with a `# TODO` comment, and flags and kinds stay those of EN. It never
   registers the pack. Without direct access (OAuth2 systems), collect the texts as in step 3 and
   pass `--sap-texts <file>`. Then set `date_format`, and run `ruff format` on the file.
2. **Register the pack** in `__init__.py` (`_PACKS`). Do this before verifying: `--verify` and the
   config accept only registered codes (`--draft` and `--print-sql` accept any 2-character key; with direct ADT access `--draft` rejects a key missing from `T002`). The
   code is then accepted as `language` in `systems.json`, because the config takes its list from
   `logon_languages()` (the full packs, then the core packs).
3. **Settle every `TODO` from SAP, not from a dictionary.** The source of most fields is recorded
   in `sources.py`, so the lookup is a query: `--print-sql` prints the SQL for every sourced field.
   Run it through ADT (`run_query`; these tables are development metadata). For `Manual` fields,
   log on in the new language and read the screen (window titles, framework texts). Fields
   that are deliberately identical to EN go into `same_as_en`; the untranslated-field test rejects
   any other value equal to EN. Remove each `TODO` comment once settled.
4. **Verify against SAP** on every release you support:
   `uv run python scripts/harvest_lang_texts.py IT --verify --system "<key>"`. If a system is not
   reachable directly, use `--sap-texts <file>` with the results of `--print-sql`. Fix every
   drift, or turn the field into `Manual("SAP text differs: ...")` with the exact difference.
5. **Test pack and fixtures.** Add the language to `unittests/testdata/lang_test.py`. The desktop
   tests take their test texts from it, selected by `SAP_LANGUAGE=<XX>`.
6. **Run the guards:**
   `uv run --group tests pytest unittests/lang unittests/test_no_ui_literals.py -q`. This covers
   completeness, equal flags across packs, the pseudo-locale tests and the no-literal scanner.
7. **Live tests logged on in the new language**, on every release you
   support. Point `SAP_CONFIG_FILE` at a copy of `systems.json` whose system has the new logon
   language, set `SAP_LANGUAGE=<XX>` as well, and run the integration tests of every transaction. Compare each failure with the
   same test in DE or EN before calling it a language problem.

## What to look out for

These are lessons from migrating DE and EN (#1044, PRs #1055–#1061):

- **SAP mixes languages on one screen.** On a German logon, SE24 shows its visibility and
  method-kind cells (`Public`, `Static Method`) in English, because the domain has no German
  texts. The merged view appends EN to every session pack, so this usually just works. Do not
  remove EN variants by hand, and check such cells live.
- **Releases differ.** The same field can read "Dynpro Number" on S/4HANA and "Screen number" on
  ECC, and the SM30 button reads "Edit" on one release and "Maintain" on the other. Message
  numbers differ too: SE11 "does not exist" is E2 503 on S/4HANA and E2 007 on ECC. Keep every
  release's spelling as a variant and verify on each release.
- **Window titles are not transaction titles.** `TSTCT` holds "ABAP Class Builder", while the
  window says "Class Builder: Initial Screen". Initial-screen checks need the window title, read
  live.
- **Case sensitivity is part of the meaning.** WebGUI matches field labels and titles exactly
  (`===` in JS, `!==` in `fill_field_with_keyboard`). Declare such fields `fold=False` and keep
  every capitalisation SAP uses ("Function Module" and "Function module"). Flags (`fold`, `word`)
  must be the same in every pack, and the guard checks that.
- **Short fragments match too much.** A text checked with `contains()` over a whole snapshot
  ("No logs", "nicht vorhanden") also matches result data. Keep such texts long, or check them
  only where the message appears (status bar, note lines).
- **Popup and activation keywords** (`popup.type_*`, `status_type.activation_*`) apply to every
  session (`universal()`). A new language's keyword must never be part of a real EN or DE text
  ("Execute" vs "executed"), so keep them specific; `test_core_pack.py` guards this.
- **Prefer technical IDs over texts.** Before adding a text, check whether the code can use a
  field name (`GD-TAB`), a column `Name`, the program and screen number (`SAPLSD_ENTRY` / `1000`),
  a T100 message ID or a WebGUI `lsdata` attribute. Use it only if it is identical on every
  release.
- **Templates.** A trailing placeholder captures up to the end of the line. Use explicit names
  (`{name}`) and check the result on a real screen, not only on a one-line test string.
- **Numbers and dates.** Hit counts accept every group separator. The date tools type dates in
  the user's own date format, read off the date field they pre-fill (#1043); the pack's
  `date_format` is only the fallback when that field is empty or unreadable.
- **Known limitation:** `tools/breakpoint_tools.py` is not migrated (#1025) and still expects DE
  or EN.

## Backend tags (#1099)

Every field of a pack section is tagged with the backend code that reads it in `lang/backends.py`
(`BACKEND_OF`: `"se16.results_title": Backend.DESKTOP`). `Backend.BOTH` marks texts that shared
code reads, and is also the safe tag when unsure. A new field needs a tag in the same change as its
entry in `schema.py`; `unittests/lang/test_backend_tags.py` derives the tag from the source (where
the field is read, see the docstring of that test) and fails on a missing tag, on a wrong tag and
on a field nothing reads.
