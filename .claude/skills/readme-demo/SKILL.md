---
name: readme-demo
description: >
  End-to-end demo of this MCP server for the project README and for users who
  want to see it in action: log into an SAP system, create a business partner
  (Max Mustermann by default), save it with Ctrl+S, capture a screenshot for
  the documentation, and verify the partner in SE16 (table BUT000). Use when
  the user says "run the readme demo", "demo the SAP MCP server", or invokes
  /readme-demo. Announce each step in one short chat sentence so the run reads
  as a story, and capture a numbered screenshot after every SAP-visible step.
---

# README Demo

You are demonstrating this MCP server end to end. The run produces two things:
a readable chat story (the sentences you say between steps) and the artifacts
that prove the work (screenshots, transcript).

**Work directory:** `/readme-demo/` (repo-root-relative, git-ignored). Create
it if missing. It receives `transcript.md` and `frames/` (create `frames/`
before the first capture).

**Data:** use obviously fake data — first name `Max`, last name `Mustermann`
(unless the user passed other values), street `Teststraße 1`, postal code
`12345`, city `Testhausen`, country `DE`. Never use real personal data.

**Optional arguments:** partner first/last name, address, system key
(default: the default system in `systems.json`).

## How to run the demo

Work through the beats below. For every beat:

1. Say one short chat sentence announcing what you are about to do (plain
   language, no JSON, no internal jargon — the reader is a first-time user).
2. Call the tool.
3. If the beat captures a frame (see the list), save it to the named file
   under `readme-demo/frames/` with the `hard_copy` script described below
   (`sap_screenshot` only shows you the picture, it cannot save a file). For
   beats with overlays, read the rectangles in that same script.
4. Append the beat to `readme-demo/transcript.md` in the sidecar format
   below. `tool=` names the beat's primary tool; `frame=` references the
   screenshot file (relative to `readme-demo/`), when the beat has one.

**Once, right after `sap_login`** (before the first frame): create
`readme-demo/frames/` and shrink the SAP window so its text stays legible at
GIF size — `wnd.restore()` then `wnd.resize_working_pane(100, 22, False)` via
`sap_run_script` (gives a frame of about 1045×900 px; check the first PNG's
size). Do not resize again during the run: the overlay coordinates below are
only valid for the window size the frame was captured at.

Do not add artificial waits between steps. Pacing happens later at GIF
assembly time, outside this skill.

### How to capture frames (important)

`sap_screenshot` returns the picture to *you* (the agent sees it) but cannot
save it to disk. To write a frame file, use `sap_run_script` (desktop backend)
with the COM `hard_copy` call — the same way the server itself implements
screenshots. Absolute path required:

```python
# via sap_run_script, one shot per frame:
wnd = session.find_by_id("wnd[0]")
wnd.hard_copy(r"C:\<absolute path to repo>\readme-demo\frames\03_bp_initial.png", 2)
output("frame saved")
```

(`2` = PNG. `open()`/`import` are sandbox-blocked, but the injected
`session` object writes the file through COM — no `open()` needed. After the
first frame, check that the PNG exists at that path before proceeding; if it
does not, the path form is wrong.)

### Beats

