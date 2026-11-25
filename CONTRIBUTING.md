# Contributing to SAP MCP Server

Thank you for contributing to this project! This guide covers development setup, testing, and coding standards.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture overview — layers, request flow diagrams, file organization, and how to add new transaction tools.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Hochfrequenz/sapgui.mcp.git
cd sapgui.mcp

# Install uv first: https://docs.astral.sh/uv/getting-started/installation/
# Then create the development environment
uv sync --group dev

# Activate the environment
.venv\Scripts\activate
```

`uv sync --group dev` installs everything needed to run the unit tests (`dev` includes the `tests` group and the runtime dependencies such as `fastmcp`). If a bare `pytest` or `import mcp` fails with a missing module, you are most likely in a stale or different virtual environment: run commands through `uv run ...` (e.g. `uv run pytest --version`) instead of relying on an activated older venv.

### SAP Test System Setup

To run integration tests, you need a configured SAP system. See **[docs/SAP_TEST_PREREQUISITES.md](docs/SAP_TEST_PREREQUISITES.md)** for:

- SAP GUI Scripting configuration (RZ11 + client settings)
- Required test objects (report, class, function module)
- `.env` file configuration

## Running Tests

This server drives SAP GUI for Windows, so integration tests need Windows with SAP GUI. The unit tests run on any OS, but the desktop unit tests only run on Windows. This project uses [uv](https://docs.astral.sh/uv/) to run all tests and checks. The test suite includes:

- **Unit tests**: Offline tests using mocked COM (no SAP required)
- **Desktop integration tests**: Tests against SAP GUI via COM (auto-skipped without SAP credentials)

### Commands

```bash
# Run all tests (integration tests auto-skip if SAP not accessible)
uv run --group tests python -m pytest

# Run only unit tests (fast, no SAP needed)
uv run --group tests python -m pytest unittests/ -m "not integration"

# Run only SAP integration tests (requires SAP access)
uv run --group tests python -m pytest unittests/ -m integration
```

SAP credentials are loaded from your `systems.json` (see [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config)). The logon language of the tests comes from `SAP_LANGUAGE` in your `.env` file.

**Other checks:**

```bash
uv run --group coverage coverage run -m pytest  # Run tests with coverage report
uv run --group linting ruff check .             # Run ruff (lint)
uv run --group linting ruff format --check .     # Check formatting
uv run --group linting ruff check --select I .   # Check import order
uv run --group type_check mypy --show-error-codes src/sapguimcp --strict  # Run mypy type checking
uv run --group spell_check codespell --ignore-words=domain-specific-terms.txt src  # Run codespell
```

### Running Tests in PyCharm

You can run tests directly in PyCharm. Credentials come from your `systems.json`; settings are loaded from your `.env` file automatically.

1. **Unit tests**: Right-click `unittests/desktop/test_element_finder.py` → Run
2. **Integration tests**: Right-click any `unittests/desktop/test_*_integration.py` file → Run

To change language, edit `SAP_LANGUAGE` in your `.env` file.

**uv vs PyCharm**: uv creates an isolated virtualenv (good for CI), PyCharm uses your current interpreter (faster for development).

### Desktop Integration Tests

Desktop integration tests run against SAP GUI via COM. They:

- Live in `unittests/desktop/`
- Use the shared `backend` fixture from `conftest.py` (logs in once per module)
- Auto-skip on non-Windows or when SAP credentials are missing
- Are marked `integration` automatically (any test requesting `backend` or `sap_mcp_client`), so `-m "not integration"` excludes them and `-m integration` selects only them
- Test object names are centralized in `conftest.py` (`TEST_REPORT`, `TEST_CLASS`, etc.)
- Open visible SAP GUI windows by default. Set `SAPGUI_TEST_MINIMIZED=1` to minimize each window right after a test opens it, so a live run can go on in the background while you work. A new window can still show for a few seconds before it is minimized.

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

Unit tests use mocked COM objects. No SAP connection needed.

```python
# Mocked COM tests
def test_my_com_feature():
    session = MagicMock()
    result = my_function(session)
    assert result == expected
```

## Code Style

This project uses:

- [ruff](https://docs.astral.sh/ruff/) for linting, import sorting and code formatting (replaces black, isort and pylint) — when adding per-file ignores keep the human-readable rule **name** as a trailing comment (`# too-many-arguments`), not just the code
- [mypy](https://mypy.readthedocs.io/) for type checking
- [codespell](https://github.com/codespell-project/codespell) for spell checking

### Python

The `dev` and `linting` dependency groups install ruff.

```bash
uv run --group linting ruff format .   # Format code
uv run --group linting ruff check --fix .   # Lint and auto-fix (incl. import sorting)
```

Linting and type checking:

```bash
uv run --group linting ruff check .
uv run --group type_check mypy --show-error-codes src/sapguimcp --strict
```

### Markdown

Use Prettier for formatting:

```bash
npm run format
```

### SAP UI Texts and Languages

SAP screen texts differ per logon language, so they live only in the language packs under
`src/sapguimcp/lang/`. Never write a button label, title, status text or column header as a literal
in tool or backend code: read it from `lang.current()` (see
[`ARCHITECTURE.md`](ARCHITECTURE.md#sap-ui-texts-and-language-packs) and the
[design spec](docs/superpowers/specs/2026-11-10-language-packs-design.md)).

`unittests/test_no_ui_literals.py` enforces this. If it flags a literal, move the text into the
packs (plus a `SOURCES` entry in `lang/sources.py`), or, when the literal is code or the server's
own message, add `# lang-ok: <reason>` on the flagged line. Never add
to `unittests/lang_baseline.json`; it holds only `tools/breakpoint_tools.py` (#1025).

To add a new login language: create `lang/<xx>.py` modelled on `en.py`, register it in
`lang/__init__.py`, fill the test pack in `unittests/testdata/lang_test.py`, verify it with
`uv run python scripts/harvest_lang_texts.py <XX> --verify`, and run
`uv run --group tests pytest unittests/lang unittests/test_no_ui_literals.py` (the pseudo-locale test
included). The full guide, with the pitfalls found while migrating DE and EN, is
[`src/sapguimcp/lang/ADDING_A_LANGUAGE.md`](src/sapguimcp/lang/ADDING_A_LANGUAGE.md).

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
        "they're faster than clicking. "
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
In the long commit message include what we learned (about SAP, about SAP GUI scripting, about MCP usage etc.).
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
3. Ensure all tests pass: `uv run --group tests python -m pytest unittests/ -m "not integration"`
4. Ensure linting passes: `uv run --group linting ruff check .`, `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict`
5. Create PR with clear description

## Extending the Server

### Adding New Tools

See [src/sapguimcp/tools/README.md](src/sapguimcp/tools/README.md) for detailed instructions on creating new tools.

### Adding New Models

See [src/sapguimcp/models/README.md](src/sapguimcp/models/README.md) for information about the data models.

### Creating Skills

See [src/sapguimcp/skills/README.md](src/sapguimcp/skills/README.md) for how to create reusable workflows.
