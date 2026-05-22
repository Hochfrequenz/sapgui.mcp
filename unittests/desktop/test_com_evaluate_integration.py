"""Integration tests for sap_com_evaluate on desktop backend."""

import json
import sys

import pytest

from sapguimcp.backend.desktop.models.com_results import ComEvaluateResult, ComOperation
from sapguimcp.tools.com_tools import ComOperationInput, _execute_single_op
from unittests.desktop.conftest import go_home, skip_no_sap

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


@skip_no_sap
@pytest.mark.anyio
async def test_com_get_window_title(backend):
    """get action reads the main window title."""
    session = backend.require_session()

    def _run():
        op = ComOperationInput(element_id="wnd[0]", action="get", property_or_method="Text")
        return _execute_single_op(session, op)

    result = await backend.com.run(_run)
    assert result.success, f"Failed: {result.error}"
    assert result.result is not None
    title = json.loads(result.result)
    assert isinstance(title, str)
    assert len(title) > 0, "Window should have a title"


@skip_no_sap
@pytest.mark.anyio
async def test_com_get_status_bar_text(backend):
    """get action reads status bar text."""
    session = backend.require_session()

    def _run():
        op = ComOperationInput(element_id="wnd[0]/sbar", action="get", property_or_method="Text")
        return _execute_single_op(session, op)

    result = await backend.com.run(_run)
    assert result.success, f"Failed: {result.error}"
    # Status bar text may be empty, but the property should be readable
    assert result.result is not None


@skip_no_sap
@pytest.mark.anyio
async def test_com_set_okcode_field(backend):
    """set action writes to the OkCode field."""
    session = backend.require_session()

    def _run():
        op = ComOperationInput(
            element_id="wnd[0]/tbar[0]/okcd",
            action="set",
            property_or_method="Text",
            args=["SE16"],
        )
        return _execute_single_op(session, op)

    result = await backend.com.run(_run)
    assert result.success, f"Failed: {result.error}"
    assert json.loads(result.result) == "SE16"

    # Clear it back
    def _clear():
        op = ComOperationInput(
            element_id="wnd[0]/tbar[0]/okcd",
            action="set",
            property_or_method="Text",
            args=[""],
        )
        return _execute_single_op(session, op)

    await backend.com.run(_clear)


@skip_no_sap
@pytest.mark.anyio
async def test_com_call_sendvkey(backend):
    """call action invokes SendVKey (Enter) on the window."""
    # Navigate to SE16 first so Enter has a predictable effect
    await backend.enter_transaction("SE16N")
    await backend.wait_for_ready()

    session = backend.require_session()

    def _run():
        op = ComOperationInput(
            element_id="wnd[0]",
            action="call",
            property_or_method="SendVKey",
            args=[0],  # Enter
        )
        return _execute_single_op(session, op)

    result = await backend.com.run(_run)
    assert result.success, f"Failed: {result.error}"
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_com_element_not_found(backend):
    """get on nonexistent element returns failure."""
    session = backend.require_session()

    def _run():
        op = ComOperationInput(
            element_id="wnd[0]/usr/ZZZNONEXISTENT",
            action="get",
            property_or_method="Text",
        )
        return _execute_single_op(session, op)

    result = await backend.com.run(_run)
    assert not result.success
    assert result.error is not None
    assert "not found" in result.error.lower() or "element" in result.error.lower()


@skip_no_sap
@pytest.mark.anyio
async def test_com_batch_operations(backend):
    """Multiple operations execute sequentially in one COM thread call."""
    await backend.enter_transaction("SE93")
    await backend.wait_for_ready()

    session = backend.require_session()

    def _run():
        ops = [
            ComOperationInput(element_id="wnd[0]", action="get", property_or_method="Text"),
            ComOperationInput(element_id="wnd[0]/sbar", action="get", property_or_method="Text"),
        ]
        results = []
        for op in ops:
            results.append(_execute_single_op(session, op))
        return results

    results = await backend.com.run(_run)
    assert len(results) == 2
    assert results[0].success
    assert results[1].success
    # First result should be SE93 window title
    title = json.loads(results[0].result)
    assert isinstance(title, str)
    await go_home(backend)


@skip_no_sap
@pytest.mark.anyio
async def test_com_model_roundtrip(backend):
    """ComEvaluateResult must JSON-serialize (roundtrip)."""
    session = backend.require_session()

    def _run():
        op = ComOperationInput(element_id="wnd[0]", action="get", property_or_method="Text")
        return _execute_single_op(session, op)

    op_result = await backend.com.run(_run)
    eval_result = ComEvaluateResult(operations=[op_result])

    json_str = eval_result.model_dump_json()
    parsed = json.loads(json_str)
    assert "operations" in parsed
    assert len(parsed["operations"]) == 1

    restored = ComEvaluateResult.model_validate_json(json_str)
    assert len(restored.operations) == 1
    assert restored.operations[0].element_id == "wnd[0]"


@skip_no_sap
@pytest.mark.anyio
async def test_com_snapshot_returns_element_tree(backend):
    """sap_com_snapshot returns an element tree with IDs the LLM can use."""
    snapshot = await backend.get_snapshot()
    text = str(snapshot)
    # Should contain SAP GUI element types
    assert "Gui" in text, "Snapshot should contain GuiXxx element types"
    # Should contain common elements like status bar, toolbar, okcode field
    assert "sbar" in text or "okcd" in text, "Snapshot should contain sbar or okcd"
    # Should have multiple lines (it's a tree)
    assert text.count("\n") > 5, "Snapshot should be a multi-line tree"


@skip_no_sap
@pytest.mark.anyio
async def test_com_snapshot_element_ids_usable(backend):
    """Element IDs from snapshot can be used in sap_com_evaluate."""
    # Get snapshot
    snapshot = str(await backend.get_snapshot())
    # The snapshot should contain wnd[0]/sbar (status bar)
    assert "sbar" in snapshot

    # Use the ID to read the status bar text
    session = backend.require_session()

    def _run():
        op = ComOperationInput(element_id="wnd[0]/sbar", action="get", property_or_method="Text")
        return _execute_single_op(session, op)

    result = await backend.com.run(_run)
    assert result.success, f"Failed to read status bar: {result.error}"
