"""Workflow storage layer for loading and saving workflows."""

import logging
from pathlib import Path

from sapwebguimcp.models.workflow_models import Workflow

__all__ = [
    "load_workflow",
    "load_all_workflows",
    "save_workflow",
    "delete_workflow",
    "is_bundled_workflow",
    "is_user_workflow",
]

logger = logging.getLogger(__name__)

# Bundled workflows directory (inside package)
BUNDLED_WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"

# User workflows directory (in user's home)
USER_WORKFLOWS_DIR = Path.home() / ".sap-mcp" / "workflows"


def get_bundled_workflows_dir() -> Path:
    """Get the bundled workflows directory."""
    return BUNDLED_WORKFLOWS_DIR


def get_user_workflows_dir() -> Path:
    """Get the user workflows directory, creating it if necessary."""
    USER_WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    return USER_WORKFLOWS_DIR


def load_workflow(name: str) -> Workflow | None:
    """
    Load a workflow by name.

    User workflows take precedence over bundled workflows.

    Args:
        name: Workflow name (without .md extension)

    Returns:
        Workflow if found, None otherwise
    """
    # Check user workflows first (higher priority)
    user_path = get_user_workflows_dir() / f"{name}.md"
    if user_path.exists():
        content = user_path.read_text(encoding="utf-8")
        return Workflow.from_markdown(name, content)

    # Fall back to bundled workflows
    bundled_path = get_bundled_workflows_dir() / f"{name}.md"
    if bundled_path.exists():
        content = bundled_path.read_text(encoding="utf-8")
        return Workflow.from_markdown(name, content)

    return None


def load_all_workflows() -> list[Workflow]:
    """
    Load all available workflows.

    User workflows override bundled workflows with the same name.

    Returns:
        List of all workflows, with user workflows taking precedence
    """
    workflows: dict[str, Workflow] = {}

    # Load bundled workflows first
    bundled_dir = get_bundled_workflows_dir()
    if bundled_dir.exists():
        for path in bundled_dir.glob("*.md"):
            name = path.stem
            try:
                content = path.read_text(encoding="utf-8")
                workflows[name] = Workflow.from_markdown(name, content)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Could not load bundled workflow", extra={"name": name, "error": str(e)})

    # Load user workflows (override bundled)
    user_dir = get_user_workflows_dir()
    if user_dir.exists():
        for path in user_dir.glob("*.md"):
            name = path.stem
            try:
                content = path.read_text(encoding="utf-8")
                workflows[name] = Workflow.from_markdown(name, content)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("Could not load user workflow", extra={"name": name, "error": str(e)})

    return list(workflows.values())


def save_workflow(workflow: Workflow) -> Path:
    """
    Save a workflow to the user workflows directory.

    Args:
        workflow: Workflow to save

    Returns:
        Path where the workflow was saved
    """
    user_dir = get_user_workflows_dir()
    path = user_dir / f"{workflow.name}.md"
    path.write_text(workflow.to_markdown(), encoding="utf-8")
    logger.info("Saved workflow", extra={"name": workflow.name, "path": str(path)})
    return path


def delete_workflow(name: str) -> bool:
    """
    Delete a user workflow.

    Only user workflows can be deleted, not bundled ones.

    Args:
        name: Workflow name to delete

    Returns:
        True if deleted, False if not found or is bundled
    """
    user_path = get_user_workflows_dir() / f"{name}.md"
    if user_path.exists():
        user_path.unlink()
        logger.info("Deleted user workflow", extra={"name": name})
        return True
    return False


def is_bundled_workflow(name: str) -> bool:
    """Check if a workflow is bundled (not user-created)."""
    bundled_path = get_bundled_workflows_dir() / f"{name}.md"
    return bundled_path.exists()


def is_user_workflow(name: str) -> bool:
    """Check if a workflow exists in user directory."""
    user_path = get_user_workflows_dir() / f"{name}.md"
    return user_path.exists()
