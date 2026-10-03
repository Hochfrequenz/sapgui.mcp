# Issue #879 design: COM retry must not re-run completed steps of a multi-step callable

## Problem

`ComThread._execute_with_retry` retries the *entire* callable `fn()` on
RETRYLATER / CALL_REJECTED / RPC_S_UNKNOWN_IF. If `fn` is a multi-step batch
(e.g. `sap_com_evaluate`'s `_run_all`, or `DesktopBackend.login`'s sapsucker
login lambda), a transient error mid-batch re-runs every already-completed
step. For a batch that contains a Save (SendVKey 11), the Save fires twice.

## Approach: progress-aware re-invocation (opt-in per callable)

Retrying only the *failing COM call* is impossible from the ComThread — it
sees one opaque `fn()`. So the fix moves the retry boundary into the callable
and makes the whole-callable retry safe:

1. **`sap_com_evaluate._run_all`**: make the batch resume-capable. The
   callable keeps a mutable `cursor` (index of the first op not yet durably
   attempted). On a retryable COM error the op's own try/except in
   `_execute_single_op` already catches per-op exceptions — the ONLY errors
   that escape to `_execute_with_retry` are COM transport errors raised
   *inside* a COM call. So: catch retryable COM errors per-op inside
   `_run_all`, remember the resume point, and re-raise a dedicated
   `BatchRetry` exception carrying (results-so-far, resume-index). The
   ComThread, seeing `BatchRetry`, retries `fn` which fast-forwards past
   completed ops.
2. **`ComThread._execute_with_retry`**: recognise a `ComBatchRetry` carrier
   exception; on retry, pass the carrier back into the new `fn` invocation
   so it can resume instead of restarting. The callable API: `fn(resume)` —
   callables that don't care ignore the argument.
3. **`DesktopBackend.login`**: the login lambda opens a NEW parallel
   connection; a retry after partial failure can open a second connection.
   Wrap login in the same mechanism: on retryable error mid-login, resume
   from the last completed phase. Given login's phases are opaque (inside
   sapsucker), the pragmatic fix: pass `max_retries=0` for the login call —
   a partially-opened connection is recoverable by the user retrying login
   (the reconcile pass prunes ghost connections), whereas a double connection
   is silently wrong.

## Consequences

- Batches: no double-execution of completed ops; the destructive
  Save-twice scenario is closed.
- Login: no silent double connection; failures surface immediately, and
  ghost-connection reconcile on the next login cleans up.

## Tests

- Unit (fake COM errors, no SAP): batch with a retryable error on op 3 of 5
  → ops 1-2 executed exactly once; ops 4-5 run after retry; final result
  complete.
- Unit: `login` path passes `max_retries=0`.
- Existing com_thread tests keep passing (default path unchanged).
