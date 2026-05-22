"""
Integration tests for SE09 (Transport Organizer) lookup tool.

These tests run against a real SAP system to verify the sap_se09_lookup tool.
"""

import pytest
from mcp import ClientSession

from sapguimcp.models import LoginResult, ShortcutsResult
from sapguimcp.models.se09_models import TransportListResult

from .conftest import call_tool_typed
from .integration_helpers import capture_html_snapshot


@pytest.mark.anyio
async def test_se09_lookup_default(sap_mcp_client: ClientSession) -> None:
    """Test sap_se09_lookup with default parameters (current user, modifiable)."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count >= 0
    assert len(result.requests) == result.request_count

    # Verify structure
    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        assert req.owner != ""


@pytest.mark.anyio
async def test_se09_lookup_workbench_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by workbench request type."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"request_type": "workbench", "status": "modifiable"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    # When filtering by workbench, returned requests should be Workbench type
    # (but the parser may not always detect the type if the section header is missing)
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench", f"Expected Workbench, got {req.request_type}"


@pytest.mark.anyio
async def test_se09_lookup_all_status(sap_mcp_client: ClientSession) -> None:
    """Test with both modifiable and released."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"request_type": "all", "status": "all"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count >= 0


@pytest.mark.anyio
async def test_se09_lookup_no_results(sap_mcp_client: ClientSession) -> None:
    """Test with a user that has no transports."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "ZZZNOUSER99", "request_type": "all", "status": "all"},
        TransportListResult,
    )

    # Should succeed with 0 results (or gracefully handle if checkboxes are disabled)
    if result.success:
        assert result.request_count == 0
    else:
        # May fail if the user field is not accepted or checkboxes disabled
        assert "error" in result.error.lower() or "timeout" in result.error.lower()


@pytest.mark.anyio
async def test_se09_lookup_include_objects(sap_mcp_client: ClientSession) -> None:
    """Test sap_se09_lookup with include_objects=True to get tasks."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "include_objects": True},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0

    # At least one request should have tasks (KLEINK has modifiable transports with tasks)
    requests_with_tasks = [r for r in result.requests if r.tasks]
    assert len(requests_with_tasks) > 0, "Expected at least one request with tasks"

    # Verify task structure
    for req in result.requests:
        for task in req.tasks:
            assert len(task.task_number) == 10
            assert task.task_number[3] == "K"
            # Task number should be different from request number
            assert task.task_number != req.request_number


@pytest.mark.anyio
async def test_se09_lookup_customizing_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by customizing request type with wildcard user."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    # Use username="*" to search across all users (KLEINK has no customizing transports)
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "customizing", "status": "all"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0, "Expected customizing transports with wildcard user"

    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        assert req.owner != ""
        if req.request_type:
            assert req.request_type == "Customizing", f"Expected Customizing, got {req.request_type}"


@pytest.mark.anyio
async def test_se09_lookup_released_only(sap_mcp_client: ClientSession) -> None:
    """Test filtering by released status with explicit request_type."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "released"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0, "Expected released transports with wildcard user"
    for req in result.requests:
        if req.status:
            assert req.status == "Released", f"Expected Released, got {req.status}"


@pytest.mark.anyio
async def test_se09_lookup_workbench_include_objects(sap_mcp_client: ClientSession) -> None:
    """Test workbench-only filter combined with include_objects."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "request_type": "workbench", "include_objects": True},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0

    # All requests should be workbench type
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench"

    # At least one request should have tasks
    requests_with_tasks = [r for r in result.requests if r.tasks]
    assert len(requests_with_tasks) > 0


@pytest.mark.anyio
async def test_se09_lookup_all_types_all_status(sap_mcp_client: ClientSession) -> None:
    """Test retrieving all request types and all statuses."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "request_type": "all", "status": "all"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    # KLEINK should have at least the modifiable workbench transports
    assert result.request_count >= 5

    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        assert req.owner != ""


@pytest.mark.anyio
async def test_se09_lookup_all_types_wildcard_returns_valid_results(sap_mcp_client: ClientSession) -> None:
    """Test that all-types lookup with wildcard user returns valid results.

    Note: The parser may only capture visible rows, so we can't guarantee
    both Workbench and Customizing appear on the first page. We just assert
    the lookup succeeds and returns structurally valid results.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "all"},
        TransportListResult,
    )

    assert result.success, f"SE09 lookup failed: {result.error}"
    assert result.request_count > 0, "Expected results with all types and statuses"

    # Verify parsed data is structurally valid
    for req in result.requests:
        assert len(req.request_number) == 10
        assert req.request_number[3] == "K"
        assert req.owner != ""


