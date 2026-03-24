# Architecture

This document explains how the SAP MCP Server is structured so you can navigate the codebase, understand the request flow, and add new features without reading every file first.

## SAP in 30 Seconds

SAP GUI is a desktop application for interacting with SAP ERP systems. Users navigate by entering **transaction codes** (tcodes like `SE16`, `VA01`, `SM37`) into the **OK-Code field** and pressing Enter. Each transaction shows a different screen with fields, tables, and buttons. The **status bar** at the bottom shows success/error messages after each action.

This MCP server automates that interaction — it enters tcodes, fills fields, reads tables, and returns structured results. It works through two backends: browser automation (WebGUI) or direct COM scripting (Desktop).

## Layers

```mermaid
graph TD
    Client["MCP Client<br/>(Claude Desktop, Claude Code)"]
    Server["FastMCP Server<br/>server.py"]
    Tools["Tools Layer<br/>tools/*.py — 30+ tool modules"]
    Manager["Backend Manager<br/>backend/manager.py"]
    Protocol["SapUiBackend Protocol<br/>backend/protocol.py"]
    WebGUI["WebGuiBackend<br/>backend/webgui/backend.py<br/>(Playwright + Chrome)"]
    Desktop["DesktopBackend<br/>backend/desktop/__init__.py<br/>(COM + sapsucker)"]
    Parsers["HTML Parsers<br/>backend/webgui/parsers/*.py"]
    Models["Result Models<br/>models/*.py — Pydantic"]

    Client -->|stdio/SSE| Server
    Server --> Tools
    Tools --> Manager
    Manager --> Protocol
    Protocol --> WebGUI
    Protocol --> Desktop
    WebGUI --> Parsers
    Tools --> Models
    WebGUI --> Models
    Desktop --> Models
```

### Layer Responsibilities

