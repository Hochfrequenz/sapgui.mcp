"""Tests for the prompts module."""

import tempfile
from pathlib import Path
from typing import Any

import pytest

from sapguimcp.prompts import PromptValidationError
from sapguimcp.prompts import __file__ as prompts_module_file
from sapguimcp.prompts import parse_frontmatter, validate_prompt_file


def get_prompts_dir() -> Path:
    """Get the prompts directory using the module's location."""
    return Path(prompts_module_file).parent


class TestParseFrontmatter:
    """Tests for parse_frontmatter function."""

    def test_valid_frontmatter(self) -> None:
        """Test parsing valid YAML frontmatter."""
        content = """---
description: A test prompt description
---
# Heading

Body content here.
"""
        frontmatter, body = parse_frontmatter(content)

        assert frontmatter["description"] == "A test prompt description"
        assert body == "# Heading\n\nBody content here."

    def test_no_frontmatter(self) -> None:
        """Test content without frontmatter."""
        content = "# Just a heading\n\nSome content."
        frontmatter, body = parse_frontmatter(content)

        assert frontmatter == {}
        assert body == content

    def test_empty_frontmatter(self) -> None:
        """Test empty frontmatter block."""
        content = """---
---
# Heading
"""
        frontmatter, body = parse_frontmatter(content)

        assert frontmatter == {}
        assert body == "# Heading"

    def test_invalid_yaml(self) -> None:
        """Test that invalid YAML raises PromptValidationError."""
        content = """---
description: [invalid yaml
  broken: structure
---
# Heading
"""
        with pytest.raises(PromptValidationError, match="Invalid YAML frontmatter"):
            parse_frontmatter(content)

    def test_frontmatter_with_multiple_fields(self) -> None:
        """Test frontmatter with extra fields (ignored but parsed)."""
        content = """---
description: Main description
extra_field: some value
another: 123
---
# Content
"""
        frontmatter, body = parse_frontmatter(content)

        assert frontmatter["description"] == "Main description"
        assert frontmatter["extra_field"] == "some value"
        assert frontmatter["another"] == 123

    def test_frontmatter_with_dashes_in_body(self) -> None:
        """Test that --- in the body doesn't confuse the parser."""
        content = """---
description: A valid description
---
# Title

Some content with --- in the middle
---
This should still be part of the body
"""
        frontmatter, body = parse_frontmatter(content)

        assert frontmatter["description"] == "A valid description"
        assert "---" in body
        assert "This should still be part of the body" in body


class TestValidatePromptFile:
    """Tests for validate_prompt_file function."""

    def test_valid_prompt_file(self) -> None:
        """Test validation of a properly formatted prompt file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "valid_prompt.md"
            file_path.write_text(
                """---
description: A valid prompt with sufficient description length
---
# Valid Prompt

Content here.
""",
                encoding="utf-8",
            )

            name, frontmatter, body = validate_prompt_file(file_path)

            assert name == "valid_prompt"
            assert frontmatter["description"] == "A valid prompt with sufficient description length"
            assert "# Valid Prompt" in body

    def test_invalid_filename_uppercase(self) -> None:
        """Test that uppercase filenames are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "InvalidPrompt.md"
            file_path.write_text(
                """---
description: A valid description here
---
# Content
""",
                encoding="utf-8",
            )

            with pytest.raises(PromptValidationError, match="must be snake_case"):
                validate_prompt_file(file_path)

    def test_invalid_filename_hyphen(self) -> None:
        """Test that hyphens in filenames are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "invalid-prompt.md"
            file_path.write_text(
                """---
description: A valid description here
---
# Content
""",
                encoding="utf-8",
            )

            with pytest.raises(PromptValidationError, match="must be snake_case"):
                validate_prompt_file(file_path)

    def test_missing_description(self) -> None:
        """Test that missing description field is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "missing_desc.md"
            file_path.write_text(
                """---
other_field: value
---
# Content
""",
                encoding="utf-8",
            )

            with pytest.raises(PromptValidationError, match="Missing required 'description'"):
                validate_prompt_file(file_path)

    def test_description_too_short(self) -> None:
        """Test that short descriptions are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "short_desc.md"
            file_path.write_text(
                """---
