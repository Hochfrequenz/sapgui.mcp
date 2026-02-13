"""
MCP prompts for SAP Web GUI automation.

This module provides auto-discovery and registration of markdown-based prompts.
Each .md file in this directory (except README.md) becomes an MCP prompt.

Prompts are reusable recipes that guide subagents through tested, step-by-step
SAP workflows. The main agent validates an approach, then parallel subagents
execute the proven recipe.
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from fastmcp import FastMCP

__all__ = ["register_prompts", "parse_frontmatter", "validate_prompt_file", "PromptValidationError"]

logger = logging.getLogger(__name__)

# Pattern for valid prompt filenames (snake_case)
SNAKE_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class PromptValidationError(Exception):
    """Raised when a prompt file fails validation."""


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """
    Extract YAML frontmatter and markdown body from content.

    Args:
        content: Full markdown content with optional YAML frontmatter.

    Returns:
        Tuple of (frontmatter dict, markdown body).
        If no frontmatter, returns empty dict and full content.
    """
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter_yaml = parts[1]
    body = parts[2].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_yaml) or {}
    except yaml.YAMLError as e:
        raise PromptValidationError(f"Invalid YAML frontmatter: {e}") from e

    return frontmatter, body


def validate_prompt_file(file_path: Path) -> tuple[str, dict[str, Any], str]:
    """
    Validate a prompt file and return its components.

    Args:
        file_path: Path to the markdown prompt file.

    Returns:
        Tuple of (prompt_name, frontmatter, body).
        The body is the markdown content without the YAML frontmatter.

    Raises:
        PromptValidationError: If the file fails validation.
    """
    # Validate filename is snake_case (must start with lowercase letter)
    stem = file_path.stem
    if not SNAKE_CASE_PATTERN.match(stem):
        raise PromptValidationError(
            f"Filename '{file_path.name}' must be snake_case "
            "(must start with lowercase letter, then lowercase letters, numbers, underscores)"
        )

    # Read and parse content
    content = file_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(content)

    # Validate required fields
    if "description" not in frontmatter:
        raise PromptValidationError(f"Missing required 'description' field in frontmatter of '{file_path.name}'")

    description = frontmatter["description"]
    if not isinstance(description, str) or len(description.strip()) < 10:
        raise PromptValidationError(f"'description' in '{file_path.name}' must be a string with at least 10 characters")

    return stem, frontmatter, body


def register_prompts(mcp: FastMCP) -> None:
    """
    Scan prompts directory and register each .md file as an MCP prompt.

    Args:
        mcp: FastMCP server instance to register prompts with.

    Raises:
        PromptValidationError: If any prompt file fails validation.
    """
    prompt_dir = Path(__file__).parent
    md_files = sorted(prompt_dir.glob("*.md"))
    registered_count = 0

    for md_file in md_files:
        # Skip README.md
        if md_file.name.lower() == "readme.md":
            continue

        # Validate and parse the file - returns body without frontmatter
        prompt_name, frontmatter, body = validate_prompt_file(md_file)
        description = frontmatter["description"]

        # Register with FastMCP using a factory to capture the content
        # We use body (without frontmatter) as the prompt content
        def make_prompt_fn(content: str) -> Callable[[], str]:
            def prompt_fn() -> str:
                return content

            return prompt_fn

        mcp.prompt(name=prompt_name, description=description)(make_prompt_fn(body))

        logger.info("Registered prompt", extra={"prompt": prompt_name})
        registered_count += 1

    if registered_count == 0:
        logger.warning("No prompt files found", extra={"directory": str(prompt_dir)})
    else:
        logger.info("Registered prompts", extra={"count": registered_count, "directory": str(prompt_dir)})
