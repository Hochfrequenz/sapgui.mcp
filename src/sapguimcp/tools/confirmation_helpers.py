"""Shared helper for gating destructive MCP tools behind a real confirmation dialog.

Mirrors aibap.mcp's Go ConfirmDestructive helper: uses MCP elicitation to pause a
tool call and ask the connected client to render a yes/no form before a destructive
action proceeds. Unlike a docstring instruction telling the calling agent to "ask
the human first", this is enforced in code — the destructive action is only reached
if the client actually returns confirm=True.

How the question is asked depends on the negotiated MCP protocol version:

- Handshake-era connections (up to 2025-11-25): ``ctx.elicit()`` sends a
  server-initiated ``elicitation/create`` request and waits for the answer.
- 2026-07-28 connections have no server-to-client back-channel (SEP-2322), so
  ``ctx.elicit()`` raises there. Instead the tool returns an ``InputRequiredResult``
  carrying the elicitation; the client asks the human and re-calls the tool with
  the answer in ``ctx.input_responses``.
"""

from __future__ import annotations

import logging

from fastmcp import Context
from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from mcp.types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult
from mcp.types.version import MODERN_PROTOCOL_VERSIONS

logger = logging.getLogger(__name__)

_CONFIRM_REQUEST_KEY = "confirm_destructive_action"
_CONFIRM_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "boolean", "title": "Proceed?"}},
    "required": ["value"],
}


def _is_modern_connection(ctx: Context) -> bool:
    """True on a 2026-07-28 connection, where ctx.elicit() is unavailable."""
    request_context = getattr(ctx, "request_context", None)
    return request_context is not None and request_context.protocol_version in MODERN_PROTOCOL_VERSIONS


async def confirm_destructive_action(  # pylint: disable=too-many-return-statements
    ctx: Context | None, message: str
) -> tuple[bool, str, bool] | InputRequiredResult:
    """Ask the client to confirm a destructive action via MCP elicitation.

    On a 2026-07-28 connection the first call returns an ``InputRequiredResult``
    that the calling tool must return as-is; the client then re-calls the tool and
    this function reads the answer. The question is sealed into ``request_state``,
    so an answer only counts for the exact message it was given for.

    Returns (proceed, reason, skipped):
    - proceed: True when the operation should proceed, False when the user
      declined/cancelled.
    - reason: empty when proceed=True and not skipped; otherwise a human-readable
      explanation.
    - skipped: True when no real human confirmation was obtained — ctx is None, the
      client doesn't support elicitation, or any other error occurred while asking.
      Whenever skipped=True, proceed is always True (fail-open).

    Fails open: skipped cases return (True, "", True) so tool behavior is unchanged
    for clients/contexts where a real confirmation dialog isn't possible. Callers
    should surface `skipped` in their result so "human confirmed" and "confirmation
    unavailable, proceeded anyway" are distinguishable.
    """
    if ctx is None:
        return True, "", True

    if _is_modern_connection(ctx):
        return _confirm_via_input_required(ctx, message)

    try:
        result = await ctx.elicit(message, response_type=bool, response_title="Proceed?")
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("Elicitation failed or unsupported by client, proceeding without confirmation: %s", exc)
        return True, "", True

    if isinstance(result, AcceptedElicitation):
        if result.data:
            return True, "", False
        return False, "user declined via confirmation form", False
    if isinstance(result, DeclinedElicitation):
        return False, "user declined the confirmation", False
    if isinstance(result, CancelledElicitation):
        return False, "user cancelled the confirmation", False
    return False, f"unexpected elicitation result: {result!r}", False


def _confirm_via_input_required(ctx: Context, message: str) -> tuple[bool, str, bool] | InputRequiredResult:
    """2026-07-28 variant: ask via InputRequiredResult, then read the client's answer."""
    capabilities = ctx.request_context.session.client_capabilities if ctx.request_context else None
    if capabilities is None or capabilities.elicitation is None:
        logger.warning("Client does not support elicitation, proceeding without confirmation")
        return True, "", True
    answer = (ctx.input_responses or {}).get(_CONFIRM_REQUEST_KEY)
    if answer is None or ctx.request_state != message:
        # First round, or the question changed since the answer was given: (re-)ask.
        return InputRequiredResult(
            input_requests={
                _CONFIRM_REQUEST_KEY: ElicitRequest(
                    params=ElicitRequestFormParams(message=message, requested_schema=_CONFIRM_SCHEMA)
                )
            },
            request_state=message,
        )
    if not isinstance(answer, ElicitResult):
        return False, f"unexpected elicitation result: {answer!r}", False
    if answer.action == "accept":
        if (answer.content or {}).get("value") is True:
            return True, "", False
        return False, "user declined via confirmation form", False
    if answer.action == "decline":
        return False, "user declined the confirmation", False
    return False, "user cancelled the confirmation", False