| Beat | Say | Do | Frame (if any) |
| --- | --- | --- | --- |
| 1 | State the whole task in one sentence. | — (no tool call; transcript block is `role=user` with the user's prompt text) | none of its own — write `frame=frames/02_easy_access.png` (the later beat-2 frame) |
| 2 | "Logging into the dev system…" | `sap_login(system_key=…)` | `frames/02_easy_access.png` |
| 3 | "Opening transaction BP…" | `sap_transaction(tcode="bp")` | `frames/03_bp_initial.png` |
| 4 | "Creating a person…" | `sap_press_key(key="F5")` (if a type-selection popup appears — visible as `wnd[1]` in the `sap_press_key` response's `active_window` — confirm it with `sap_press_key(key="Enter")`) | `frames/04_bp_empty.png` |
| 5 | "Filling in name and address…" | `sap_fill_form({...})` — see field table | `frames/05_bp_filled.png` |
| 6 | "Saving…" | `sap_press_key(key="Ctrl+S")` | none of its own — write `frame=frames/07_bp_saved.png` (the later beat-7 frame) |
| 7 | "Capturing a screenshot for the documentation…" | `sap_screenshot` (shows you the picture) + `sap_run_script` `hard_copy` → `frames/07_bp_saved.png`, and a second `hard_copy` in the same script → `readme-demo/BP_<Nachname>.png` | `frames/07_bp_saved.png` |
| 8 | "Now verifying it exists in SE16…" | `sap_se16_query(table="BUT000", filters={"PARTNER": "<GP number>"})` (leaves the result list on screen for the frame) | `frames/08_se16_result.png` |
| 9 | "✓ Partner <GP number> exists in BUT000, screenshot saved as BP_<Nachname>.png." | — (report to the user) | none of its own — repeat `frame=frames/08_se16_result.png` |

Beat numbering in `transcript.md` follows the table. If a step needs extra
tool calls (field discovery, popup handling), fold them into the narrative of
the current beat — do not invent new beats.

### BP form fields (labels are the keys for `sap_fill_form`)

| Key | Value |
| --- | --- |
| `Anrede` | (leave default unless user specified) |
| `Vorname` | `<first name>` |
| `Nachname` | `<last name>` |
| `Straße/Hausnummer` | `<street>` |
| `Postleitzahl/Ort` | `<postal code>` |
| `Ort` | `<city>` |
| `Land` | `DE` |

> `Postleitzahl/Ort` labels the whole address row and resolves to the postal
> code field; `Ort` addresses the city field in the same row, which has no
> separate visible label. Both keys are required.

If `sap_fill_form` reports `not_found` fields, call `sap_discover_fields` to
read the system's actual labels, adjust the keys, and retry. If the status
bar reports a duplicate or validation error after `Ctrl+S`, show the message
to the user and stop — do not create duplicates on purpose. If the flow needs
repeated manual correction that this file did not anticipate, report that
upstream instead of silently patching this skill.

### Save and result evaluation

`Ctrl+S` is the save action. The `sap_press_key(key="Ctrl+S")` response
carries `status_bar_type` and `status_bar_message` — read the result directly
from that response; no separate `sap_read_status_bar` call is needed. On
`type=S` (success), extract the business partner number from the message. If
the message carries no partner number or the type is not `S`, show it to the
user and stop (you may re-read the status bar with `sap_read_status_bar`).
Report it in beat 9 and use it as the `PARTNER` filter in beat 8. Note: run
beat 7's screenshot *after* the successful save so the status bar shows the
success message.

### Transcript sidecar format

```markdown
[beat 1] role=user frame=frames/02_easy_access.png
<the user's one-sentence task>

[beat 2] role=assistant frame=frames/02_easy_access.png
Logging into the dev system…
tool=sap_login

[beat 3] role=assistant frame=frames/03_bp_initial.png
Opening transaction BP…
tool=sap_transaction
mark=20,91,156,26 Transaction: BP

[beat 6] role=assistant frame=frames/07_bp_saved.png
Saving…
tool=sap_press_key
status=8,853,1029,40 <status bar message>
```

Rules:

- One block per beat; blocks are separated by a blank line, so there are no
  blank lines inside a block.
- The header is `[beat N] role=… frame=…`. `role=` is `user` or `assistant`
  (`title` exists for a title card, which the demo does not use). `frame=` is
  optional, relative to `readme-demo/`, and may repeat an earlier file.
- Then the message text, then — each on its own line, never in the header —
  `tool=` (assistant beats only; the beat's primary tool, fold retries and
  popup handling under it) and the overlay lines below.

**Overlays (assistant beats only, optional):** `mark=x,y,w,h caption` draws an
orange ring and caption pill around an element of the frame; `status=x,y,w,h text`
draws the status-bar message (the screenshot does not render it; at most one
per beat). `x,y,w,h` are four plain integers separated by commas — no spaces,
brackets or minus signs — in pixels *of the captured frame*. A malformed line
is a parse error in the renderer.

Which beats get overlays: beat 3 marks the command field (`Transaction: BP`),
beat 4 the `Person` toolbar button (`F5 = Person`), beat 5 each filled field
(caption = the value, e.g. `Max`), beat 6 and beat 7 carry the same `status=`
line (the status bar text after the save), beat 8 and beat 9 mark the result
list if you can locate that control (its id differs between SE16 variants;
otherwise skip it). Beats 1 and 2 have none.

Read the rectangles live via COM in the **same `sap_run_script` call that saves
the frame**, after the beat's SAP action. This script prints ready-made lines:

```python
wnd = session.find_by_id("wnd[0]")
wx, wy = wnd.screen_left, wnd.screen_top

def rect(el):  # element position relative to the window = pixel position in the frame
    return "%d,%d,%d,%d" % (el.screen_left - wx, el.screen_top - wy, el.width, el.height)

wnd.hard_copy(r"C:\<absolute path to repo>\readme-demo\frames\03_bp_initial.png", 2)
output("mark=" + rect(session.find_by_id("wnd[0]/tbar[0]/okcd")) + " Transaction: BP")
sbar = session.find_by_id("wnd[0]/sbar")
output("status=" + rect(sbar) + " " + sbar.text)   # beats 6 and 7
```

Toolbar buttons are under `wnd[0]/tbar[1]` (match on `.text`, e.g. `Person`).
Form fields are nested deep in subscreens: take their ids from
`sap_discover_fields`, or find them with a recursive walk over `.children`
that matches the end of the id (`txtBUT000-NAME_FIRST`, `txtBUT000-NAME_LAST`,
`txtADDR2_DATA-STREET`, `txtADDR2_DATA-POST_CODE1`, `txtADDR2_DATA-CITY1`,
`ctxtADDR2_DATA-COUNTRY`):

```python
def find_by_suffix(node, suffix, depth=0):
    if depth > 14:
        return None
    try:
        kids = node.children
    except Exception:
        return None
    for kid in kids:
        if kid.id.endswith(suffix):
            return kid
        hit = find_by_suffix(kid, suffix, depth + 1)
        if hit is not None:
            return hit
    return None
```

If an element cannot be found or reports a zero size, skip that mark — marks
are optional and must never block the run.

### After the run

Tell the user: partner number, screenshot path, SE16 confirmation, and where
the artifacts live (`readme-demo/`). If the user wants the README GIF, point
them to `scripts/README.md` (render + ffmpeg commands) — that step is
maintainer-side.

### An improved internal recipe

An improved internal skill for creating business partners may be installed in
this environment (it is not part of this repository). If present, you may
prefer it for the beat 3–6 flow; it handles more edge cases (role/grouping
prompts, company-code data). When in doubt or when fields mismatch, fall back
to the flow above — it is authoritative for this demo.
