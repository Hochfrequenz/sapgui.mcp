# Prompts

MCP prompts are reusable recipes for SAP automation tasks. They guide subagents through tested, step-by-step workflows.

## Use Case

1. Main agent explores and validates an approach (transaction codes, keyboard shortcuts, field selectors)
2. Once tested, the approach becomes a prompt (recipe)
3. Parallel subagents execute the recipe without exploration

## Creating a Prompt

1. Create a new `.md` file in this directory
2. Use snake_case filename (e.g., `se16_bulk_read.md`)
3. Add YAML frontmatter with `description`
4. Write the recipe in markdown

## File Format

```markdown
---
description: One-line description shown in MCP prompt list
---

# Prompt Title

## Overview

Brief description of what this recipe accomplishes.

## Prerequisites

- User must be logged into SAP
- Required authorizations

## Steps

1. Step one with tool calls
2. Step two...

## Error Handling

Common errors and how to recover.
```

## Validation

CI enforces:

- Valid YAML frontmatter with `description` (at least 10 characters)
- Snake_case filename (must start with lowercase letter, then lowercase letters, numbers, or underscores)
- Prettier-formatted markdown

Run locally:

```bash
tox -e unit_tests  # Validates prompt files
npm run format     # Formats markdown
```

## Example

See `se16_bulk_read.md` for a complete example.
