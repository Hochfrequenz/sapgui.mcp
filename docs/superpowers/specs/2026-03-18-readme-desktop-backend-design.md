# Design: README Update for Desktop Backend

**Date:** 2026-03-18
**Goal:** Document the desktop (SAP GUI COM) backend in the README so .exe users know how to choose between desktop and WebGUI backends.

---

## Problem

The README only describes the WebGUI (browser-based) backend. The desktop backend (`BACKEND_TYPE=desktop`) shipped in the multi-session PR (#398) but is undocumented. Users downloading the .exe have no guidance on how to use it.

## Changes

### 1. Intro text (lines 8–9)

Update the tagline to mention both backends:

> An MCP (Model Context Protocol) server for SAP automation.
> Control SAP through Claude Desktop or Claude Code — via **SAP GUI desktop** (COM) or **SAP Web GUI** (browser).

### 2. Standalone Executable section — two sub-paths

Restructure the `.exe` `<details>` block. Replace the current single flow with two clearly labeled options:

#### Option A: Desktop Backend (SAP GUI) — presented first

**Windows-only.** Requires SAP GUI for Windows with scripting enabled.

**Prerequisites:**
- SAP GUI for Windows installed
- SAP GUI Scripting enabled (server + client)

**Enable scripting (one-time):**
- Server: transaction `RZ11` → set `sapgui/user_scripting` to `TRUE` (dynamic, no restart needed; user must re-login)
- Client: SAP GUI Options → Accessibility & Scripting → Scripting → check "Enable Scripting", uncheck both notification checkboxes (if left checked, every COM connection triggers a modal popup that blocks automation)

**Config examples** (Claude Desktop + Claude Code):
- `BACKEND_TYPE` set to `desktop`
- `SAP_CONNECTION_NAME` — the display name from SAP Logon pad (e.g. `"HF S/4"`)
- `SAP_USER`, `SAP_PASSWORD`, `SAP_MANDANT`, `SAP_LANGUAGE` — same as today
- No `SAP_URL`, no `BROWSER_MODE`, no `CDP_URL` needed
- Optional `GITHUB_PAT`

No Chrome, no CDP proxy required.

#### Option B: WebGUI Backend (Browser) — current content

Move existing .exe content (Chrome + CDP steps) under this heading. Add `BACKEND_TYPE=webgui` to the env examples (or note it's the default). No other changes to this sub-section.

### 3. Configuration Reference table

Add two rows and update conditionally-required annotations:

| Variable | Required | Description | Default |
|---|---|---|---|
| `BACKEND_TYPE` | No | `webgui` (browser automation) or `desktop` (SAP GUI COM, Windows only) | `webgui` |
| `SAP_CONNECTION_NAME` | When `BACKEND_TYPE=desktop` | SAP Logon pad connection entry name (e.g. `"HF S/4"`) | — |

Update `SAP_URL` required column: change from "Yes" to "When `BACKEND_TYPE=webgui`" (it is ignored by the desktop backend).

### 4. Architecture diagram

Add a second path below the existing one:

```
Desktop Backend (BACKEND_TYPE=desktop):

┌─────────────────────────────────────────────────────────┐
│  SAP GUI for Windows                                    │
│  - COM Scripting API                                    │
│  - Persistent session(s)                                │
└─────────────────────────────────────────────────────────┘
            ↑
            │ COM (pywin32)
            ↓
┌─────────────────────────────────────────────────────────┐
│  MCP Server (sapguimcp)                              │
│  - Desktop backend with COM thread                      │
│  - SAP-specific tools                                   │
└─────────────────────────────────────────────────────────┘
            ↑
            │ MCP (stdio)
            ↓
┌─────────────────────────────────────────────────────────┐
│  Claude Desktop / Claude Code                           │
└─────────────────────────────────────────────────────────┘
```

Label the existing diagram as "WebGUI Backend (BACKEND_TYPE=webgui):" for symmetry.

### 5. Docker and Development Setup sections

No changes. Docker is WebGUI-only. Development setup could mention `BACKEND_TYPE=desktop` but that's out of scope for this task — the .exe path is the priority.

## Known follow-ups (out of scope for this task)

- **Available Tools table** — browser tools don't apply to desktop backend; add a note or split the table. For now, leave as-is.
- Documenting desktop-specific tools (COM evaluate, multi-session) — those are advanced and can come later
- Updating CONTRIBUTING.md for desktop dev workflow
- Adding desktop info to Docker section

## Success criteria

- A user downloading the .exe can choose desktop or WebGUI by reading the README
- `BACKEND_TYPE` appears in the Configuration Reference
- Architecture diagram shows both paths