| Layer | Key Files | What It Does |
|-------|-----------|-------------|
| **Server** | `server.py` | Creates the FastMCP app, registers all tools/resources/prompts, manages lifecycle |
| **Tools** | `tools/sap_tools.py`, `tools/se16_tools.py`, ... | Define MCP tools the LLM can call. Each tool gets a backend via `get_backend()`, calls protocol methods, returns a Pydantic result model |
| **Backend Manager** | `backend/manager.py` | Singleton that creates/caches the right backend based on `BACKEND_TYPE`. Routes session IDs to backend instances |
| **Protocol** | `backend/protocol.py` | Structural typing protocol (`SapUiBackend`) with 5 sub-protocols: Navigation, Primitives, Inspection, Editor, Popup. Both backends implement this — tools never import a concrete backend |
| **WebGUI Backend** | `backend/webgui/backend.py`, `browser.py` | Implements protocol via Playwright page automation. Fills fields with JavaScript, reads screens with ARIA snapshots |
| **Desktop Backend** | `backend/desktop/__init__.py` | Implements protocol via COM scripting through [sapsucker](https://github.com/Hochfrequenz/sapsucker). Dispatches all COM calls to a dedicated thread (`_com_thread.py`) for apartment-threading safety |
| **Parsers** | `backend/webgui/parsers/*.py` | WebGUI-specific HTML → structured data extraction. One parser per transaction (e.g., `se16_parser.py`, `se24_parser.py`) |
| **Models** | `models/*.py` | Pydantic models for tool results, screen state, config. Shared by both backends. Never import from backend or tools |

## Request Flow

What happens when the LLM calls `sap_se16_query(table="MARA", max_hits=10)`:

```mermaid
sequenceDiagram
    participant LLM as MCP Client
    participant Tool as se16_tools.py
    participant Mgr as BackendManager
    participant BE as WebGUI/Desktop Backend
    participant SAP as SAP System

    LLM->>Tool: sap_se16_query(table="MARA")
    Tool->>Mgr: get_backend(session, agent_id)
    Mgr-->>Tool: backend instance
    Tool->>BE: enter_transaction("SE16N")
    BE->>SAP: Navigate to SE16N
    SAP-->>BE: Screen loaded
    Tool->>BE: fill_field("Table", "MARA")
    Tool->>BE: press_key("F8")
    BE->>SAP: Execute query
    SAP-->>BE: Results displayed
    Tool->>BE: read_table(max_rows=10)
    BE-->>Tool: TableData(headers, rows)
    Tool-->>LLM: SE16Result(table, columns, rows)
```

## File Organization

```
src/sapwebguimcp/
  server.py                    # FastMCP app, tool registration, lifecycle
  models/
    config.py                  # SapWebGuiSettings (all env vars)
    base.py                    # ToolResult base class, TCode type
    sap_results.py             # Shared results (LoginResult, ScreenInfo, ...)
    se16_models.py             # SE16-specific result models
    se24_models.py             # SE24-specific result models
    ...                        # One model file per transaction
  backend/
    protocol.py                # SapUiBackend protocol definition
    manager.py                 # Backend factory + session routing
    types.py                   # Shared type aliases
    webgui/
      backend.py               # WebGuiBackend implementation
      browser.py               # Chrome/Playwright lifecycle management
      chrome_finder.py          # Auto-detect Chrome installation
      js_helpers.py            # JavaScript helper loader
      js/*.js                  # Injected JS for field filling, screen reading
      parsers/                 # HTML → structured data (one per transaction)
    desktop/
      __init__.py              # DesktopBackend implementation
      _com_thread.py           # Dedicated COM thread (apartment-threading)
      _session_registry.py     # Multi-session tracking
      _element_finder.py       # COM tree traversal helpers
      _key_mapping.py          # Key name → SAP VKey mapping
      _landscape.py            # SAP Logon XML parsing
      _discovery.py            # Client/system discovery via SE16N
  tools/
    sap_tools.py               # Core tools: login, transaction, screen, keyboard, ...
    se16_tools.py              # SE16N data browser (query tables)
    se24_tools.py              # SE24 class lookup
    se24_edit_tools.py         # SE24 class source editing
    se37_tools.py              # SE37 function module lookup
    se37_edit_tools.py         # SE37 function module editing
    se38_edit_tools.py         # SE38 report editing
    ...                        # More transaction tools
    _backend_utils.py          # _is_desktop_backend() helper
    field_helpers.py           # Shared field-filling logic
    table_helpers.py           # Shared table-reading logic
    session_tools.py           # Multi-session management
    feedback_tools.py          # LLM feedback logging → GitHub issues
```

## How to Add a New Transaction Tool

Follow the SE16 pattern. For a new transaction `SE99`:

### 1. Create the result model

`src/sapwebguimcp/models/se99_models.py`:

```python
from pydantic import Field
from sapwebguimcp.models.base import ToolResult

class SE99Result(ToolResult):
    """Result from sap_se99_query tool."""
    data: list[dict[str, str]] = Field(default_factory=list)
    # Add transaction-specific fields
```

Export it from `models/__init__.py`.

### 2. Create the tool file

`src/sapwebguimcp/tools/se99_tools.py`:

```python
from fastmcp import FastMCP
from sapwebguimcp.backend.manager import get_backend
from sapwebguimcp.models.se99_models import SE99Result

def register_se99_tools(mcp: FastMCP) -> None:
    @mcp.tool(description="Query SE99 data")
    async def sap_se99_query(
        param: str,
        session: str | None = None,
        agent_id: str | None = None,
    ) -> SE99Result:
        backend = await get_backend(session=session, agent_id=agent_id, tool_name="sap_se99_query")

        # Navigate
        tx = await backend.enter_transaction("SE99")
        if not tx.success:
            return SE99Result.failure(f"Navigation failed: {tx.error}")

        # Fill fields, execute, read results
        await backend.fill_field("Field Label", param)
        await backend.press_key("F8")
        # ... parse results ...

        return SE99Result(data=[...])
```

### 3. Add desktop-specific path (if needed)

If the desktop backend needs different logic (e.g., COM table reading instead of HTML parsing), add a helper:

```python
from sapwebguimcp.tools._backend_utils import _is_desktop_backend

if _is_desktop_backend(backend):
    result = await _query_se99_desktop(backend, param)
else:
    result = await _query_se99_webgui(backend, param)
```

### 4. Add a WebGUI parser (if needed)

`src/sapwebguimcp/backend/webgui/parsers/se99_parser.py` — for extracting structured data from HTML/ARIA snapshots. Only needed for WebGUI; desktop reads data via COM.

### 5. Register the tool

In `server.py`, add:

```python
from sapwebguimcp.tools.se99_tools import register_se99_tools
# ... in create_mcp_server():
register_se99_tools(mcp)
```

### 6. Add tests

- `unittests/test_se99_models.py` — model validation (offline)
- `unittests/desktop/test_se99_integration.py` — desktop integration (needs SAP, auto-skipped)
- `unittests/webgui/test_se99_integration.py` — webgui integration (needs SAP, auto-skipped)

## Tests

### Categories

| Category | Location | Needs SAP? | How to run |
|----------|----------|-----------|------------|
| Unit tests | `unittests/test_*.py` | No | `tox -e unit_tests` |
| Desktop unit tests | `unittests/desktop/test_*_unit.py`, `test_desktop_backend.py` | No | `tox -e unit_tests` |
| WebGUI snapshot tests | `unittests/webgui/test_*_integration.py` (HTML-based) | No | `tox -e unit_tests` |
| Desktop integration | `unittests/desktop/test_*_integration.py` | Yes | `tox -e integration_tests` |
| WebGUI integration | `unittests/webgui/test_*_exploration.py` | Yes | `tox -e integration_tests` |

### Skip Mechanism

Integration tests auto-skip via markers defined in `unittests/desktop/conftest.py`:

- `skip_not_sap` — skips if the machine hostname is not in the allowed list (`is_sap_integration_test_machine()` in `unittests/conftest.py`)
- `skip_no_creds` — skips if SAP credentials are not configured in `.env`

Desktop test files include `pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")` to skip on Linux/macOS CI.

### Running Tests

```bash
tox -e unit_tests          # Fast, no SAP needed (~200 tests)
tox -e integration_tests   # Needs SAP connection
tox -e tests               # Both (integration auto-skips without SAP)
tox -e linting             # pylint
tox -e type_check          # mypy --strict
tox -e formatting          # black + isort check
```

## Configuration

All settings are in `src/sapwebguimcp/models/config.py` and loaded from environment variables or `.env` files.

### Required

| Variable | Description |
|----------|-------------|
| `BACKEND_TYPE` | `desktop` or `webgui` (default: `webgui`) |
| `SAP_USER` | SAP login username |
| `SAP_PASSWORD` | SAP login password |
| `SAP_MANDANT` | SAP client number (e.g., `100`) |

**Desktop-only:** `SAP_CONNECTION_NAME` — SAP Logon entry name (bold text in SAP Logon list)

**WebGUI-only:** `SAP_URL` — Web GUI URL (e.g., `https://server/sap/bc/gui/sap/its/webgui`)

### Optional

| Group | Variables | Purpose |
|-------|-----------|---------|
| **Language** | `SAP_LANGUAGE` | `DE` or `EN` (default: `DE`) |
| **Multi-system** | `SAP_CREDENTIALS` | JSON mapping connection names to credentials (see README) |
| **Browser** | `BROWSER_MODE`, `CDP_URL`, `CHROME_PATH`, `CHROME_USER_DATA_DIR`, `BROWSER_HEADLESS` | Chrome/Playwright configuration |
| **COM timing** | `COM_MIN_INTERVAL_MS` | Minimum ms between COM calls (desktop, prevents overload) |
| **GitHub** | `GITHUB_PAT`, `GITHUB_REPO`, `ABAPGIT_PAT` | Feedback issue creation, abapGit operations |
| **Logging** | `PAPERTRAIL_HOST`, `PAPERTRAIL_PORT` | Remote syslog (optional) |

See `.env.example` for a complete template with descriptions.
