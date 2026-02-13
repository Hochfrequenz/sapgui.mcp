"""
Workflow tools for repetitive SAP task automation.

This module provides tools to learn, save, run, and share workflows
for bulk SAP operations with minimal context consumption.

Key feature: workflow_run uses server-side agent loops via ctx.sample()
to execute workflows without filling the client's context.
"""

import logging

import httpx
from fastmcp import Context, FastMCP

from sapwebguimcp.models import (
    Workflow,
    WorkflowDeleteResult,
    WorkflowError,
    WorkflowListResult,
    WorkflowRunResult,
    WorkflowSaveInput,
    WorkflowSaveResult,
    WorkflowSubmitResult,
)
from sapwebguimcp.models.config import get_settings
from sapwebguimcp.models.workflow_storage import (
    delete_workflow,
    is_bundled_workflow,
    load_all_workflows,
    load_workflow,
    save_workflow,
)
from sapwebguimcp.tools.sap_tool_impl import get_sampling_tools

__all__ = ["register_workflow_tools"]

_logger = logging.getLogger(__name__)


async def _execute_workflow_run(  # pylint: disable=too-many-locals
    name: str,
    items: list[dict[str, str]],
    ctx: Context,
) -> WorkflowRunResult:
    """
    Execute a workflow for multiple items using server-side agent loops.

    This is the implementation extracted from workflow_run to reduce
    statement count in register_workflow_tools.
    """
    _logger.warning(
        "workflow_run called - using ctx.sample() for server-side agent loops. "
        "WARNING (January 2026): This tool is UNTESTED because no MCP client currently "
        "supports both sampling AND SAP authentication. "
        "See docs/testing/workflow-sampling-copilot-setup.md for client compatibility."
    )

    workflow = load_workflow(name)
    if not workflow:
        return WorkflowRunResult.failure(
            f"Workflow '{name}' not found. Use workflow_list to see available workflows.",
            total=len(items),
        )

    # Fail-fast: test sampling support before processing any items
    try:
        await ctx.sample(messages="Test sampling support. Reply with 'OK'.", tools=[])
    except Exception as e:  # pylint: disable=broad-exception-caught
        error_str = str(e)
        if "sampling" in error_str.lower() or "not support" in error_str.lower():
            return WorkflowRunResult.failure(
                "Client does not support MCP Sampling. This tool requires a sampling-capable "
                "client. As of January 2026, Claude Desktop/Code do NOT support sampling. "
                "Fallback: Use the workflow prompt from workflow_list as guidance and "
                "execute items manually with individual tool calls.",
                total=len(items),
            )
        # Other errors during test - log but continue (might be transient)
        _logger.warning("Sampling test failed with unexpected error", extra={"error": error_str})

    results: list[str] = []
    errors: list[WorkflowError] = []

    for i, item in enumerate(items):
        await ctx.report_progress(progress=i, total=len(items))

        try:
            result = await ctx.sample(
                messages=f"{workflow.prompt}\n\nCurrent item ({i + 1}/{len(items)}):\n"
                + "\n".join(f"  {k}: {v}" for k, v in item.items())
                + "\n\nExecute the workflow for this item. Return a short confirmation like "
                '"BP 12345: Max Mustermann created" on success, or describe the error if it fails.',
                tools=get_sampling_tools(),
            )
            results.append(result.text or f"Item {i + 1} completed")
            _logger.info(
                "Workflow item completed", extra={"item": i + 1, "total": len(items), "result": results[-1][:100]}
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            _logger.warning("Workflow item failed", extra={"item": i + 1, "total": len(items), "error": str(e)})
            item_summary = ", ".join(f"{k}={v}" for k, v in list(item.items())[:3])
            errors.append(
                WorkflowError(
                    input_summary=item_summary + (", ..." if len(item) > 3 else ""),
                    error=str(e),
                )
            )

    await ctx.report_progress(progress=len(items), total=len(items))

    _logger.info(
        "Workflow completed",
        extra={"workflow": name, "succeeded": len(results), "total": len(items), "failed": len(errors)},
    )

    return WorkflowRunResult(
        total=len(items),
        succeeded=len(results),
        failed=len(errors),
        succeeded_items=results,
        errors=errors,
    )


async def _create_workflow_issue(
    pat: str,
    repo: str,
    workflow: Workflow,
) -> tuple[str | None, str | None]:
    """
    Create a GitHub issue for a workflow submission.

    Returns:
        (issue_url, None) on success
        (None, error_message) on failure
    """
    headers = {
        "Authorization": f"Bearer {pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Ensure label exists
            label_url = f"https://api.github.com/repos/{repo}/labels/workflow-submission"
            response = await client.get(label_url, headers=headers)
            if response.status_code != 200:
                create_url = f"https://api.github.com/repos/{repo}/labels"
                payload = {
                    "name": "workflow-submission",
                    "color": "0e8a16",  # Green
                    "description": "User-submitted workflow for review",
                }
                await client.post(create_url, headers=headers, json=payload)

            # Create the issue
            title = f"Workflow: {workflow.name} - {workflow.description}"
            body = f"""## Workflow Submission

**Name**: `{workflow.name}`
**Author**: {workflow.author}

### Description

{workflow.description}

### When to Use

{workflow.applicable_when}

### When NOT to Use

{workflow.not_applicable_when or "(not specified)"}

### Workflow Prompt

```
{workflow.prompt}
```

---

*Submitted via `workflow_submit` tool*
"""

            url = f"https://api.github.com/repos/{repo}/issues"
            issue_payload: dict[str, str | list[str]] = {
                "title": title,
                "body": body,
                "labels": ["workflow-submission"],
            }
            response = await client.post(url, headers=headers, json=issue_payload)
            if response.status_code == 201:
                return response.json().get("html_url"), None
            return None, f"GitHub API error: {response.status_code} - {response.text}"
    except httpx.RequestError as e:
        return None, f"Request failed: {e}"


def register_workflow_tools(mcp: FastMCP) -> None:
    """Register workflow automation tools with the MCP server."""

    @mcp.tool(
        description=(
            "List all available workflows for repetitive SAP tasks. "
            "Shows bundled workflows (shipped with server) and user-created workflows. "
            "User workflows (~/.sap-mcp/workflows/) override bundled ones with same name. "
            "Use 'applicable_when' field to find the right workflow for your task."
        )
    )
    async def workflow_list() -> WorkflowListResult:  # pylint: disable=missing-function-docstring
        try:
            workflows = load_all_workflows()
            return WorkflowListResult(workflows=workflows)
        except Exception as e:  # pylint: disable=broad-exception-caught
            _logger.exception("Listing workflows")
            return WorkflowListResult.failure(f"Error listing workflows: {e}")

    @mcp.tool(
        description=(
            "Save a learned workflow for future use. "
            "Use after successfully completing 2-3 iterations manually "
            "to capture the optimized prompt for bulk execution with workflow_run. "
            "Args: workflow_input = WorkflowSaveInput with name, description, prompt, "
            "applicable_when, not_applicable_when, and optional author."
        )
    )
    async def workflow_save(  # pylint: disable=missing-function-docstring
        workflow_input: WorkflowSaveInput,
        _: Context | None = None,
    ) -> WorkflowSaveResult:
        try:
            # Default author to configured SAP user
            author = workflow_input.author
            if not author:
                settings = get_settings()
                author = settings.sap_user or "unknown"

            workflow = Workflow(
                name=workflow_input.name,
                description=workflow_input.description,
                prompt=workflow_input.prompt,
                applicable_when=workflow_input.applicable_when,
                not_applicable_when=workflow_input.not_applicable_when,
                author=author,
            )

            path = save_workflow(workflow)
            _logger.info("Saved workflow", extra={"workflow": workflow_input.name, "path": str(path)})

            return WorkflowSaveResult(name=workflow_input.name, path=str(path))
        except Exception as e:  # pylint: disable=broad-exception-caught
            _logger.exception("Saving workflow", extra={"workflow": workflow_input.name})
            return WorkflowSaveResult.failure(f"Error saving workflow: {e}", name=workflow_input.name, path="")

    @mcp.tool(
        description=(
            "Execute a workflow for repetitive SAP tasks using server-side agent loops. "
            "Use when user requests bulk operations ('create 100...', 'for each entry...', 'repeat for all...'). "
            "Preserves client context by running iterations server-side via ctx.sample(). "
            "REQUIRES: MCP Sampling support - Claude Desktop/Code do NOT support sampling (Jan 2026). "
            "FALLBACK: If sampling unavailable, use workflow_list to get prompt and execute manually. "
            "WARNING: UNTESTED - no client currently supports both sampling AND SAP auth."
        )
    )
    async def workflow_run(  # pylint: disable=missing-function-docstring
        name: str,
        items: list[dict[str, str]],
        ctx: Context,
    ) -> WorkflowRunResult:
        return await _execute_workflow_run(name, items, ctx)

    @mcp.tool(
        description=(
            "Share a working workflow with the development team via GitHub issue. "
            "Use when you have a workflow that works well and could help others. "
            "Creates a GitHub issue for review - may be added to bundled workflows. "
            "REQUIRES: GITHUB_PAT configured."
        )
    )
    async def workflow_submit(name: str) -> WorkflowSubmitResult:  # pylint: disable=missing-function-docstring
        # Load workflow
        workflow = load_workflow(name)
        if not workflow:
            return WorkflowSubmitResult.failure(
                f"Workflow '{name}' not found. Use workflow_list to see available workflows.",
                name=name,
            )

        # Check GitHub PAT
        settings = get_settings()
        if not settings.github_pat:
            return WorkflowSubmitResult.failure(
                "GITHUB_PAT not configured. Cannot submit workflow without GitHub access.",
                name=name,
            )

        # Create GitHub issue
        issue_url, error = await _create_workflow_issue(
            pat=settings.github_pat,
            repo=settings.github_repo,
            workflow=workflow,
        )

        if error:
            return WorkflowSubmitResult.failure(f"Failed to create GitHub issue: {error}", name=name)

        _logger.info("Submitted workflow", extra={"workflow": name, "issue_url": issue_url})

        return WorkflowSubmitResult(name=name, issue_url=issue_url)

    @mcp.tool(
        description=(
            "Delete a user-created workflow. "
            "Only user workflows (~/.sap-mcp/workflows/) can be deleted - "
            "bundled workflows shipped with the server cannot be deleted."
        )
    )
    async def workflow_delete(name: str) -> WorkflowDeleteResult:  # pylint: disable=missing-function-docstring
        # Check if it's a bundled workflow
        if is_bundled_workflow(name):
            return WorkflowDeleteResult.failure(
                f"Cannot delete bundled workflow '{name}'. " "Only user-created workflows can be deleted.",
                name=name,
            )

        # Try to delete
        if delete_workflow(name):
            _logger.info("Deleted workflow", extra={"workflow": name})
            return WorkflowDeleteResult(name=name)

        return WorkflowDeleteResult.failure(f"Workflow '{name}' not found in user workflows.", name=name)
