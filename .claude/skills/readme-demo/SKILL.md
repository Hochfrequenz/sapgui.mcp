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
3. If the beat captures a frame (see the list), call `sap_screenshot` and save
   the image to the named file (saved as described below) under
   `readme-demo/frames/`.
4. Append the beat to `readme-demo/transcript.md` in the sidecar format
   below. `tool=` names the beat's primary tool; `frame=` references the
   screenshot file (relative to `readme-demo/`), when the beat has one.

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
`session` object writes the file through COM — no `open()` needed. Verify the
absolute path form on the first live frame before proceeding with the run.)

### Beats

| Beat | Say | Do | Frame (if any) |
| --- | --- | --- | --- |
| 1 | State the whole task in one sentence. | — (no tool call; transcript block is `role=user` with the user's prompt text) | (references beat 2's frame: `frames/02_easy_access.png`) |
| 2 | "Logging into the dev system…" | `sap_login(system_key=…)` | `frames/02_easy_access.png` |
| 3 | "Opening transaction BP…" | `sap_transaction(tcode="bp")` | `frames/03_bp_initial.png` |
| 4 | "Creating a person…" | `sap_press_key(key="F5")` (if a type-selection popup appears — visible as `wnd[1]` in the `sap_press_key` response's `active_window` — confirm it with `sap_press_key(key="Enter")`) | `frames/04_bp_empty.png` |
| 5 | "Filling in name and address…" | `sap_fill_form({...})` — see field table | `frames/05_bp_filled.png` |
| 6 | "Saving…" | `sap_press_key(key="Ctrl+S")` | (beat 6 references beat 7's frame) |
| 7 | "Capturing a screenshot for the documentation…" | `sap_screenshot` (shows you the picture) + `sap_run_script` `hard_copy` → `frames/07_bp_saved.png`, and copy that file as `readme-demo/BP_<Nachname>.png` | `frames/07_bp_saved.png` |
| 8 | "Now verifying it exists in SE16…" | `sap_se16_query(table="BUT000", filters={"PARTNER": "<GP number>"})` (leaves the result list on screen for the frame) | `frames/08_se16_result.png` |
| 9 | "✓ Partner <GP number> exists in BUT000, screenshot saved as BP_<Nachname>.png." | — (report to the user) | (holds beat 8's frame) |

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

[beat 2] role=assistant
Logging into the dev system…
tool=sap_login

[beat 8] role=assistant frame=frames/08_se16_result.png
Now verifying it exists in SE16…
tool=sap_se16_query
```

Rules: one block per beat; `role=` is `user`, `assistant`, or `title`; `tool=`
names the beat's primary tool (fold retries and popup handling under it); only
on assistant beats; `frame=` may repeat an earlier beat's file.

**Overlays (optional, assistant beats only):** `mark=x,y,w,h caption` draws an
orange ring (and caption pill) around an element of the frame, and
`status=x,y,w,h text` draws the status-bar message (the screenshot does not
render it). Coordinates are pixels *in the captured frame*, read live via COM
in the same `sap_run_script` call that saves the frame:

```python
wnd = session.find_by_id("wnd[0]")
wx, wy = wnd.screen_left, wnd.screen_top
el = session.find_by_id("wnd[0]/tbar[0]/okcd")
output([el.screen_left - wx, el.screen_top - wy, el.width, el.height])  # -> mark=x,y,w,h
output(session.find_by_id("wnd[0]/sbar").text)                          # -> status text
```

Before the first frame, shrink the window so SAP text stays legible at GIF
size: `wnd.restore()` then `wnd.resize_working_pane(100, 22, False)` (about
1045×900 px). Marks for `sap_fill_form` fields can be found by walking
`wnd[0]/usr` children and matching the id suffix (e.g. `txtBUT000-NAME_FIRST`).

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
