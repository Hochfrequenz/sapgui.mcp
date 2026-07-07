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
    proceed, reason, skipped = await confirm_destructive_action(None, "Proceed?")
    assert proceed is True
    assert reason == ""
    assert skipped is True


@pytest.mark.anyio
async def test_accept_true_proceeds():
    ctx = _FakeContext(elicit_result=AcceptedElicitation(data=True))
    proceed, reason, skipped = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is True
    assert reason == ""
    assert skipped is False
    ctx.elicit.assert_awaited_once()


@pytest.mark.anyio
async def test_accept_false_aborts():
    ctx = _FakeContext(elicit_result=AcceptedElicitation(data=False))
    proceed, reason, skipped = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is False
    assert "declined" in reason.lower()
    assert skipped is False


@pytest.mark.anyio
async def test_decline_aborts():
    ctx = _FakeContext(elicit_result=DeclinedElicitation())
    proceed, reason, skipped = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is False
    assert "declined" in reason.lower()
    assert skipped is False


@pytest.mark.anyio
async def test_cancel_aborts():
    ctx = _FakeContext(elicit_result=CancelledElicitation())
    proceed, reason, skipped = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is False
    assert "cancelled" in reason.lower()
    assert skipped is False


@pytest.mark.anyio
async def test_unsupported_client_fails_open():
    ctx = _FakeContext(elicit_exception=RuntimeError("Elicitation not supported"))
    proceed, reason, skipped = await confirm_destructive_action(ctx, "Proceed?")
    assert proceed is True
    assert reason == ""
    assert skipped is True
    ctx.elicit.assert_awaited_once()
