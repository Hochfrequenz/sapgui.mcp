# Contributing to SAP Web GUI MCP Server

Thank you for contributing to this project! This guide covers coding standards and best practices.

## Development Setup

```bash
# Clone and install
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp
pip install -e ".[dev]"

# Create virtual environment in .tox/dev/
tox -e dev

# Run linting
tox -e linting

# Run type check
tox -e type_check

# Run tests
tox -e unittests
# note only few tests run without SAP system access, the others will be skipped.
```

## MCP Tool Guidelines

### Tool Descriptions (Important!)

**All important information must go in the `description` parameter, NOT the docstring.**

AI clients read the `description` to understand how to use tools. The docstring is for developers only.

```python
# CORRECT - info in description
@mcp.tool(
    description=(
        "Discover clickable buttons on the current SAP screen. "
        "Returns buttons with label, selector (for browser_click), shortcut. "
        "Use the 'selector' field with browser_click to click buttons reliably. "
        "For input fields use sap_discover_fields instead."
    )
)
async def sap_discover_buttons() -> DiscoveredButtons:
    """Discover all clickable buttons on the current SAP screen."""
    ...

# WRONG - info hidden in docstring
@mcp.tool(description="Discover buttons")
async def sap_discover_buttons() -> DiscoveredButtons:
    """
    Discover all clickable buttons on the current SAP screen.

    Returns buttons with label, selector, shortcut...
    Use the 'selector' field with browser_click...
    """
    ...
```

### JavaScript Files

- Place JavaScript in `src/sapwebguimcp/js/`
- Use IIFE pattern: `() => { ... }`
- Load with `_load_js("filename.js")` in Python
- Document SAP-specific quirks in comments

### Pydantic Models and DTOs

- Place in `src/sapwebguimcp/models/`
- Use `Field(description=...)` for all fields
- Export from `__init__.py`

## Testing

### Integration Tests

Integration tests run against a real SAP system. They:

- Require SAP credentials in environment
- Are slow (~10-30s each)
- Should capture HTML snapshots for debugging

```python
@pytest.mark.anyio
async def test_my_feature(sap_mcp_client: ClientSession) -> None:
    await sap_mcp_client.call_tool("sap_login", {})
    # ... test logic
    await capture_html_snapshot(sap_mcp_client, "my_feature_result")
```

### Unit Tests

Unit tests use HTML snapshots from `unittests/testdata/html_snapshots/`.

```python
def test_my_parser():
    html = load_snapshot("bp_person_form_de.html")
    result = parse_something(html)
    assert result == expected
```

## Code Style

### Python

In the tox `dev` and `formatting` venv black and isort are installed.

- Use `black .` for formatting
- Use `isort .` for imports

linting and type checking should happen via tox (see above).

### Javascript and Markdown

Use Prettier for formatting.

```bash
npm run format
```

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/).
In the long commit message include what we learned (about SAP, about playwright, about MCP usage etc.).
Also include what assumptions we made and which prior assumptions turned out to be wrong.
Be honest.

### No Force Push

Do not force push unless absolutely necessary and discussed with the team.

### No amend

In the end, one pull request should contain one logical change.
We'll squash merge PRs when they're ready.
So it's ok to have commits that are not perfect.
You don't need to put any effort in rebases, amends or similar.

## Pull Requests

1. Create a feature branch: `feat/my-feature` or `fix/my-bug`
2. Write tests for new functionality
3. Ensure all tests pass: `tox -e unittests`
4. Ensure linting passes: `tox -e linting`, `tox -e type_check`
5. Create PR with clear description
