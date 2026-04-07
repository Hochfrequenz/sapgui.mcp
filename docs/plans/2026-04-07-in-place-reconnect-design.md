# In-Place Reconnect on Transient COM Errors — Design Document

**Date:** 2026-04-07
**Status:** Draft — open for review
**Issue:** #642 (deferred from #637)
**Related:** PR #638 (reconcile / reset_to_primary), PR #645 (`sap_session_status` per-id)

## Problem

Issue #637 surfaced a real failure mode: under parallel-agent SAP automation (5 agents creating BPs in their own sessions, save loops), transient COM errors mid-operation make a session unusable. The agent's *only* recovery path today is to spawn a new window via `sap_transaction(..., new_window=True)` — which inflates window count, causes more COM pressure, causes more transient errors, and the cycle compounds.

PR #638 added **visibility & recovery** (`reconcile`, `reset_to_primary`): the agent can detect drift after the fact and clean up. But the cycle still starts on the next operation. This document proposes the actual fix: **retry the failing operation on the same session/window** instead of spawning a replacement.

If this works, the acceptance criterion #1 from #637 ("max N sessions for N agents") is satisfied automatically — you literally can't drift if no extras are ever spawned. Session caps (#641) become belt-and-suspenders rather than load-bearing.

## Goals

- **Same-session recovery**: a transient COM error during a tool call is retried on the same session, transparently to the agent.
- **Bounded retries**: clear failure budget per call and per session, no infinite loops.
- **No silent corruption**: replays must be safe (idempotent or skipped) — the user trusts that retried calls do not double-apply input.
- **Layered visibility**: the agent / LLM can still see *that* a retry happened (via logs and optionally via tool result metadata) so it can adapt strategy if a tool keeps flaking.
- **Minimal blast radius for the rollout**: ship per-tool, starting with the highest-traffic operations, so a bug in the retry layer can't break every desktop call at once.

## Non-Goals

- **WebGUI parity** (this PR is desktop-only). WebGUI has a different reconnect story — Playwright pages have close listeners, browser tabs survive transient network errors differently. Desktop COM is the bleeding wound.
- **Session re-creation**. If the underlying SAP session is genuinely dead (window closed externally, user logged off, SAP-side crash), this design **does not** recreate it. That's session caps + reset_to_primary territory.
- **Full transaction rollback / replay**. We do not snapshot SAP screen state and replay multi-step operations. Each retry is a single COM call.
- **Cross-session retry** (failing over to s2 if s1 dies). That's a separate question about agent affinity.
- **LLM-level retry**. The LLM can still observe failures and react. This design adds a *lower* retry layer, not a replacement.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Retry layer** | Inside `ComThread.run()` only, with a per-call `idempotent: bool` flag the caller passes | Single chokepoint, no cross-cutting refactor of every tool. Caller declares whether the call is safe to replay. |
| **Error taxonomy** | Three classes: `transient` (retry), `session_gone` (don't retry, surface as `SessionGoneError`), `fatal` (don't retry, propagate) | Already exists for the `_RETRYABLE_COM_ERRORS` set in `_com_thread.py:46` — extend it, don't reinvent. |
| **Idempotency model** | Caller-declared, default `False` (no retry) | Safer default. Tool author opts in per call when they know the operation is read-only or naturally idempotent. |
| **Failure budget** | 3 retries per call (existing `max_retries` default), exponential backoff (existing) | Reuse existing infrastructure; no new tunables to tune. |
| **Session-level circuit breaker** | After 5 consecutive transient errors on the same session, open the breaker for 30s — return `SessionGoneError` immediately, let the next reconcile prune | Prevents a single flaky session from spiraling into infinite per-call retries. |
| **State replay strategy** | None — single COM call only | We do NOT replay multi-call operations like `fill_form`. Retry is per-COM-call, not per-tool. Tools that compose multiple COM calls (`fill_form`, `enter_transaction`) still fail at the tool boundary, but each individual COM call inside them retries cleanly. |
| **Visibility** | Existing `com_call_retry` log line is enough; no tool-result metadata change | Less surface area to maintain. Operators can already correlate via logs. |
| **WebGUI behaviour** | Unchanged | Out of scope. |

## Architecture

### The hard question: idempotency

This is the only one that needs product input. The other questions have natural answers; this one has a real tradeoff.

**Option A — Caller declares idempotency per call.** `ComThread.run(fn, idempotent=False)` defaults to no retry. Tool authors opt in:

```python
# Read-only probes, screen inspection — safe to retry
await self.com.run(_get_status_bar, idempotent=True)
await self.com.run(_dump_tree, idempotent=True)
await self.com.run(_find_okcode_field, idempotent=True)

# Mutations — NOT safe to retry blindly
await self.com.run(_set_field_value, idempotent=False)  # default
await self.com.run(_send_v_key, idempotent=False)
```

