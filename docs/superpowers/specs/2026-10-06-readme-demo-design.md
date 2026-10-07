# README Demo Design

**Date:** 2026-10-06
**Status:** Approved (brainstorming session)
**Related:** follow-up to PR #893 (its demo GIF was out of scope; this design delivers it), #936/#937/#789/#798 are unrelated open bugs, not blockers for this work.

## Goal

A GIF in the project README that shows the MCP server in action: a chat with
Claude Desktop on the left, the real SAP GUI reacting on the right. The viewer
should understand "I chat, SAP does the work" in one glance, without any MCP,
JSON, or SAP expertise. It should look helpful, not technical.

The GIF is **dual-purpose**: it is produced by a demo skill that is also
documented in the README so users can run the same demo themselves against
their own system.

## Scope

**In scope**
- A demo skill `readme-demo` (tracked in the repo, see "The skill" section for
  location and rationale) that choreographs the demo run and emits a
  transcript + screenshot frames.
- A deterministic assembler script (`scripts/render_readme_demo.py`) that
  composites transcript + frames into per-beat PNGs.
- A documented ffmpeg command that turns the composite PNGs into the final GIF.
- The GIF embedded near the top of the README, plus a short "run this demo
  yourself" note pointing at the skill.

**Out of scope**
- Recording real screen video (we build a staged composite instead, see
  Approach below).
- Redaction of system IDs: the maintainer has explicitly waived the
  CLAUDE.md "no internal identifiers" rule for the demo system IDs visible in
  the SAP GUI title/status bars. Hostname-exposing screens (e.g. System →
  Status) stay out of the flow anyway.
