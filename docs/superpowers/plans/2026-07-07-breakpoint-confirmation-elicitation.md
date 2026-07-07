# Breakpoint Confirmation via MCP Elicitation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the docstring-only "ask the human first" instruction on `sap_breakpoint_set` with a real, code-enforced confirmation dialog, built as a reusable helper other destructive tools can adopt later.

**Architecture:** A new standalone async helper, `confirm_destructive_action(ctx, message) -> (bool, str)`, wraps FastMCP's `Context.elicit()` and mirrors aibap.mcp's Go `ConfirmDestructive` pattern: ask the connected client to render a yes/no form, block until it answers, fail open (proceed) if the client can't do elicitation at all. `sap_breakpoint_set` calls this helper — after it has already navigated to the target and resolved the exact line, before it touches COM to toggle the breakpoint — with a message describing what will happen and why it's dangerous.

**Tech Stack:** Python 3.12, FastMCP 3.2 (`Context.elicit`, `fastmcp.server.elicitation` result types), pytest + pytest-anyio, `unittest.mock`.

## Global Constraints

- Repo: `C:\Users\JonatanMeiske\Documents\50_KI_Agenten\sapgui.mcp`, branch `fix/791-breakpoint-session-busy-collapse` (this lands as a follow-up on PR #797).
- Spec: `docs/superpowers/specs/2026-07-07-breakpoint-confirmation-elicitation-design.md` — follow it exactly; this plan implements it task-by-task.
- Fail-open on unsupported/erroring elicitation (approved design decision — do not change to fail-closed).
- No changes to `sap_breakpoint_delete` or `sap_breakpoint_list` in this plan.
- No decorator-based wiring — plain, explicitly-called helper function only (approved design decision).
- Follow existing codebase conventions: shared tool helpers live in `src/sapguimcp/tools/*_helpers.py` (see `field_helpers.py`); tool-level tests use `fastmcp.Client(mcp)` against the real `mcp` server object from `sapguimcp.server`, with `unittest.mock.patch` on `get_backend` and internal module functions (see `unittests/test_general_purpose_tools.py`).
- Run all commands from the repo root: `C:\Users\JonatanMeiske\Documents\50_KI_Agenten\sapgui.mcp`.

---

### Task 1: `confirm_destructive_action` helper module

**Files:**
- Create: `src/sapguimcp/tools/confirmation_helpers.py`
- Test: `unittests/test_confirmation_helpers.py`

**Interfaces:**
- Produces: `async def confirm_destructive_action(ctx: Context | None, message: str) -> tuple[bool, str]` — importable as `from sapguimcp.tools.confirmation_helpers import confirm_destructive_action`. Returns `(True, "")` to proceed, `(False, reason)` to abort. Task 2 imports and calls this directly.

- [ ] **Step 1: Write the failing test**

Create `unittests/test_confirmation_helpers.py`:

```python
"""Unit tests for the shared destructive-action confirmation helper."""

from unittest.mock import AsyncMock

import pytest
from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation

from sapguimcp.tools.confirmation_helpers import confirm_destructive_action


class _FakeContext:
    """Minimal stand-in for fastmcp.Context — only .elicit is exercised."""

    def __init__(self, elicit_result=None, elicit_exception=None):
        if elicit_exception is not None:
            self.elicit = AsyncMock(side_effect=elicit_exception)
        else:
            self.elicit = AsyncMock(return_value=elicit_result)


@pytest.mark.anyio
async def test_ctx_none_proceeds_without_asking():
    proceed, reason = await confirm_destructive_action(None, "Proceed?")
    assert proceed is True
    assert reason == ""


@pytest.mark.anyio
async def test_accept_true_proceeds():
    ctx = _FakeContext(elicit_result=AcceptedElicitation(data=True))
    proceed, reason = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is True
    assert reason == ""
    ctx.elicit.assert_awaited_once()


@pytest.mark.anyio
async def test_accept_false_aborts():
    ctx = _FakeContext(elicit_result=AcceptedElicitation(data=False))
    proceed, reason = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is False
    assert "declined" in reason.lower()


@pytest.mark.anyio
async def test_decline_aborts():
    ctx = _FakeContext(elicit_result=DeclinedElicitation())
    proceed, reason = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is False
    assert "declined" in reason.lower()


@pytest.mark.anyio
async def test_cancel_aborts():
    ctx = _FakeContext(elicit_result=CancelledElicitation())
    proceed, reason = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is False
    assert "cancelled" in reason.lower()


@pytest.mark.anyio
async def test_unsupported_client_fails_open():
    ctx = _FakeContext(elicit_exception=RuntimeError("Elicitation not supported"))
    proceed, reason = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is True
    assert reason == ""
    ctx.elicit.assert_awaited_once()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest unittests/test_confirmation_helpers.py -v`
Expected: `ModuleNotFoundError: No module named 'sapguimcp.tools.confirmation_helpers'` (collection error) — the module doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `src/sapguimcp/tools/confirmation_helpers.py`:

```python
"""Shared helper for gating destructive MCP tools behind a real confirmation dialog.

Mirrors aibap.mcp's Go ConfirmDestructive helper: uses MCP elicitation to pause a
tool call and ask the connected client to render a yes/no form before a destructive
action proceeds. Unlike a docstring instruction telling the calling agent to "ask
the human first", this is enforced in code — the destructive action is only reached
if the client actually returns confirm=True.
"""

from __future__ import annotations

import logging

from fastmcp import Context
from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation

logger = logging.getLogger(__name__)


async def confirm_destructive_action(ctx: Context | None, message: str) -> tuple[bool, str]:
    """Ask the client to confirm a destructive action via MCP elicitation.

    Returns (True, "") when the operation should proceed, or (False, reason) when
    the user declined/cancelled.

    Fails open: if ctx is None, the client doesn't support elicitation, or any
    other error occurs while asking, returns (True, "") so tool behavior is
    unchanged for clients/contexts where a real confirmation dialog isn't possible.
    """
    if ctx is None:
        return True, ""

    try:
        result = await ctx.elicit(message, response_type=bool, response_title="Proceed?")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Elicitation failed or unsupported by client, proceeding without confirmation: %s", exc)
        return True, ""

    if isinstance(result, AcceptedElicitation):
        if result.data:
            return True, ""
        return False, "user declined via confirmation form"
    if isinstance(result, DeclinedElicitation):
        return False, "user declined the confirmation"
    if isinstance(result, CancelledElicitation):
        return False, "user cancelled the confirmation"
    return False, f"unexpected elicitation result: {result!r}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest unittests/test_confirmation_helpers.py -v`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/sapguimcp/tools/confirmation_helpers.py unittests/test_confirmation_helpers.py
git commit -m "feat: add confirm_destructive_action MCP elicitation helper"
```

---

### Task 2: Wire confirmation into `sap_breakpoint_set`

**Files:**
- Modify: `src/sapguimcp/tools/breakpoint_tools.py:11` (import), `:21` (import), `:453-477` (add message-builder helper after `_resolve_line_number`), `:510-529` (function signature + docstring), `:592-602` (insert confirmation call)
- Test: `unittests/test_breakpoint_tools_confirmation.py`

**Interfaces:**
- Consumes: `confirm_destructive_action(ctx: Context | None, message: str) -> tuple[bool, str]` from Task 1 (`sapguimcp.tools.confirmation_helpers`).
- Produces: `sap_breakpoint_set` gains a `ctx: Context | None = None` parameter (FastMCP auto-injects it; it does not appear in the tool's client-visible schema). `_build_breakpoint_confirm_message(object_type, object_name, method_name, line_number) -> str` is a new private module function in `breakpoint_tools.py` (not consumed elsewhere).

- [ ] **Step 1: Write the failing tests**

Create `unittests/test_breakpoint_tools_confirmation.py`:

```python
"""Unit tests for the elicitation-based confirmation gate on sap_breakpoint_set.

Uses a real DesktopBackend instance (with a fake COM thread that just runs the
passed callable inline) so `isinstance(backend, DesktopBackend)` and the
`backend_type` property behave exactly as in production, without touching real
SAP GUI COM objects.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from sapguimcp.backend.desktop import DesktopBackend
from sapguimcp.server import mcp

_PATCH_GET_BACKEND = "sapguimcp.tools.breakpoint_tools.get_backend"
_ARGS = {"object_type": "PROG", "object_name": "Z_TICTACTOE", "line_number": 250}


class _FakeComThread:
    """Runs the callable passed to backend.com.run() inline, synchronously."""

    async def run(self, fn):
        return fn()


def _make_desktop_backend() -> DesktopBackend:
    backend = DesktopBackend(com_thread=_FakeComThread())
    backend.require_session = lambda: object()  # never dereferenced when patches below are in place
    return backend


def _parse_result(raw) -> dict:
    return json.loads(raw.content[0].text)


def _patches(backend):
    """Common patches: real navigation/COM steps replaced with stand-ins so only
    the confirmation gate itself is under test."""
    return (
        patch(_PATCH_GET_BACKEND, new=AsyncMock(return_value=backend)),
        patch("sapguimcp.tools.breakpoint_tools._navigate_to_editor", new=AsyncMock(return_value=None)),
        patch("sapguimcp.tools.breakpoint_tools._resolve_line_number", new=AsyncMock(return_value=(250, None))),
        patch("sapguimcp.tools.breakpoint_tools._resolve_shell_path_com", return_value="usr/cntlEDITOR/shellcont/shell"),
        patch("sapguimcp.tools.breakpoint_tools._toggle_breakpoint_com", return_value=(True, "Breakpoint wurde gesetzt")),
    )


@pytest.mark.anyio
async def test_breakpoint_set_aborts_on_decline():
    backend = _make_desktop_backend()

    async def decline_handler(message, response_type, params, context):
        assert "Z_TICTACTOE" in message
        assert "250" in message
        return ElicitResult(action="decline")

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=decline_handler) as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is False
    assert "aborted" in data["error"].lower()
    mock_toggle.assert_not_called()


@pytest.mark.anyio
async def test_breakpoint_set_aborts_on_confirm_false():
    backend = _make_desktop_backend()

    async def decline_via_false(message, response_type, params, context):
        return False

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=decline_via_false) as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is False
    assert "aborted" in data["error"].lower()
    mock_toggle.assert_not_called()


@pytest.mark.anyio
async def test_breakpoint_set_proceeds_on_accept():
    backend = _make_desktop_backend()

    async def accept_handler(message, response_type, params, context):
        return True

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp, elicitation_handler=accept_handler) as client:
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is True
    assert data["line_number"] == 250
    mock_toggle.assert_called_once()


@pytest.mark.anyio
async def test_breakpoint_set_proceeds_when_client_lacks_elicitation():
    """Fail-open: a client with no elicitation_handler must not block the tool."""
    backend = _make_desktop_backend()

    p_backend, p_nav, p_line, p_shell, p_toggle = _patches(backend)
    with p_backend, p_nav, p_line, p_shell, p_toggle as mock_toggle:
        async with Client(mcp) as client:  # no elicitation_handler configured
            raw = await client.call_tool("sap_breakpoint_set", _ARGS)
    data = _parse_result(raw)
    assert data["success"] is True
    mock_toggle.assert_called_once()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest unittests/test_breakpoint_tools_confirmation.py -v`
Expected: `test_breakpoint_set_aborts_on_decline` and `test_breakpoint_set_aborts_on_confirm_false` FAIL — `assert True is False` (the tool has no confirmation gate yet, so it proceeds to a successful `BreakpointSetResult` regardless of the elicitation answer). `test_breakpoint_set_proceeds_on_accept` and `test_breakpoint_set_proceeds_when_client_lacks_elicitation` already PASS (nothing blocks them yet — this is expected and correct).

- [ ] **Step 3: Add the message-builder helper**

In `src/sapguimcp/tools/breakpoint_tools.py`, insert this function immediately after `_resolve_line_number` (after line 477, before `def register_breakpoint_tools`):

```python
def _build_breakpoint_confirm_message(
    object_type: Literal["PROG", "CLAS", "FUGR"],
    object_name: str,
    method_name: str | None,
    line_number: int,
) -> str:
    """Build the elicitation confirmation message for sap_breakpoint_set."""
    target = f"{object_type} {object_name}"
    if method_name:
        target += f" ({method_name})"
    return (
        f"About to set an external ABAP breakpoint on {target}, line {line_number}.\n\n"
        "This is dangerous: once the breakpoint fires, SAP GUI opens a modal ABAP "
        "debugger that only a human can drive — there is no tool to step, continue, "
        "or read variables. Live-verified (issue #791): firing it can destroy ALL "
        "open sessions for this agent at once, not just this one, with no known "
        "in-band recovery.\n\n"
        "Proceed only if you intend to sit at the SAP GUI yourself and step through "
        "the debugger when it fires."
    )
```

- [ ] **Step 4: Add the `ctx` parameter and confirmation call to `sap_breakpoint_set`**

In `src/sapguimcp/tools/breakpoint_tools.py`, line 11, change:

```python
from fastmcp import FastMCP
```

to:

```python
from fastmcp import Context, FastMCP
```

After line 21 (`from sapguimcp.tools.field_helpers import fill_field_with_keyboard`), add:

```python
from sapguimcp.tools.confirmation_helpers import confirm_destructive_action
```

In the `sap_breakpoint_set` signature (currently lines 510-518), add `ctx` as the last parameter:

```python
    async def sap_breakpoint_set(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-return-statements,too-many-branches
        object_type: Literal["PROG", "CLAS", "FUGR"],
        object_name: str,
        line_number: Annotated[int, PydanticField(gt=0)] | None = None,
        match_pattern: str | None = None,
        method_name: str | None = None,
        session: str | None = None,
        agent_id: str | None = None,
        ctx: Context | None = None,
    ) -> BreakpointSetResult:
```

In its docstring `Args:` block, add a line after `agent_id`:

```python
            agent_id: Agent identifier for binding check. Optional.
            ctx: MCP request context, auto-injected by FastMCP. Used to ask the
                connected client for explicit confirmation before arming the
                breakpoint. Not part of the tool's client-visible parameters.
```

Then, right after `assert resolved_line is not None` and before `session_com = backend.require_session()` (between current lines 600 and 602), insert:

```python
            confirm_message = _build_breakpoint_confirm_message(object_type, object_name, method_name, resolved_line)
            proceed, reason = await confirm_destructive_action(ctx, confirm_message)
            if not proceed:
                return BreakpointSetResult.failure(
                    error=f"sap_breakpoint_set aborted: {reason}",
                    object_type=object_type,
                    object_name=object_name,
                    method_name=method_name,
                    line_number=resolved_line,
                )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest unittests/test_breakpoint_tools_confirmation.py -v`
Expected: `4 passed`

- [ ] **Step 6: Run the directly affected test files to check for regressions**

Run: `pytest unittests/test_breakpoint_models.py unittests/test_confirmation_helpers.py unittests/test_breakpoint_tools_confirmation.py -v`
Expected: all pass — `test_breakpoint_models.py` confirms the `BreakpointSetResult` model itself is untouched, the other two confirm the new helper and its wiring. (Do not run the full `unittests/` suite here — it's slow and out of scope for this change; the existing `unittests/desktop/test_breakpoint_tools_integration.py` tests are `integration`-marked, `skip_no_sap`-gated, exercise internal helpers directly rather than `sap_breakpoint_set` itself, and are unaffected by this change.)

- [ ] **Step 7: Commit**

```bash
git add src/sapguimcp/tools/breakpoint_tools.py unittests/test_breakpoint_tools_confirmation.py
git commit -m "feat: gate sap_breakpoint_set behind an MCP elicitation confirmation dialog"
```

---

## Self-Review Notes

- **Spec coverage:** Goals section (deterministic gate, danger-explaining message, DRY reusable helper, no regression for non-elicitation clients) → Task 1 (helper) + Task 2 (wiring, message, fail-open test). Non-goals (no `_delete`/`_list` wiring, no decorator) → explicitly not touched; decorator alternative documented as rejected in the spec, not reintroduced here. Testing Plan section → Tasks 1 and 2 steps 1 implement exactly the listed test cases (with two extra confirm-value variants added for belt-and-suspenders coverage of `AcceptedElicitation(data=False)` vs `DeclinedElicitation`).
- **Placeholder scan:** No TBD/TODO; all code blocks are complete and were validated by running them against the actual current codebase (see below).
- **Type consistency:** `confirm_destructive_action(ctx: Context | None, message: str) -> tuple[bool, str]` is identical between Task 1's implementation and Task 2's call site. `_build_breakpoint_confirm_message` signature matches its single call site.
- **Validated against real code, not just reasoned about:** every test file and code change in this plan was dry-run against the actual current `sapgui.mcp` checkout (editable-installed locally) before being written down — including confirming the exact pre-fix failure mode (`test_breakpoint_set_aborts_on_decline`/`_on_confirm_false` fail with a clean `assert True is False`, not an unrelated crash) and the exact post-fix passing behavior.
