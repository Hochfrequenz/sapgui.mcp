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

## Procedure

1. **Draft the pack.** Run
   `uv run python scripts/harvest_lang_texts.py IT --draft [--system "<key>"] --out src/sapguimcp/lang/it.py`
   on a system that has the language installed with its texts (`T002`, and texts in `DD04T`; a
   system that only lists the language yields no SAP text). The draft is a copy of `en.py`:
   sourced `Text` fields hold SAP's text; `Manual`, fragment and `Template` / `RegexText` fields
   keep the EN value with a `# TODO` comment, and flags and kinds stay those of EN. It never
   registers the pack. Without direct access (OAuth2 systems), collect the texts as in step 3 and
   pass `--sap-texts <file>`. Then set `html_lang` (the ISO code the WebGUI page reports in
   `<html lang>`, e.g. `"it"`), `logon_dropdown` (the language's name in the WebGUI logon
   dropdown) and `date_format`, and run `ruff format` on the file.
2. **Register the pack** in `__init__.py` (`_PACKS`). Do this before verifying: `--verify` and the
   config accept only registered codes (`--draft` and `--print-sql` accept any 2-character key; with direct ADT access `--draft` rejects a key missing from `T002`). The
   code is then accepted as `language` in `systems.json`, because the config takes its list from
   `supported_languages()`.
3. **Settle every `TODO` from SAP, not from a dictionary.** The source of most fields is recorded
   in `sources.py`, so the lookup is a query: `--print-sql` prints the SQL for every sourced field.
   Run it through ADT (`run_query`; these tables are development metadata). For `Manual` fields,
   log on in the new language and read the screen (window titles, WebGUI framework texts). Fields
   that are deliberately identical to EN go into `same_as_en`; the untranslated-field test rejects
   any other value equal to EN. Remove each `TODO` comment once settled.
4. **Verify against SAP** on every release you support:
   `uv run python scripts/harvest_lang_texts.py IT --verify --system "<key>"`. If a system is not
   reachable directly, use `--sap-texts <file>` with the results of `--print-sql`. Fix every
   drift, or turn the field into `Manual("SAP text differs: ...")` with the exact difference.
5. **Test pack and fixtures.** Add the language to `unittests/webgui/testdata/lang_test.py`. Capture
   WebGUI snapshots in the new language next to the existing `*_de` / `*_en` files and add parser
   tests for them. Set `SAP_LANGUAGE=<XX>` while capturing: the WebGUI tests take their test texts
   and the snapshot file suffix from it.
6. **Run the guards:**
   `uv run --group tests pytest unittests/lang unittests/test_no_ui_literals.py -q`. This covers
   completeness, equal flags across packs, regex and JS portability (Node), the pseudo-locale
   tests and the no-literal scanner.
7. **Live tests logged on in the new language**, on desktop and WebGUI and on every release you
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
- **Status-bar noise and popup buttons** (`status_type.noise`, `popup.button_labels`) apply to
  every session (`universal()`). A new language's noise word must never be part of a real
  message ("Execute" vs "executed"), so keep them case-sensitive and specific.
- **Prefer technical IDs over texts.** Before adding a text, check whether the code can use a
  field name (`GD-TAB`), a column `Name`, the program and screen number (`SAPLSD_ENTRY` / `1000`),
  a T100 message ID or a WebGUI `lsdata` attribute. Use it only if it is identical on every
  release.
- **Templates.** A trailing placeholder captures up to the end of the line. Use explicit names
  (`{name}`) and check the result on a real screen, not only on a one-line test string.
- **Numbers and dates.** Hit counts accept every group separator. The date format still comes
  from the pack's `date_format`, not from the user's own settings (#1043).
- **Known limitation:** `tools/breakpoint_tools.py` is not migrated (#1025) and still expects DE
  or EN.
