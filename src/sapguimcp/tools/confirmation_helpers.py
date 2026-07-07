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


async def confirm_destructive_action(  # pylint: disable=too-many-return-statements
    ctx: Context | None, message: str
) -> tuple[bool, str, bool]:
    """Ask the client to confirm a destructive action via MCP elicitation.

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

    try:
        # mypy (strict) misresolves this to the `response_type: None` overload
        # regardless of the actual type passed (reproduces even for `str`) —
        # a mypy/fastmcp overload-matching quirk on fastmcp>=3.4, not a real
        # type error; the runtime behavior (and the isinstance checks below)
        # is correct.
        result = await ctx.elicit(message, response_type=bool, response_title="Proceed?")  # type: ignore[arg-type]
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
