# Design: Elicitation-Based Confirmation for `sap_breakpoint_set`

**Date:** 2026-07-07
**Repo:** https://github.com/Hochfrequenz/sapgui.mcp
**Type:** Feature Design
**Related:** #791, #797 (this lands as a follow-up commit on PR #797)

---

## Context & Motivation

`sap_breakpoint_set`'s tool description already tells the calling agent, in prose, to
"ask the human operator for explicit permission" before arming a breakpoint — because a
live repro (issue #791) showed that firing an external ABAP breakpoint can open a modal
SAP GUI debugger that collapses every other open session for the agent, with no in-band
recovery.

That instruction is pure docstring text. Nothing in the code enforces it: an LLM client
can call `sap_breakpoint_set` immediately, with no gate, regardless of what the
description says. This was confirmed by auditing the whole codebase (no confirmation
gate, no elicitation usage, no dangerous-action flag anywhere in `src/`).

The sibling ADT server, `aibap.mcp` (Go), already solved this class of problem for
`delete_object` and `update_customizing` via real **MCP elicitation**: a
`ConfirmDestructive(ctx, elicitor, message)` helper that pauses the tool call and asks
the connected client to render a yes/no form, blocking further execution until the human
responds. This design ports that pattern to Python/FastMCP for `sap_breakpoint_set`.

---

## Goals

- A deterministic, code-enforced confirmation step for `sap_breakpoint_set`, backed by
  the MCP elicitation protocol (not just docstring prose).
- The confirmation message must state what is about to happen (exact object/line) and
  why setting a breakpoint is dangerous (modal debugger, no step/continue tooling,
  session-collapse risk per #791). It must also be honest about the underlying **toggle**
  semantics (see Design §2) — it must not claim "set" when the action could equally
  delete an existing breakpoint at that line.
- The tool's result must indicate when a breakpoint was armed *without* a real human
  confirmation (fail-open triggered because the client can't do elicitation), so a human
  reviewing the transcript can tell "confirmed" apart from "confirmation unavailable,
  proceeded anyway."
- DRY: the confirmation mechanism must be a standalone, reusable helper — not
  breakpoint-specific — so future destructive tools (e.g. a future `update_customizing`
  equivalent) can adopt it with one call.
- No regression for clients that don't support MCP elicitation.

## Non-Goals

- Not wiring this into `sap_breakpoint_delete` or `sap_breakpoint_list` now — both are
  already annotated as less dangerous (`destructiveHint=False`). The helper is generic
  enough to add later with a one-line call if that changes.
- Not building a decorator-based auto-wiring mechanism (see Alternatives).
- Not touching the Go `aibap.mcp` codebase — this is a Python-only, sapgui.mcp-only change.

---

## Design

### 1. New shared module: `src/sapguimcp/tools/confirmation_helpers.py`

Mirrors the existing `field_helpers.py` convention in this codebase: a small module of
plain async functions, imported and called explicitly by tool implementations — no
decorators, no registration side effects.

```python
async def confirm_destructive_action(ctx: Context | None, message: str) -> tuple[bool, str, bool]:
    """Ask the client to confirm a destructive action via MCP elicitation.

    Returns (proceed, reason, skipped):
    - proceed: True when the operation should proceed, False when the user
      declined/cancelled.
    - reason: empty when proceed=True and not skipped; otherwise a human-readable
      explanation.
    - skipped: True when no real human confirmation was obtained — ctx is None, the
      client doesn't support elicitation, or any other error occurred while asking.
      Whenever skipped=True, proceed is always True (fail-open); skipped=False means
      the client actually rendered the form and a human answered it.

    Mirrors aibap.mcp's Go ConfirmDestructive helper, extended with the `skipped` flag
    so callers can surface "armed without confirmation" distinctly from "human confirmed."
    """
```

Behavior:

| Condition | Result `(proceed, reason, skipped)` |
|---|---|
| `ctx is None` | `(True, "", True)` — no client context available (e.g. bare unit test) |
| `ctx.elicit(...)` raises any exception | Logged as a warning, then `(True, "", True)` (fail-open) |
| Client accepts, `value=True` | `(True, "", False)` |
| Client accepts, `value=False` | `(False, "user declined via confirmation form", False)` |
| Client declines the form | `(False, "user declined the confirmation", False)` |
| Client cancels the form | `(False, "user cancelled the confirmation", False)` |

Implementation calls `ctx.elicit(message, response_type=bool, response_title="Proceed?")`.
FastMCP auto-generates a single-field `{value: boolean}` schema for a primitive
`response_type` and deconstructs the response back to `bool` — no custom Pydantic model
needed (simpler than the Go side, which has to hand-rolls the JSON schema).

### 2. Wiring into `sap_breakpoint_set`

File: `src/sapguimcp/tools/breakpoint_tools.py`.

- Add `ctx: Context | None = None` parameter to `sap_breakpoint_set`, following the
  existing pattern used in `se16_tools.py`, `feedback_tools.py`, `sap_tools.py`,
  `intent_tools.py`. FastMCP injects this automatically and excludes it from the
  client-visible tool schema.
- Call point: **after** `_navigate_to_editor` and `_resolve_line_number` succeed, and
  **before** the COM toggle (`_toggle_breakpoint_com`). At that point the exact target
  line is known, so the confirmation message can name it. Navigation itself has no
  destructive effect, so doing it before asking is safe.
- New helper `_build_breakpoint_confirm_message(object_type, object_name, method_name,
  resolved_line) -> str` builds the message text. It must describe the action as a
  **toggle**, not an unconditional "set" — `_toggle_breakpoint_com` deletes an existing
  breakpoint at that exact line instead of setting a new one (see the tool's own
  docstring: "SAP toggles breakpoints: if the line already has a breakpoint, VKey 45
  deletes it"). The message doesn't know in advance which of the two will happen (that's
  only discovered after the toggle, via the status-bar text), so it states both outcomes
  honestly rather than pre-checking with an extra COM round trip:

  > "About to toggle the external ABAP breakpoint on PROG Z_TICTACTOE, line 250: if no
  > breakpoint exists there yet, this SETS one; if one already exists at this exact
  > line, SAP briefly clears it and this tool immediately re-arms it — either way the
  > breakpoint ends up ARMED.
  >
  > Setting a breakpoint is dangerous: once it fires, SAP GUI opens a modal debugger
  > that only a human can drive — there is no tool to step, continue, or read
  > variables. Live-verified: firing it can destroy ALL open sessions for this agent at
  > once (issue #791), not just this one. Proceed?"

- On `proceed=False`: return `BreakpointSetResult.failure(error=f"sap_breakpoint_set
  aborted: {reason}", ...)` immediately. The COM toggle is never invoked.
- On `proceed=True`: pass `skipped` through to a new `confirmation_skipped: bool` field
  on `BreakpointSetResult` (default `False`), set to the helper's `skipped` value on the
  success path. This is how the fail-open case (§ Goals) becomes visible to whoever reads
  the result, instead of only appearing in a server-side log line.

### 3. Scope: `sap_breakpoint_set` only

`sap_breakpoint_delete` and `sap_breakpoint_list` are not touched. The helper module is
generic (`confirm_destructive_action` takes any message), so adding a call site there —
or to a future destructive tool elsewhere in the codebase — is a small, additive change.

---

## Alternatives Considered

1. **Decorator-based auto-wiring** (`@requires_confirmation(...)` wrapping the
   `@mcp.tool`-decorated function). Rejected for now: `@mcp.tool` inspects the wrapped
   function's signature to build the JSON schema exposed to clients; stacking another
   decorator underneath risks breaking that introspection unless done very carefully
   with signature-preserving wraps. Not worth the complexity for a single call site
   today. The plain-helper approach doesn't preclude adding a decorator later once
   there's a real multi-tool need.
2. **Generic "aborted result" builder.** Rejected: every tool in this codebase has its
   own typed Result model (`BreakpointSetResult`, `BreakpointDeleteResult`, ...) with its
   own `.failure()` classmethod. A shared abort-result type doesn't fit that pattern; the
   abort branch stays in each tool, only the yes/no decision is shared.

---

## Testing Plan

New test file `unittests/test_confirmation_helpers.py`:

- `ctx=None` → `(True, "", True)`, `ctx.elicit` never called.
- Stub `ctx` with `.elicit` as an `AsyncMock` returning each of: accepted+`True`,
  accepted+`False`, declined, cancelled, and a raised exception — assert the five
  documented `(proceed, reason, skipped)` outcomes, in particular that `skipped=True`
  only for the `ctx=None` and exception cases.

New test file `unittests/test_breakpoint_tools_confirmation.py` (unit-level, mocked
backend — does not require live SAP GUI, unlike the existing integration tests):

- `sap_breakpoint_set` with a mocked backend/navigation/line-resolution and a mocked
  `ctx.elicit` returning decline → asserts `_toggle_breakpoint_com` is never called and
  the result is `success=False` with `"aborted"` in the error message.
- Same setup with `ctx.elicit` returning accept+`True` → asserts the toggle path runs
  as before, and `confirmation_skipped=False` in the result.
- `ctx=None` (or a client with no elicitation handler) → asserts the breakpoint set
  still proceeds (fail-open), but `confirmation_skipped=True` in the result.

Existing integration tests in `unittests/desktop/test_breakpoint_tools_integration.py`
exercise internal helpers (`_navigate_prog`, `_toggle_breakpoint_com`, etc.) directly,
not the registered `sap_breakpoint_set` tool function — they are unaffected by this
change.