**Pros:**
- Conservative default. Existing behaviour is preserved exactly when no flag is passed.
- Tool authors who know their operation is safe explicitly opt in. They have the context to judge.
- No new error taxonomy on top of `_RETRYABLE_COM_ERRORS`.
- No replay state to maintain.

**Cons:**
- Manual annotation effort. ~30 call sites across `desktop/__init__.py`. Easy to miss one.
- Not all "mutations" are unsafe to retry — `_send_v_key(VK_F8)` (back) is genuinely idempotent in most contexts. Caller must judge per call.

**Option B — Whitelist of always-safe operations on the COM thread.** `ComThread` keeps a registry of known-idempotent SAP COM properties/methods (`Info.*`, `FindById`, `Children.*`, `Type`, `Text` reads) and auto-retries those. Mutations (`Text =`, `SendVKey`, `Press`, `CloseSession`) never retry.

**Pros:**
- Zero per-call annotation effort.
- The whitelist is small and stable (SAP GUI Scripting API doesn't change much).

**Cons:**
- The whitelist has to be hand-curated and the COM thread has to *parse* the lambda to figure out what it's doing. Brittle (lambdas are opaque). Or the caller has to express the COM call as a path-like structure (`session.com.Info.Transaction`) instead of a lambda — which is a major API churn.
- Read-modify-write patterns inside one lambda (read tree, decide, click button) are unclassifiable.

**Option C — All COM calls retry by default; fix idempotency at the tool layer.** Make `idempotent=True` the default. Tool authors opt OUT for known-unsafe operations.

**Pros:** Maximum coverage, zero annotation cost for the common case.
**Cons:** **Dangerous default.** A `_set_field_value` that retries on a stale-interface error could double-apply input on the next page (if SAP advanced after the apparent failure). The user explicitly does NOT want silent corruption — that's a goals violation.

**Recommendation: Option A (caller-declared, default `False`).** It's the safest default — the existing behaviour is preserved exactly until a tool author opts in. The annotation effort is real but bounded (~30 sites) and we can ship per-tool starting with the safest read-only operations. The "miss a call site" failure mode is **degradation back to current behaviour**, not silent corruption. That asymmetry is decisive.

I want product confirmation on this before any code lands. Specifically: are you OK with a default that prefers correctness over coverage, accepting that we'll incrementally annotate?

### Error taxonomy

Existing in `_com_thread.py:46`:

```python
_RETRYABLE_COM_ERRORS = {
    _RPC_E_SERVERCALL_RETRYLATER,  # 0x80010105 — COM busy
    _RPC_E_CALL_REJECTED,          # 0x80010001 — COM busy
    _RPC_S_UNKNOWN_IF,             # 0x800706B5 — stale interface
}
```

Proposed extension: split this into three sets and apply them based on call shape.

```python
# Always-retryable: COM is just busy. Retry regardless of idempotency.
_TRANSIENT_BUSY_ERRORS = {
    _RPC_E_SERVERCALL_RETRYLATER,
    _RPC_E_CALL_REJECTED,
}

# Retryable iff caller declared idempotent=True. RPC_S_UNKNOWN_IF can mean
# either "stale proxy needs re-resolving" (safe) or "session is dying"
# (NOT safe to retry a mutation against). Treat as "soft dead" — retry only
# when we know the call doesn't change state.
_SOFT_DEAD_ERRORS = {
    _RPC_S_UNKNOWN_IF,
}

# Never retryable: connection is gone. Surface as SessionGoneError so the
# reconcile path can prune.
_HARD_DEAD_ERRORS = {
    _RPC_E_DISCONNECTED,
}
```

This is a refinement of the existing single set, not a redesign. The reconcile path in #638 already uses `max_retries=0` to bypass the retry loop entirely for probes — that mechanism stays.

### Failure budget and circuit breaker

**Per-call budget:** existing `max_retries=3` (default in `ComThread.__init__`). No change.

**Per-session circuit breaker:** new. Track consecutive transient errors per session ID. After 5 in a row on the same session, open the breaker for 30 seconds — every call to that session immediately raises `SessionGoneError` (which the reconcile path will then prune). The breaker auto-resets on the first successful call after the window closes.

This prevents a flaky session from spiraling into 3 retries × N calls × M agents of useless backoff. The 5/30s numbers are starting points — they should be tunable via env var (`SAP_SESSION_CIRCUIT_FAILS=5`, `SAP_SESSION_CIRCUIT_OPEN_S=30`) and observable via the existing `com_throttle_increase` log lines.

The circuit breaker state lives **on `ComThread`**, keyed by session ID, since `ComThread` is the only place that sees every COM call. It does NOT live on the `DesktopSessionRegistry` — the registry is intentionally COM-free per its line-56 contract.

### State replay — explicitly NOT done

The reviewer in #638's plan-review brought this up: "if the failing call had already partially executed on the SAP side (e.g. half a `fill_form`), can we safely retry?". The honest answer is **no**, and this design avoids the question by retrying at the **single COM call** level only.

`fill_form` is a tool that internally makes ~N COM calls (one per field plus a save). Each individual COM call retries cleanly — `_set_field_value` either succeeds or fails atomically. If field 4 fails after fields 1-3 succeeded, the tool surfaces an error as it does today; the retry layer never tries to replay fields 1-3. The agent observes the partial-fill via the existing `FillFormResult.failed_fields` and decides what to do.

This is a deliberate scope limit. The cost is that high-level recovery (re-trying a whole `fill_form`) stays at the LLM/agent layer, where it has the context to judge. The benefit is that the COM thread's retry logic stays small and trustworthy.

## Rollout

Per-tool, in this order:

1. **Pure read operations** (`get_screen_info`, `get_screen_text`, `dump_tree`, `discover_fields`, `discover_buttons`, `get_status_bar`). Mark every COM call inside these as `idempotent=True`. Smallest blast radius — if the retry layer has a bug, the worst case is a misleading status read.
2. **Single-action mutations** (`press_key`, `click_button`, `click_tab`). These are mostly safe to retry too (idempotent SAP actions like F-keys, navigation, focus). Each call site annotated individually.
3. **Multi-call composites** (`enter_transaction`, `fill_form`, `select_dropdown`, `set_field`). The COM calls *inside* them get annotated individually. The tool itself does not change.
4. **Transactional operations** (`sap_login`, `open_new_session`, `close_session`). These are explicitly **not retryable** at the COM-thread layer — they have higher-level retry logic at the BackendManager. Annotate as `idempotent=False`.

Each step is its own PR (plus tests). Step 1 ships first as the proof-of-concept; steps 2–4 follow once we see the metrics on the read path.

## Test strategy

For each step:

- **Unit tests**: `test_com_thread_idempotency.py` — pass a mock callable that raises `_RPC_S_UNKNOWN_IF` on first call, succeeds on second; assert it's retried iff `idempotent=True`. Test the full matrix (`_TRANSIENT_BUSY_ERRORS` always retried, `_SOFT_DEAD_ERRORS` retried only when idempotent, `_HARD_DEAD_ERRORS` never retried).
- **Circuit-breaker tests**: simulate 5 consecutive transient errors on the same session, assert the 6th call raises immediately. Then advance time past the open window and assert it tries again.
- **Per-tool integration tests**: each rollout step adds a regression test that runs the tool against a mock that fails the first COM call and verifies the tool succeeds anyway. Linux-runnable, no real SAP needed.
- **Real SAP smoke test**: the existing `test_com_thread_stress.py::test_multi_session_parallel_stress` should pass with no behavioural change. Worth running on a Windows machine after each step.

No new integration tests against real SAP gates — the existing suite + reviewer-driven Windows validation (per PR #638's pattern) is enough.

## What this PR (the design doc) is NOT

- **Not implementation.** Zero code change. This is a `docs/plans/` document for product alignment.
- **Not a binding API.** The decisions table is my best guess; any of them are negotiable in PR comments. The biggest open question is **idempotency model (Option A vs B vs C)**, then circuit-breaker numbers (5/30s), then rollout order.
- **Not exhaustive.** Items like SAP-screen-state replay, cross-session failover, agent re-binding on session death are flagged as out-of-scope but worth their own designs eventually.

## Open questions for review

1. **Is Option A (caller-declared idempotency, default `False`) the right tradeoff?** The cost is per-call annotation effort (~30 sites). The benefit is conservative-by-default. Alternatives:
   - **Option B**: COM-thread inspects the lambda for known-safe operations. Brittle.
   - **Option C**: Default to retry everywhere; opt-out for known-unsafe. Risk of silent corruption.
2. **Circuit breaker thresholds.** 5 failures / 30s is a starting point. Are those numbers reasonable for your typical agent workload, or should one or both be more aggressive?
3. **Rollout order.** Step 1 = pure reads first. Are there higher-priority tools you'd want me to annotate sooner?
4. **Per-session circuit breaker on the COM thread, not the registry.** I argued for this on the line-56 "registry is COM-free" contract. Sound, or should the breaker live somewhere else?
5. **What does the LLM see?** Today it sees only the existing `com_call_retry` warning in the logs (operator-visible). Should the tool result also surface a `retried_count` field so the LLM can adapt its strategy after seeing repeated retries? Adds API surface area, marginal LLM benefit.
6. **WebGUI scope.** I scoped this to desktop only because COM is the bleeding wound. Is WebGUI's reconnect story actually fine, or should this design extend to it?