@pytest.mark.anyio
async def test_se09_customizing_then_workbench(sap_mcp_client: ClientSession) -> None:
    """After customizing-only lookup, workbench-only must still return results.

    Checkbox config: customizing = Workbench=off, Customizing=on
                     workbench   = Workbench=on,  Customizing=off
    The tool must explicitly re-check Workbench after it was unchecked.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Customizing-only with wildcard user
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "customizing", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"customizing lookup failed: {result.error}"
    assert result.request_count > 0, "customizing: expected results with wildcard user"
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Customizing", f"customizing: got {req.request_type}"

    # Workbench-only — the critical transition
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "workbench", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"workbench lookup failed: {result.error}"
    assert result.request_count > 0, (
        "workbench: expected results — " "Workbench checkbox was likely not re-checked after customizing step"
    )
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench", f"workbench: got {req.request_type}"


@pytest.mark.anyio
async def test_se09_workbench_then_customizing(sap_mcp_client: ClientSession) -> None:
    """After workbench-only lookup, customizing-only must still return results.

    Checkbox config: workbench   = Workbench=on,  Customizing=off
                     customizing = Workbench=off, Customizing=on
    The tool must explicitly re-check Customizing after it was unchecked.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Workbench-only
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "workbench", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"workbench lookup failed: {result.error}"
    assert result.request_count > 0, "workbench: expected results"
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench", f"workbench: got {req.request_type}"

    # Customizing-only — the critical transition
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "customizing", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"customizing lookup failed: {result.error}"
    assert result.request_count > 0, (
        "customizing: expected results — " "Customizing checkbox was likely not re-checked after workbench step"
    )
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Customizing", f"customizing: got {req.request_type}"


@pytest.mark.anyio
async def test_se09_all_then_workbench_only(sap_mcp_client: ClientSession) -> None:
    """After all-types lookup, workbench-only must only return workbench.

    Checkbox config: all       = Workbench=on,  Customizing=on
                     workbench = Workbench=on,  Customizing=off
    The tool must explicitly uncheck Customizing.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # All types
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"all-types lookup failed: {result.error}"
    assert result.request_count > 0, "all-types: expected results"

    # Workbench-only — must uncheck Customizing from previous step
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "workbench", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"workbench lookup failed: {result.error}"
    assert result.request_count > 0, "workbench: expected results"
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Workbench", (
                f"workbench: got {req.request_type} — "
                "Customizing checkbox was likely not unchecked after all-types step"
            )


@pytest.mark.anyio
async def test_se09_all_then_customizing_only(sap_mcp_client: ClientSession) -> None:
    """After all-types lookup, customizing-only must only return customizing.

    Checkbox config: all         = Workbench=on,  Customizing=on
                     customizing = Workbench=off, Customizing=on
    The tool must explicitly uncheck Workbench.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # All types
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"all-types lookup failed: {result.error}"
    assert result.request_count > 0, "all-types: expected results"

    # Customizing-only — must uncheck Workbench from previous step
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "customizing", "status": "all"},
        TransportListResult,
    )
    assert result.success, f"customizing lookup failed: {result.error}"
    assert result.request_count > 0, "customizing: expected results"
    for req in result.requests:
        if req.request_type:
            assert req.request_type == "Customizing", (
                f"customizing: got {req.request_type} — "
                "Workbench checkbox was likely not unchecked after all-types step"
            )


