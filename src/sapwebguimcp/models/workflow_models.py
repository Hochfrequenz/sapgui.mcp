"""Workflow models for repetitive SAP task automation."""

import yaml
from pydantic import BaseModel, Field

from sapwebguimcp.models.base import ToolResult


class Workflow(BaseModel):
    """A learned, optimized workflow prompt for repetitive SAP tasks."""

    name: str = Field(description="Unique identifier for the workflow, e.g. 'bp-creation'")
    description: str = Field(
        description="Short description of what the workflow does, e.g. 'Business Partner anlegen (Person)'"
    )
    author: str = Field(description="SAP username of the person who created/refined this workflow, e.g. 'kleink'")
    prompt: str = Field(
        description="The optimized prompt containing step-by-step instructions "
        "and learnings from previous executions"
    )
    applicable_when: str = Field(
        description="Conditions under which this workflow should be used, "
        "e.g. 'Personen als Business Partner anlegen (natuerliche Personen)'"
    )
    not_applicable_when: str | None = Field(
        default=None,
        description="Conditions under which this workflow should NOT be used, "
        "e.g. 'Organisationen/Firmen anlegen - dafuer F6 statt F5'",
    )

    @classmethod
    def from_markdown(cls, name: str, content: str) -> "Workflow":
        """Parse a workflow from markdown with YAML frontmatter."""
        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid workflow format: missing YAML frontmatter in {name}")
        _, frontmatter, prompt = parts
        meta = yaml.safe_load(frontmatter)
        return cls(name=name, prompt=prompt.strip(), **meta)

    def to_markdown(self) -> str:
        """Serialize workflow to markdown with YAML frontmatter."""
        lines = [
            "---",
            f"description: {self.description}",
            f"author: {self.author}",
            f"applicable_when: {self.applicable_when}",
        ]
        if self.not_applicable_when:
            lines.append(f"not_applicable_when: {self.not_applicable_when}")
        lines.append("---")
        lines.append("")
        lines.append(self.prompt)
        return "\n".join(lines)


class WorkflowError(BaseModel):
    """Details about a failed workflow item."""

    input_summary: str = Field(description="Identifying info of the failed item, e.g. 'Max Mustermann, Berlin'")
    error: str = Field(description="What went wrong, e.g. 'Pflichtfeld PLZ leer'")


class WorkflowRunResult(ToolResult):
    """Result from workflow_run tool."""

    total: int = Field(default=0, description="Total items to process, e.g. 100")
    succeeded: int = Field(default=0, description="Successfully completed, e.g. 95")
    failed: int = Field(default=0, description="Failed items, e.g. 5")
    succeeded_items: list[str] = Field(
        default_factory=list,
        description="Short confirmations, e.g. ['BP 12345: Max Mustermann']",
    )
    errors: list[WorkflowError] = Field(
        default_factory=list,
        description="Details about failed items",
    )


class WorkflowListResult(ToolResult):
    """Result from workflow_list tool."""

    workflows: list[Workflow] = Field(
        default_factory=list,
        description="List of available workflows (bundled + user)",
    )


class WorkflowSaveInput(BaseModel):
    """Input parameters for workflow_save tool."""

    name: str = Field(description="Unique identifier (e.g., 'bp-creation', 'material-master')")
    description: str = Field(description="Short description of what the workflow does")
    prompt: str = Field(description="The optimized prompt with step-by-step instructions")
    applicable_when: str = Field(description="When this workflow should be used")
    not_applicable_when: str | None = Field(
        default=None,
        description="When this workflow should NOT be used",
    )
    author: str | None = Field(
        default=None,
        description="SAP username (defaults to SAP_USER from config)",
    )


class WorkflowSaveResult(ToolResult):
    """Result from workflow_save tool."""

    name: str = Field(description="Name of the saved workflow")
    path: str = Field(description="Path where the workflow was saved")


class WorkflowDeleteResult(ToolResult):
    """Result from workflow_delete tool."""

    name: str = Field(description="Name of the deleted workflow")


class WorkflowSubmitResult(ToolResult):
    """Result from workflow_submit tool."""

    name: str = Field(description="Name of the submitted workflow")
    issue_url: str | None = Field(default=None, description="URL of the created GitHub issue")