- Naming internal private repositories in any committed file. An internal
  skill for creating business partners is maintained in a private internal
  repository; committed files must refer to it only descriptively (see "The
  skill").
- Any change to the server runtime or tools.

## Demo scenario

One continuous story, chosen to exercise login, create, save, screenshot,
and verify:

> "Log into the dev system, create business partner **Max Mustermann** with a
> test address, save it, take a screenshot for the documentation, and verify
> in SE16 that it exists."

Fixed fake data throughout (name, street, `12345 Testhausen`), so no real
personal data can leak. The partner number assigned by SAP is shown as-is.

### Storyboard (9 beats, ≈27 s final GIF)

| # | Chat says | SAP shows |
|---|-----------|-----------|
| 1 | **User:** the task (one sentence, see above) | SAP Easy Access (captured post-login; placed here at assembly time) |
| 2 | "Logging into the dev system…" `▸ sap_login` | Easy Access after login |
| 3 | "Opening transaction BP…" `▸ sap_transaction` | BP initial screen |
| 4 | "Creating a person…" `▸ sap_click_button` / key F5 | BP create screen (empty) |
| 5 | "Filling in name and address…" `▸ sap_fill_form` | Filled form |
| 6 | "Saving…" `▸ sap_press_key Ctrl+S` | Status bar: "Business partner … created" |
| 7 | "Capturing a screenshot for the documentation…" `▸ sap_screenshot` | The saved BP — this frame *is* the demo's own screenshot |
| 8 | "Now verifying it exists in SE16…" `▸ sap_se16_query` | SE16 result: the BUT000 row |
| 9 | "✓ Partner <num> exists in BUT000, screenshot saved." | SE16 result, held, ✓ overlay in chat |

### Layout

Side-by-side composite, 1280×640: chat panel 480px left, SAP panel 800px
right (the two panels fill the canvas), title bar on top, 24px internal
padding within each panel. Chat bubbles appear one by one; each assistant
bubble carries one muted tool chip (`▸ sap_login`). Tool chips are the only
technical element — they say "MCP tools" at a glance without JSON. SAP frames
are real captures of the SAP window (`hard_copy` via `sap_run_script`), scaled
uniformly, never squashed. Hard cuts between beats, no transitions.

Chat text must remain legible at GitHub's GIF render width (~880px), i.e.
≥14px effective size at final width.

## Approach

Chosen over three options discussed:

1. ~~Real screen recording~~ — chat becomes unreadable at GIF width, dead time
   needs cutting, retakes are painful.
2. **Staged composite (chosen)** — run the real task once; rebuild the
   animation from the real transcript and real per-beat screenshots with
   deliberate pacing. Clarity beats authenticity for a README, and the raw
   material comes free from the run itself.
3. ~~Hybrid crop/overlay of a real recording~~ — middle ground, but still
   requires manual retakes.

**Honesty requirement:** the composite contains only real messages and real
screenshots from a real run; only the timing is edited. The PR description
must state this explicitly.

**Overlays (what the renderer adds):** orange rings and short caption pills mark
the screen element the agent operates, and the status-bar message is drawn as
text. The SAP screenshot cannot render that message in this theme, although COM
returns it. Both come from the same live run: element rectangles are read via
COM (position relative to the window = pixel position in the captured frame)
and the message text from the status bar. Nothing is hand-placed or invented.
The SAP window itself is resized for the run (`resize_working_pane`, 100×22
characters, about 1045×900 px) so SAP text stays readable at GIF size.

## The skill

**Name:** `readme-demo`.

**Location:** `.claude/skills/readme-demo/SKILL.md`, **tracked in git**.
`.gitignore` currently excludes all of `.claude/` in directory form
(`.claude/`), and git cannot re-include a path under an excluded directory —
a plain `!.claude/skills/` negation is silently dead. The plan therefore
switches the entry to glob form, which makes the skill trackable while
ignoring everything else in `.claude/`:

```gitignore
.claude/*
!.claude/skills/
.claude/skills/*
!.claude/skills/readme-demo/
```

This is required for the dual-purpose goal: the README points readers at the
skill, so it must exist in the repo. `.claude/skills/` is the standard
discovery location for Claude Code project skills; for Claude Desktop the
maintainer should confirm during production that the repo skill is picked up
(or note the import step in SKILL.md). A tracked path elsewhere (such as the
existing recipe store `src/sapguimcp/skills/examples/`) would not be
auto-discovered.

**Trigger:** "run the readme demo", "demo the SAP MCP server",
`/readme-demo`. Optional args: partner name, address, system key; defaults:
Max Mustermann, test address, default system from `systems.json`.

**BP creation: inline recipe, optional internal upgrade.** There is a
high-quality BP-creation recipe maintained internally in a private internal
skills marketplace. That marketplace is **private** and must not
be named in any committed file (the repo is public; CLAUDE.md forbids
disclosing internal tooling). Therefore:

- The committed SKILL.md contains the **full inline BP flow itself** — open
  BP, choose type (F5 for person), `sap_fill_form` with the visible-label
  keys (including the `"Postleitzahl/Ort"` + `"Ort"` address-row convention),
  `Ctrl+S`, evaluate `status_bar_type`/`status_bar_message` from the
  `sap_press_key` response, extract the GP number, handle the common error
  cases (`not_found` fields → `sap_discover_fields`; duplicate/validation
  errors → report to user). This is the documented path for everyone.
- A single descriptive sentence (no repo/marketplace names) may note that an
  improved internal recipe may be loaded *if installed*; if absent, the
  inline flow is authoritative. External users always use the inline flow.
- The inline flow is distilled from the internal recipe's hard-won specifics
  (label conventions, status-bar evaluation), so it is not a degraded
  fallback but the primary path.

**Behavior:**

1. `sap_login` (system key from arg), `sap_transaction("bp")`.
2. **Capture a frame after every SAP-visible step.** Each storyboard beat
   needs its own real screenshot, and tool responses carry no images — a
   frame not captured during the run cannot be added later. So after each
   SAP-visible step the agent saves a `hard_copy` capture (via `sap_run_script`; `sap_screenshot` cannot write files) into
   `readme-demo/frames/` with a beat-numbered name:
   - `02_easy_access.png` — post-login Easy Access (also serves beat 1, which
     is placed at assembly time)
   - `03_bp_initial.png` — after `sap_transaction("bp")`
   - `04_bp_empty.png` — after F5/type selection
   - `05_bp_filled.png` — after `sap_fill_form`
   - `07_bp_saved.png` — after `Ctrl+S` with the success status bar; also kept
     as `readme-demo/BP_<Nachname>.png`, the screenshot path reported to the
     user (beat 6 references this same capture)
   - `08_se16_result.png` — the SE16 result (see step 5)
3. Between steps the agent appends one short chat sentence + tool chip to
   `readme-demo/transcript.md` (format below). No artificial sleeps — pacing
   happens only at GIF assembly time.
4. BP creation per the inline flow above; extract the new GP number from the
   status bar message.
5. Verify: `sap_transaction("se16")` → table `BUT000` → filter
   `PARTNER = <GP number>` → confirm the row → **`sap_screenshot` of the SE16
   result** as `readme-demo/frames/08_se16_result.png` (beat 8 needs its own
   frame); append the verification beat and final summary beat.
6. Report result to the user in chat (GP number, screenshot path, SE16
   confirmation).

**Maintenance note (in SKILL.md):** if the BP flow reports unexpected field
errors, resolve them with `sap_discover_fields` and report upstream rather
than patching the demo skill silently.

**Working directory:** `/readme-demo/`, repo-root-relative, **added to
`.gitignore` by the plan** as `/readme-demo/` (currently it isn't ignored —
stating it here does not ignore it). Contains: `transcript.md`, `frames/`
(input frames), `composite/` (assembler output, separate directory so re-runs
never re-ingest the assembler's own output), `BP_<Nachname>.png`.

## Transcript format

Plain markdown sidecar, one block per beat:

```markdown
[beat 2] role=assistant
Logging into the dev system…
tool=sap_login
```

Optional keys: `tool=` (muted chip under the bubble), `frame=` (screenshot
file in `frames/` to show during this beat; beats without one hold the
previous frame — an explicit repeat of an earlier frame's file name is also
valid, e.g. beat 6 referencing `07_bp_saved.png`). `role=user|assistant`.

Example with a frame (beat 8, SE16 verification):

```markdown
[beat 8] role=assistant frame=frames/08_se16_result.png
Now verifying in SE16 that it exists…
tool=sap_se16_query
```

## Assembler and GIF

**`scripts/render_readme_demo.py`** (dev-only dependency: Pillow):

- Inputs: `readme-demo/transcript.md`, `readme-demo/frames/`; output to
  `readme-demo/composite/` (kept separate from the input frames directory so
  a re-run never re-ingests its own output).
- Fixed 1280×640 canvas: chat 480px, SAP 800px (panels fill the canvas), 24px
  internal padding within each panel.
- Renders one composite PNG per beat (full chat history so far + current
  frame) to `readme-demo/composite/composite_NN.png`.
- Emits an ffmpeg concat file with per-beat durations (a timing table in the
  script, tuned once during production).

**GIF encode:** a single documented ffmpeg command (palettegen/paletteuse) in
`scripts/README.md` — kept out of the Python script on purpose.

**Unit tests** (offline, per CONTRIBUTING): transcript parser (all key
combinations, malformed lines rejected), layout math (bubble wrapping, canvas
sizes), assembler produces one composite per beat from fixture inputs. Tests
live in `unittests/` following the existing `test_*.py` naming. **Pillow** is
added to the `tests` dependency group in `pyproject.toml` (pinned, like its
siblings; `default-groups = []` means nothing is implicit). The final GIF
encode itself is not unit-tested.

## Testing / acceptance

- [ ] Skill exists at the tracked path `.claude/skills/readme-demo/SKILL.md`
      (committed — `.gitignore` negation in place); triggers on the documented
      phrases; contains the full inline BP flow.
- [ ] `readme-demo/` is git-ignored.
- [ ] A real run against the test system produces `transcript.md` + frames
      matching the storyboard: all six frame files from Behavior step 2 exist
      (`02_easy_access.png`, `03_bp_initial.png`, `04_bp_empty.png`,
      `05_bp_filled.png`, `07_bp_saved.png`, `08_se16_result.png`).
- [ ] Assembler tests pass offline (`pytest -k readme_demo`).
- [ ] `scripts/render_readme_demo.py` renders composites; ffmpeg command
      documented in `scripts/README.md` produces the GIF.
- [ ] README embeds the GIF near the top with a one-line caption and a
      "run this demo yourself" pointer to the skill.
- [ ] PR description states the honesty note (staged composite of a real run).