@pytest.mark.anyio
async def test_se09_released_then_modifiable(sap_mcp_client: ClientSession) -> None:
    """After released-only lookup, modifiable-only must still return results.

    Checkbox config: released   = Modifiable=off, Released=on
                     modifiable = Modifiable=on,  Released=off
    The tool must explicitly re-check Modifiable after it was unchecked.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Released-only with wildcard user
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "released"},
        TransportListResult,
    )
    assert result.success, f"released lookup failed: {result.error}"
    assert result.request_count > 0, "released: expected results with wildcard user"
    for req in result.requests:
        if req.status:
            assert req.status == "Released", f"released: got {req.status}"

    # Modifiable-only — the critical transition
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "modifiable"},
        TransportListResult,
    )
    assert result.success, f"modifiable lookup failed: {result.error}"
    assert result.request_count > 0, (
        "modifiable: expected results — " "Modifiable checkbox was likely not re-checked after released step"
    )
    for req in result.requests:
        if req.status:
            assert req.status == "Modifiable", f"modifiable: got {req.status}"


@pytest.mark.anyio
async def test_se09_modifiable_then_released(sap_mcp_client: ClientSession) -> None:
    """After modifiable-only lookup, released-only must still return results.

    Checkbox config: modifiable = Modifiable=on,  Released=off
                     released   = Modifiable=off, Released=on
    The tool must explicitly re-check Released after it was unchecked.
    """
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Modifiable-only
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "modifiable"},
        TransportListResult,
    )
    assert result.success, f"modifiable lookup failed: {result.error}"
    assert result.request_count > 0, "modifiable: expected results"
    for req in result.requests:
        if req.status:
            assert req.status == "Modifiable", f"modifiable: got {req.status}"

    # Released-only — the critical transition
    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "all", "status": "released"},
        TransportListResult,
    )
    assert result.success, f"released lookup failed: {result.error}"
    assert result.request_count > 0, (
        "released: expected results — " "Released checkbox was likely not re-checked after modifiable step"
    )
    for req in result.requests:
        if req.status:
            assert req.status == "Released", f"released: got {req.status}"


@pytest.mark.anyio
async def test_se09_user_filter(sap_mcp_client: ClientSession) -> None:
    """Verify the user filter works for both specific user and wildcard."""
    login = await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    assert login.success, f"Login failed: {login.error}"

    # Specific user — KLEINK has modifiable workbench transports.
    # Note: SE09 user filter shows requests where the user has a task,
    # so the request owner may be someone else.
    result_kleink = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "KLEINK", "request_type": "workbench", "status": "modifiable"},
        TransportListResult,
    )
    assert result_kleink.success, f"KLEINK lookup failed: {result_kleink.error}"
    assert result_kleink.request_count > 0, "KLEINK: expected modifiable workbench transports"

    # Wildcard user — should return at least as many results as specific user
    result_all = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "workbench", "status": "modifiable"},
        TransportListResult,
    )
    assert result_all.success, f"wildcard lookup failed: {result_all.error}"
    assert result_all.request_count > 0, "wildcard: expected results"
    assert result_all.request_count >= result_kleink.request_count, (
        f"wildcard ({result_all.request_count}) should have >= " f"KLEINK ({result_kleink.request_count}) results"
    )


# --- Merged from test_sap_integration.py ---


@pytest.mark.anyio
async def test_se09_wildcard_username(sap_mcp_client: ClientSession) -> None:
    """SE09 with username='*' must not fail due to YAML-quoted wildcard.

    Playwright's ARIA snapshot serializer quotes the '*' character because it
    is special in YAML.  The screen state parser must strip these artifact
    quotes so that the ensure_screen_state verification pass succeeds.

    Fixes #349.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)

    result = await call_tool_typed(
        sap_mcp_client,
        "sap_se09_lookup",
        {"username": "*", "request_type": "customizing", "status": "modifiable"},
        TransportListResult,
    )

    assert result.success, f"SE09 wildcard username failed: {result.error}"
    # Wildcard search on an active SAP system should return at least one transport
    assert result.request_count > 0, "Expected at least one transport with wildcard username"


@pytest.mark.anyio
async def test_sap_get_shortcuts_on_se09(sap_mcp_client: ClientSession) -> None:
    """Regression: sap_get_shortcuts crashed on SE09 with 'NoneType' has no attribute 'strip'.

    SE09 (Transport Organizer) has elements with title attributes that resolve to
    null/undefined in JS. This caused parse_shortcut_from_title to crash.

    This test captures an HTML snapshot of the SE09 screen for offline unit testing,
    then verifies sap_get_shortcuts completes without error.
    """
    await call_tool_typed(sap_mcp_client, "sap_login", {}, LoginResult)
    await sap_mcp_client.call_tool("sap_transaction", {"tcode": "SE09"})

    # Capture HTML snapshot for offline unit test
    await capture_html_snapshot(sap_mcp_client, "se09_shortcuts", overwrite=True)

    # This used to crash: 'NoneType' object has no attribute 'strip'
    data = await call_tool_typed(sap_mcp_client, "sap_get_shortcuts", {}, ShortcutsResult)
    assert data.success, f"sap_get_shortcuts failed on SE09: {data.error}"
