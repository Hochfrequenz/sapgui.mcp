# Contributing to SAP Web GUI MCP Server

Thank you for contributing to this project! This guide covers development setup, testing, and coding standards.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Hochfrequenz/sapwebgui.mcp.git
cd sapwebgui.mcp

# Create development environment
tox -e dev

# Activate the environment
source .tox/dev/bin/activate  # Linux/macOS
# or
.tox\dev\Scripts\activate  # Windows

# Install Playwright browsers
playwright install chromium
```

## Running Tests

This project uses [tox](https://tox.wiki/) to run all tests and checks. The test suite includes:

- **Unit tests**: Offline tests using HTML snapshots (no SAP required)
- **Integration tests**: Tests against real SAP Web GUI (auto-skipped on non-SAP machines)

### Tox Environments

```bash
# Run all tests (integration tests auto-skip if SAP not accessible)
tox -e tests

# Run only unit tests (fast, no SAP needed)
tox -e unit_tests

# Run only SAP integration tests (requires SAP access)
tox -e integration_tests

# Run all checks (tests, linting, formatting, type checking)
tox
```

Language and credentials are loaded from your `.env` file.

**Other tox environments:**

```bash
tox -e coverage     # Run tests with coverage report
tox -e linting      # Run pylint
tox -e formatting   # Check black/isort formatting
tox -e type_check   # Run mypy type checking
tox -e spell_check  # Run codespell
```

### Running Tests in PyCharm

You can run tests directly in PyCharm. Settings are loaded from your `.env` file automatically.

1. **Unit tests**: Right-click `unittests/test_selectors.py` → Run
2. **Integration tests**: Right-click `unittests/test_sap_integration.py` → Run

To change language, edit `SAP_LANGUAGE` in your `.env` file.

**Tox vs PyCharm**: Tox creates isolated virtualenvs (good for CI), PyCharm uses your current interpreter (faster for development).

### HTML Snapshot Testing

We use HTML snapshots captured from real SAP Web GUI sessions to test CSS selectors offline. This approach:

1. **Captures real HTML** during integration tests (when SAP is available)
2. **Validates selectors** against snapshots in fast unit tests (no SAP needed)
3. **Supports multiple languages** (snapshots named `*_en.html`, `*_de.html`)

To capture new snapshots, set `SAP_LANGUAGE` in your `.env` file and run integration tests:

```bash
tox -e integration_tests   # Captures snapshots in configured language
tox -e unit_tests          # Run offline selector tests (no SAP needed)
```

Snapshots are stored in `unittests/testdata/html_snapshots/`.

#### Why Not Syrupy?

We considered [syrupy](https://github.com/tophat/syrupy) (a pytest snapshot testing library) but chose a simpler approach because:

1. **SAP HTML is huge** (~300KB per page) - syrupy's diff output would be unreadable
2. **We don't compare full HTML** - we only validate that specific selectors find elements
3. **Selector validation is the goal** - not detecting HTML changes
4. **BeautifulSoup is sufficient** - we parse HTML and test CSS selectors, no need for snapshot diffing
5. **Multi-language support** - we capture EN/DE variants; syrupy would create separate snapshot dirs

Our approach: capture HTML once, then write focused assertions about selector behavior. If SAP's HTML structure changes, the selector tests fail with clear messages about which selector broke.

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

This project uses:

- [Black](https://github.com/psf/black) for code formatting
- [isort](https://pycqa.github.io/isort/) for import sorting
- [pylint](https://pylint.org/) for linting
- [mypy](https://mypy.readthedocs.io/) for type checking
- [codespell](https://github.com/codespell-project/codespell) for spell checking

### Python

In the tox `dev` and `formatting` venv black and isort are installed.

```bash
black .   # Format code
isort .   # Sort imports
```

Linting and type checking should happen via tox:

```bash
tox -e linting
tox -e type_check
```

### JavaScript and Markdown

Use Prettier for formatting:

```bash
npm run format
```

## MCP Tool Guidelines

### Tool and Parameter Descriptions (Important!)

FastMCP uses **two sources** to generate the MCP tool schema:

1. **Tool description** → from `@mcp.tool(description=...)` decorator
2. **Parameter descriptions** → from the **Args section in the docstring**

Both are sent to the AI client. Without the Args section, the LLM doesn't know what parameters exist!

```python
# CORRECT - description in decorator, Args in docstring
@mcp.tool(
    description=(
        "Discover clickable buttons on the current SAP screen. "
        "Returns buttons with label, selector (for browser_click), shortcut. "
        "Use the 'selector' field with browser_click to click buttons reliably. "
        "For input fields use sap_discover_fields instead."
    )
)
async def sap_discover_buttons(session: str | None = None) -> DiscoveredButtons:
    """Discover all clickable buttons on the current SAP screen.

    Args:
        session: Session ID (e.g., "s1", "s2"). None uses primary session.
    """
    ...

# WRONG - missing Args section (parameter won't have description in schema)
@mcp.tool(description="Discover buttons")
async def sap_discover_buttons(session: str | None = None) -> DiscoveredButtons:
    """Discover all clickable buttons on the current SAP screen."""
    ...
```

**Key points:**
- Put **when/why to use the tool** in the `description` decorator
- Put **what each parameter means** in the docstring Args section
- FastMCP parses the Args section to generate parameter descriptions in the MCP schema

### JavaScript Files

- Place JavaScript in `src/sapwebguimcp/js/`
- Use IIFE pattern: `() => { ... }`
- Load with `_load_js("filename.js")` in Python
- Document SAP-specific quirks in comments

### Pydantic Models and DTOs

- Place in `src/sapwebguimcp/models/`
- Use `Field(description=...)` for all fields
- Export from `__init__.py`

## Python Specific Guidelines

Use strict typing:

- Pydantic models for data structures instead of plain dicts, tuples or dataclasses
    - Pydantic model fields should have descriptions
- Proper type hints for function parameters and return types

### MCP

Read the docs of [FastMCP](https://gofastmcp.com/servers/server) before you google or guess.

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/).
In the long commit message include what we learned (about SAP, about Playwright, about MCP usage etc.).
Also include what assumptions we made and which prior assumptions turned out to be wrong.
Be honest.

### No Force Push

Do not force push unless absolutely necessary and discussed with the team.

### No Amend

In the end, one pull request should contain one logical change.
We'll squash merge PRs when they're ready.
So it's ok to have commits that are not perfect.
You don't need to put any effort in rebases, amends or similar.

## Pull Requests

1. Create a feature branch: `feat/my-feature` or `fix/my-bug`
2. Write tests for new functionality
3. Ensure all tests pass: `tox -e unit_tests`
4. Ensure linting passes: `tox -e linting`, `tox -e type_check`
5. Create PR with clear description

## Extending the Server

### Adding New Tools

See [src/sapwebguimcp/tools/README.md](src/sapwebguimcp/tools/README.md) for detailed instructions on creating new tools.

### Adding New Models

See [src/sapwebguimcp/models/README.md](src/sapwebguimcp/models/README.md) for information about the data models.

### Creating Skills

See [src/sapwebguimcp/skills/README.md](src/sapwebguimcp/skills/README.md) for how to create reusable workflows.
