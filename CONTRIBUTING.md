# Contributing to SAP MCP Server

Thank you for contributing to this project! This guide covers development setup, testing, and coding standards.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture overview — layers, request flow diagrams, file organization, and how to add new transaction tools.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Hochfrequenz/sapgui.mcp.git
cd sapgui.mcp

# Create development environment (installs uv; see https://docs.astral.sh/uv/)
uv sync --group dev

# Activate the environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows

# Install Playwright browsers (WebGUI backend only)
uv run playwright install chromium
```

### SAP Test System Setup

To run integration tests, you need a configured SAP system. See **[docs/SAP_TEST_PREREQUISITES.md](docs/SAP_TEST_PREREQUISITES.md)** for:

- SAP GUI Scripting configuration (RZ11 + client settings)
- Required test objects (report, class, function module)
- `.env` file configuration

## Running Tests

This project uses [uv](https://docs.astral.sh/uv/) to run all tests and checks. The test suite includes:

- **Unit tests**: Offline tests using HTML snapshots and mocked COM (no SAP required)
- **WebGUI integration tests**: Tests against real SAP Web GUI (auto-skipped on non-SAP machines)
- **Desktop integration tests**: Tests against SAP GUI via COM (auto-skipped without SAP credentials)

### Commands

```bash
# Run all tests (integration tests auto-skip if SAP not accessible)
uv run --group tests python -m pytest

# Run only unit tests (fast, no SAP needed)
uv run --group tests python -m pytest unittests/ -k "not integration and not exploration"

# Run only SAP integration tests (requires SAP access)
uv run --group tests python -m pytest unittests/ -k integration
```

Language and credentials are loaded from your `.env` file.

**Other checks:**

```bash
uv run --group coverage coverage run -m pytest  # Run tests with coverage report
uv run --group linting pylint sapguimcp         # Run pylint
uv run --group formatting black --check src/sapguimcp unittests  # Check black formatting
uv run --group formatting isort --check src/sapguimcp unittests  # Check isort import order
uv run --group type_check mypy --show-error-codes src/sapguimcp --strict  # Run mypy type checking
uv run --group spell_check codespell --ignore-words=domain-specific-terms.txt src  # Run codespell
```

### Running Tests in PyCharm

You can run tests directly in PyCharm. Settings are loaded from your `.env` file automatically.

1. **Unit tests**: Right-click `unittests/webgui/test_selectors.py` → Run
2. **Integration tests**: Right-click any `unittests/webgui/test_*_integration.py` file → Run

To change language, edit `SAP_LANGUAGE` in your `.env` file.

**uv vs PyCharm**: uv creates an isolated virtualenv (good for CI), PyCharm uses your current interpreter (faster for development).

### HTML Snapshot Testing

We use HTML snapshots captured from real SAP Web GUI sessions to test CSS selectors offline. This approach:

1. **Captures real HTML** during integration tests (when SAP is available)
2. **Validates selectors** against snapshots in fast unit tests (no SAP needed)
3. **Supports multiple languages** (snapshots named `*_en.html`, `*_de.html`)

To capture new snapshots, set `SAP_LANGUAGE` in your `.env` file and run integration tests:

```bash
uv run --group tests python -m pytest unittests/ -k integration   # Captures snapshots in configured language
uv run --group tests python -m pytest unittests/ -k "not integration and not exploration"  # Run offline selector tests (no SAP needed)
```

Snapshots are stored in `unittests/webgui/testdata/html_snapshots/`.

#### Why Not Syrupy?

We considered [syrupy](https://github.com/tophat/syrupy) (a pytest snapshot testing library) but chose a simpler approach because:

1. **SAP HTML is huge** (~300KB per page) - syrupy's diff output would be unreadable
2. **We don't compare full HTML** - we only validate that specific selectors find elements
3. **Selector validation is the goal** - not detecting HTML changes
4. **BeautifulSoup is sufficient** - we parse HTML and test CSS selectors, no need for snapshot diffing
5. **Multi-language support** - we capture EN/DE variants; syrupy would create separate snapshot dirs

Our approach: capture HTML once, then write focused assertions about selector behavior. If SAP's HTML structure changes, the selector tests fail with clear messages about which selector broke.

### WebGUI Integration Tests

WebGUI integration tests run against SAP Web GUI in a browser. They:

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

### Desktop Integration Tests

Desktop integration tests run against SAP GUI via COM. They:

- Live in `unittests/desktop/`
- Use the shared `backend` fixture from `conftest.py` (logs in once per module)
- Auto-skip on non-Windows or when SAP credentials are missing
- Test object names are centralized in `conftest.py` (`TEST_REPORT`, `TEST_CLASS`, etc.)

```python
from unittests.desktop.conftest import go_home, skip_no_sap

@skip_no_sap
@pytest.mark.anyio
async def test_my_desktop_feature(backend):
    await backend.enter_transaction("SE16")
    # ... test logic
    await go_home(backend)  # Always return to Easy Access
```

See [docs/SAP_TEST_PREREQUISITES.md](docs/SAP_TEST_PREREQUISITES.md) for system setup.

### Unit Tests

Unit tests use HTML snapshots (WebGUI) or mocked COM objects (Desktop). No SAP connection needed.

```python
# WebGUI: HTML snapshot tests
def test_my_parser():
    html = load_snapshot("bp_person_form_de.html")
    result = parse_something(html)
    assert result == expected

# Desktop: mocked COM tests
def test_my_com_feature():
    session = MagicMock()
    result = my_function(session)
    assert result == expected
```

## Code Style

This project uses:

- [Black](https://github.com/psf/black) for code formatting
- [isort](https://pycqa.github.io/isort/) for import sorting
- [pylint](https://pylint.org/) for linting — when disabling rules use **speaking names** (`# pylint: disable=too-many-lines`), not codes (`# pylint: disable=C0302`)
- [mypy](https://mypy.readthedocs.io/) for type checking
- [codespell](https://github.com/codespell-project/codespell) for spell checking

### Python

The `dev` and `formatting` dependency groups install black and isort.

```bash
uv run --group formatting black .   # Format code
uv run --group formatting isort .   # Sort imports
```

Linting and type checking:

```bash
uv run --group linting pylint sapguimcp
uv run --group type_check mypy --show-error-codes src/sapguimcp --strict
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
        "Prefer keyboard shortcuts (sap_press_key) when available — "
        "they're faster and work on all backends. "
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

- Place JavaScript in `src/sapguimcp/js/`
- Use IIFE pattern: `() => { ... }`
- Load with `_load_js("filename.js")` in Python
- Document SAP-specific quirks in comments

### Pydantic Models and DTOs

- Place in `src/sapguimcp/models/`
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
3. Ensure all tests pass: `uv run --group tests python -m pytest unittests/ -k "not integration and not exploration"`
4. Ensure linting passes: `uv run --group linting pylint sapguimcp`, `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`
5. Create PR with clear description

## Extending the Server

### Adding New Tools

See [src/sapguimcp/tools/README.md](src/sapguimcp/tools/README.md) for detailed instructions on creating new tools.

### Adding New Models

See [src/sapguimcp/models/README.md](src/sapguimcp/models/README.md) for information about the data models.

### Creating Skills

See [src/sapguimcp/skills/README.md](src/sapguimcp/skills/README.md) for how to create reusable workflows.
