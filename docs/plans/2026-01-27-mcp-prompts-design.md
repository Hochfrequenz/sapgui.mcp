# MCP Prompts Design

## Overview

Add MCP prompts to the sapguimcp server. Prompts are reusable recipes that guide subagents through tested, step-by-step SAP workflows.

## Use Case

1. Main agent explores and validates an approach (transaction codes, keyboard shortcuts, field selectors)
2. Once tested, the approach becomes a prompt (recipe)
3. Parallel subagents execute the recipe without exploration

## Design Decisions

| Decision          | Choice                          | Rationale                                  |
| ----------------- | ------------------------------- | ------------------------------------------ |
| Storage format    | Markdown with YAML frontmatter  | Easy to write/maintain, version-controlled |
| Location          | `src/sapguimcp/prompts/*.md` | Alongside tools/, models/, skills/         |
| Registration      | Auto-discovery at startup       | No manual decorator per prompt             |
| Prompt name       | Derived from filename           | Keeps name and file in sync                |
| Required metadata | `description` only              | KISS, YAGNI                                |
| Formatting        | Prettier (existing CI)          | Consistent with project standards          |

## Directory Structure

```
src/sapguimcp/prompts/
├── __init__.py           # Auto-discovery + registration logic
├── README.md             # Contributor documentation
└── *.md                  # Prompt files (auto-registered)
```

## Markdown File Format

```markdown
---
description: One-line description shown in MCP prompt list
---

# Prompt Title

Step-by-step instructions...
```

## Auto-Discovery Implementation

`src/sapguimcp/prompts/__init__.py`:

- Scan `prompts/` directory for `*.md` files (excluding `README.md`)
- Parse YAML frontmatter to extract `description`
- Register each file as an MCP prompt using FastMCP
- Prompt name derived from filename stem (e.g., `se16_bulk_read.md` → `se16_bulk_read`)

## CI Validation

| Check                       | Type             | Purpose                    |
| --------------------------- | ---------------- | -------------------------- |
| Valid YAML frontmatter      | Unit test        | Catch malformed metadata   |
| `description` field present | Unit test        | Required field             |
| Snake_case filename         | Unit test        | Naming convention          |
| Prettier formatting         | Existing CI      | Consistent markdown        |
| 1 file → 1 prompt           | Integration test | Verify registration works  |
| Prompt has description      | Integration test | Verify metadata propagates |

## Test Strategy

### Unit Tests (fast, no server)

- `test_all_prompt_files_have_valid_frontmatter()`
- `test_prompt_filenames_are_snake_case()`
- `test_parse_frontmatter()` - utility function tests

### Integration Tests

- `test_prompt_count_matches_files()` - each .md file becomes one prompt
- `test_all_prompts_have_descriptions()` - metadata propagates correctly

## Contributor Documentation

README.md in prompts/ directory explaining:

- How to create a prompt
- File format with example
- Validation requirements
- How to test locally
