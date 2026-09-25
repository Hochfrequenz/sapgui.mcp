"""Unit tests for the shared destructive-action confirmation helper."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from mcp.types import ClientCapabilities, ElicitationCapability, ElicitResult, InputRequiredResult

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


# --- 2026-07-28 connections: confirmation via InputRequiredResult (SEP-2322) ---


class _FakeModernContext:
    """Stand-in for a fastmcp.Context on a 2026-07-28 connection."""

    def __init__(self, input_responses=None, request_state=None, elicitation=True):
        caps = ClientCapabilities(elicitation=ElicitationCapability() if elicitation else None)
        self.request_context = SimpleNamespace(
            protocol_version="2026-07-28", session=SimpleNamespace(client_capabilities=caps)
        )
        self.input_responses = input_responses
        self.request_state = request_state
        self.elicit = AsyncMock(side_effect=AssertionError("ctx.elicit() is unavailable on 2026-07-28"))


@pytest.mark.anyio
async def test_modern_first_round_asks_via_input_required():
    result = await confirm_destructive_action(_FakeModernContext(), "Set breakpoint?")
    assert isinstance(result, InputRequiredResult)
    assert result.request_state == "Set breakpoint?"
    request = result.input_requests["confirm_destructive_action"]
    assert request.params.message == "Set breakpoint?"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (ElicitResult(action="accept", content={"value": True}), (True, "", False)),
        (
            ElicitResult(action="accept", content={"value": False}),
            (False, "user declined via confirmation form", False),
        ),
        (ElicitResult(action="decline"), (False, "user declined the confirmation", False)),
        (ElicitResult(action="cancel"), (False, "user cancelled the confirmation", False)),
    ],
)
async def test_modern_second_round_reads_answer(answer, expected):
    ctx = _FakeModernContext(input_responses={"confirm_destructive_action": answer}, request_state="Set breakpoint?")
    assert await confirm_destructive_action(ctx, "Set breakpoint?") == expected


@pytest.mark.anyio
async def test_modern_answer_for_a_different_question_is_not_honored():
    """A yes given for another question (e.g. a different line) must trigger a fresh ask."""
    ctx = _FakeModernContext(
        input_responses={"confirm_destructive_action": ElicitResult(action="accept", content={"value": True})},
        request_state="Set breakpoint at line 10?",
    )
    result = await confirm_destructive_action(ctx, "Set breakpoint at line 250?")
    assert isinstance(result, InputRequiredResult)
    assert result.request_state == "Set breakpoint at line 250?"


@pytest.mark.anyio
async def test_modern_client_without_elicitation_fails_open():
    result = await confirm_destructive_action(_FakeModernContext(elicitation=False), "Proceed?")
    assert result == (True, "", True)


@pytest.mark.anyio
async def test_modern_answer_without_request_state_is_not_honored():
    ctx = _FakeModernContext(
        input_responses={"confirm_destructive_action": ElicitResult(action="accept", content={"value": True})},
        request_state=None,
    )
    assert isinstance(await confirm_destructive_action(ctx, "Proceed?"), InputRequiredResult)
