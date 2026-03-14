"""Integration tests for workflow tools (workflow_list, workflow_save, workflow_delete)."""

import pytest
from mcp import ClientSession

from sapwebguimcp.models import (
    WorkflowDeleteResult,
    WorkflowListResult,
    WorkflowSaveResult,
)

from .conftest import call_tool_typed


@pytest.mark.anyio
async def test_workflow_list_returns_bundled_workflows(sap_mcp_client: ClientSession) -> None:
    """
    Test that workflow_list returns bundled workflows.

    This verifies:
    1. The workflow_list tool is registered and callable
    2. Bundled workflows (shipped with the package) are listed
    3. The response has expected structure with workflow metadata
    """
    data = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert data.success, f"workflow_list failed: {data.error}"

    # Should have a workflows list
    workflows = data.workflows

    # Should have at least one bundled workflow
    assert len(workflows) >= 1, f"Expected at least one bundled workflow: {workflows}"

    # Verify workflow structure
    first_workflow = workflows[0]
    required_fields = ["name", "description", "author", "prompt", "applicable_when"]
    for field in required_fields:
        assert hasattr(first_workflow, field), f"Workflow missing '{field}': {first_workflow}"

    print(f"\nFound {len(workflows)} workflows:")
    for wf in workflows:
        print(f"  - {wf.name}: {wf.description}")


@pytest.mark.anyio
async def test_workflow_save_and_delete(sap_mcp_client: ClientSession) -> None:
    """
    Test saving and deleting a user workflow.

    This verifies:
    1. workflow_save creates a new workflow in user directory
    2. The workflow appears in workflow_list
    3. workflow_delete removes the workflow
    4. The workflow is gone from workflow_list
    """
    test_workflow_name = "test-integration-workflow-12345"

    # Save a test workflow
    save_data = await call_tool_typed(
        sap_mcp_client,
        "workflow_save",
        {
            "workflow_input": {
                "name": test_workflow_name,
                "description": "Test workflow for integration tests",
                "prompt": "This is a test prompt for integration testing",
                "applicable_when": "During integration tests",
                "not_applicable_when": "In production",
                "author": "integration-test",
            }
        },
        WorkflowSaveResult,
    )
    assert save_data.success, f"workflow_save failed: {save_data.error}"

    assert save_data.name == test_workflow_name, f"Name mismatch: {save_data}"
    assert save_data.path, f"Expected path in response: {save_data}"

    print(f"\nSaved workflow to: {save_data.path}")

    # Verify it appears in list
    list_data = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert list_data.success, f"workflow_list after save failed: {list_data.error}"

    workflow_names = [w.name for w in list_data.workflows]
    assert test_workflow_name in workflow_names, f"Saved workflow not in list: {workflow_names}"

    # Delete the workflow
    delete_data = await call_tool_typed(
        sap_mcp_client, "workflow_delete", {"name": test_workflow_name}, WorkflowDeleteResult
    )
    assert delete_data.success, f"workflow_delete failed: {delete_data.error}"

    assert delete_data.name == test_workflow_name, f"Name mismatch: {delete_data}"

    # Verify it's gone from list
    list_data2 = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert list_data2.success, f"workflow_list after delete failed: {list_data2.error}"

    workflow_names2 = [w.name for w in list_data2.workflows]
    assert test_workflow_name not in workflow_names2, f"Deleted workflow still in list: {workflow_names2}"

    print("Workflow save/delete cycle completed successfully")


@pytest.mark.anyio
async def test_workflow_delete_bundled_fails(sap_mcp_client: ClientSession) -> None:
    """
    Test that deleting a bundled workflow fails.

    Bundled workflows (shipped with the package) cannot be deleted.
    Only user-created workflows can be deleted.
    """
    # First get a bundled workflow name
    list_data = await call_tool_typed(sap_mcp_client, "workflow_list", {}, WorkflowListResult)
    assert list_data.success, f"workflow_list failed: {list_data.error}"

    workflows = list_data.workflows
    if not workflows:
        pytest.skip("No bundled workflows to test with")

    bundled_name = workflows[0].name
    print(f"\nAttempting to delete bundled workflow: {bundled_name}")

    # Try to delete it
    delete_data = await call_tool_typed(sap_mcp_client, "workflow_delete", {"name": bundled_name}, WorkflowDeleteResult)

    # Should fail
    assert not delete_data.success, f"Should not be able to delete bundled workflow: {delete_data}"
    error_msg = delete_data.error or ""
    assert (
        "bundled" in error_msg.lower() or "cannot delete" in error_msg.lower()
    ), f"Error should mention bundled: {delete_data}"

    print(f"Correctly rejected: {delete_data.error}")
