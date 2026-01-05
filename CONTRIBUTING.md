# Contributing to SAP Web GUI MCP Server

Thank you for contributing to this project! This guide covers coding standards and best practices.

## Development Setup

```bash
# Clone and install
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp
pip install -e ".[dev]"

# Run tests
tox -e dev
python -m pytest unittests/

# Run linting
tox -e linting
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

### Tool Description Best Practices

1. **First sentence**: What the tool does
2. **Return values**: What fields are returned and their purpose
3. **Usage hints**: How to use the returned data with other tools
4. **Cross-references**: Point to related tools (e.g., "For buttons use X instead")

### JavaScript Files

- Place JavaScript in `src/sapwebguimcp/js/`
- Use IIFE pattern: `() => { ... }`
- Load with `_load_js("filename.js")` in Python
- Document SAP-specific quirks in comments

### Pydantic Models

- Place in `src/sapwebguimcp/models/`
- Use `Field(description=...)` for all fields
- Export from `__init__.py`

## Testing

### Integration Tests

Integration tests run against a real SAP system. They:
- Require SAP credentials in environment
- Are slow (~20-30s each)
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

- Use `black` for formatting
- Use `isort` for imports
- Use `pylint` and `mypy` for linting
- Run `tox -e linting` before committing

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(tools): add sap_discover_buttons for button discovery
fix(login): handle session timeout gracefully
test(sm30): add integration test for button clicking
docs(readme): update installation instructions
refactor(models): extract ButtonInfo from DiscoveredButtons
```

## Pull Requests

1. Create a feature branch: `feat/my-feature` or `fix/my-bug`
2. Write tests for new functionality
3. Ensure all tests pass: `python -m pytest unittests/`
4. Ensure linting passes: `tox -e linting`
5. Create PR with clear description

## SAP-Specific Knowledge

### SAP Web GUI Button Structure

SAP buttons are `<div>` elements with:
- `role="button"` attribute
- Class containing `lsButton`
- Text in `title` attribute (NOT `textContent`)
- IDs like `M0:46:::10:18` that need CSS escaping

### SAP Web GUI Field Structure

SAP input fields use:
- `lsdata` attribute with JSON containing field metadata
- `title` attribute for field labels
- Labels linked via `lsdata["1"]` (target ID) and `lsdata["3"]` (label text)

### Common Pitfalls

1. **Button text**: Use `title` attribute, not `textContent`
2. **CSS selectors**: SAP IDs contain `:` - use `CSS.escape()` in JS
3. **Multiple fields same label**: Check for ambiguity (e.g., two "Postleitzahl" fields)
4. **Popups**: Check `blocking_popup` in tool responses
