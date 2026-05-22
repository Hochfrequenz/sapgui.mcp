# Models

This directory contains data models and core infrastructure for the SAP Web GUI MCP Server.

## Module Structure

```
models/
├── __init__.py              # Package exports
├── config.py                # Configuration settings (pydantic-settings)
├── browser.py               # Browser manager for Playwright sessions
├── sap_results.py           # Core SAP result models (StatusBarInfo, TableData, etc.)
├── screen_state.py          # Selection screen state models
├── quick_report_models.py   # QuickReportResult, ScreenClassification
└── README.md                # This file
```

## Configuration (`config.py`)

The `SapGuiSettings` class uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) to
load configuration from environment variables.

### Available Settings

| Environment Variable | Type | Default                   | Description                               |
| -------------------- | ---- | ------------------------- | ----------------------------------------- |
| `SAP_URL`            | str  | `""`                      | Default SAP Web GUI URL                   |
| `SAP_LANGUAGE`       | enum | `"EN"`                    | SAP login language (`"DE"` or `"EN"`)     |
| `BROWSER_MODE`       | enum | `"connect"`               | `"connect"` or `"launch"`                 |
| `BROWSER_TYPE`       | enum | `"chromium"`              | `"chromium"`, `"firefox"`, or `"webkit"`  |
| `BROWSER_HEADLESS`   | bool | `false`                   | Run browser without GUI                   |
| `CDP_URL`            | str  | `"http://localhost:9222"` | CDP URL for connect mode                  |

SAP credentials (user, password, mandant) are loaded from `~/.config/sap-mcp/systems.json`
(or the path set via `SAP_CONFIG_FILE` env var). See the [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) package.

### Usage

```python
from sapguimcp.models import get_settings

settings = get_settings()
print(settings.sap_url)
print(settings.browser_mode)
```

### Adding New Settings

1. Add a new field to `SapGuiSettings`:

```python
class SapGuiSettings(BaseSettings):
    # ... existing fields ...

    my_new_setting: str = Field(
        default="default_value",
        description="Description of the setting",
        json_schema_extra={"env": "MY_NEW_SETTING"},
    )
```

2. Update the `__all__` export if adding new public classes.

## Backend Abstraction (`backend/`)

SAP UI operations are abstracted behind the `SapUiBackend` protocol. Tools access the
backend via `get_backend()` instead of touching Playwright directly.

### Usage

```python
from sapguimcp.backend.manager import get_backend

backend = await get_backend(session=session, agent_id=agent_id, tool_name="my_tool")
await backend.enter_transaction("SE16")
snapshot = await backend.get_snapshot()
```

### Architecture

- **`backend/protocol.py`** — `SapUiBackend` protocol (5 sub-protocols)
- **`backend/webgui/backend.py`** — `WebGuiBackend` (Playwright-based implementation)
- **`backend/manager.py`** — `BackendManager` singleton, `get_backend()` entry point
- **`backend/webgui/browser.py`** — `BrowserManager` for low-level browser lifecycle

## Type Hints

All models use proper type hints for mypy strict mode. When adding new models:

- Use `Optional[T]` for nullable types
- Use `list[T]` instead of `List[T]` (Python 3.9+)
- Add `__all__` exports for public API
- Run `tox -e type_check` to verify type correctness