description: Short
---
# Content
""",
                encoding="utf-8",
            )

            with pytest.raises(PromptValidationError, match="at least 10 characters"):
                validate_prompt_file(file_path)

    def test_description_not_string(self) -> None:
        """Test that non-string description is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "bad_desc.md"
            file_path.write_text(
                """---
description: 12345678901
---
# Content
""",
                encoding="utf-8",
            )

            # YAML parses this as an integer, so validation should reject it
            with pytest.raises(PromptValidationError, match="must be a string"):
                validate_prompt_file(file_path)

    def test_valid_snake_case_with_numbers(self) -> None:
        """Test that snake_case with numbers is valid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "se16_bulk_read_v2.md"
            file_path.write_text(
                """---
description: A valid prompt description here
---
# Content
""",
                encoding="utf-8",
            )

            name, frontmatter, body = validate_prompt_file(file_path)
            assert name == "se16_bulk_read_v2"

    def test_invalid_filename_underscore_start(self) -> None:
        """Test that filenames starting with underscore are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "_private_prompt.md"
            file_path.write_text(
                """---
description: A valid description here
---
# Content
""",
                encoding="utf-8",
            )

            with pytest.raises(PromptValidationError, match="must be snake_case"):
                validate_prompt_file(file_path)


def _get_registered_prompts() -> dict[str, Any]:
    """Get registered prompts as {name: prompt} dict, compatible with fastmcp 2.x and 3.x.

    fastmcp 2.x: get_prompts() returns dict[str, FunctionPrompt]
    fastmcp 3.x: list_prompts() returns list[FunctionPrompt]  (get_prompts removed)
    """
    import asyncio

    from sapguimcp.server import mcp

    if hasattr(mcp, "list_prompts"):
        prompts_list = asyncio.run(mcp.list_prompts())
        if isinstance(prompts_list, dict):
            return prompts_list
        return {p.name: p for p in prompts_list}
    # fastmcp 2.x fallback
    return asyncio.run(mcp.get_prompts())  # type: ignore[union-attr]


class TestPromptRegistration:
    """Integration tests for prompt registration with FastMCP."""

    def test_prompt_count_matches_files(self) -> None:
        """Each .md file in prompts/ becomes exactly one MCP prompt."""
        prompt_dir = get_prompts_dir()
        md_files = [f for f in prompt_dir.glob("*.md") if f.name.lower() != "readme.md"]

        prompts = _get_registered_prompts()

        assert len(prompts) == len(md_files), (
            f"Expected {len(md_files)} prompts, got {len(prompts)}. "
            f"Files: {[f.name for f in md_files]}, Prompts: {list(prompts.keys())}"
        )

    def test_all_prompts_have_descriptions(self) -> None:
        """Every registered prompt must have a non-empty description."""
        prompts = _get_registered_prompts()

        for name, prompt in prompts.items():
            assert prompt.description, f"Prompt '{name}' has no description"
            assert len(prompt.description) >= 10, f"Prompt '{name}' description too short: '{prompt.description}'"

    def test_prompt_names_match_filenames(self) -> None:
        """Prompt names should match their source filenames (without .md)."""
        prompt_dir = get_prompts_dir()
        md_files = [f for f in prompt_dir.glob("*.md") if f.name.lower() != "readme.md"]
        expected_names = {f.stem for f in md_files}

        prompts = _get_registered_prompts()
        actual_names = set(prompts.keys())

        assert actual_names == expected_names, f"Mismatch: expected {expected_names}, got {actual_names}"


class TestPromptFilesInProject:
    """Tests that validate actual prompt files in the project."""

    def test_all_prompt_files_have_valid_frontmatter(self) -> None:
        """Each .md file in prompts/ must have valid frontmatter with description."""
        prompt_dir = get_prompts_dir()

        if not prompt_dir.exists():
            pytest.skip("Prompts directory not found")

        md_files = [f for f in prompt_dir.glob("*.md") if f.name.lower() != "readme.md"]

        if not md_files:
            pytest.skip("No prompt files found")

        for md_file in md_files:
            # This will raise PromptValidationError if invalid
            name, frontmatter, body = validate_prompt_file(md_file)
            assert "description" in frontmatter
            assert len(frontmatter["description"]) >= 10

    def test_prompt_filenames_are_snake_case(self) -> None:
        """Prompt filenames must be snake_case."""
        prompt_dir = get_prompts_dir()

        if not prompt_dir.exists():
            pytest.skip("Prompts directory not found")

        md_files = [f for f in prompt_dir.glob("*.md") if f.name.lower() != "readme.md"]

        for md_file in md_files:
            # validate_prompt_file checks snake_case
            validate_prompt_file(md_file)
