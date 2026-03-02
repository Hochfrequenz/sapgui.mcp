"""
Workflow tools for repetitive SAP task automation.

This module provides tools to learn, save, and share workflows
for bulk SAP operations with minimal context consumption.

Workflows can be learned, saved, shared, and executed manually using
the prompts from workflow_list.
"""

import logging

import httpx
from fastmcp import Context, FastMCP

from sapwebguimcp.models import (
    Workflow,
    WorkflowDeleteResult,
    WorkflowListResult,
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

__all__ = ["register_workflow_tools"]

_logger = logging.getLogger(__name__)


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
            "to capture the optimized prompt for future bulk execution. "
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
