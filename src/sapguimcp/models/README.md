# Models

This directory contains data models and core infrastructure for the SAP GUI MCP Server.

## Module Structure

```
models/
├── __init__.py              # Package exports
├── config.py                # Configuration settings (pydantic-settings)
├── base.py                  # ToolResult base class, TCode type, PopupInfo
├── sap_results.py           # Core SAP result models (StatusBarInfo, TableData, etc.)
├── se16_models.py           # SE16-specific result models
├── ...                      # One model file per transaction
└── README.md                # This file
```

## Configuration (`config.py`)

The `SapGuiSettings` class uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) to
load configuration from environment variables.

### Available Settings

| Environment Variable  | Type | Default | Description                                                   |
| --------------------- | ---- | ------- | ------------------------------------------------------------- |
| `OUTPUT_DIR`          | str  | `""`    | Directory that `output_file` tool arguments are confined to   |
| `SCRIPT_ROOTS`        | str  | `""`    | Allowed root directories for `sap_run_script`'s `script_path` |
| `COM_MIN_INTERVAL_MS` | int  | `100`   | Minimum ms between COM calls (prevents overload)              |
| `GITHUB_PAT`          | str  | `""`    | GitHub token for `log_feedback` and abapGit                   |
| `LOG_LEVEL`           | enum | `INFO`  | `DEBUG`, `INFO`, `WARNING` or `ERROR`                         |

The table lists a selection. See `config.py` and the README's environment variable reference for all settings.

SAP credentials and the login language (user, password, client, language) are loaded from `~/.config/sap-mcp/systems.json`
(or the path set via `SAP_CONFIG_FILE` env var). See the [sap-mcp-config](https://github.com/Hochfrequenz/sap-mcp-config) package.

### Usage

```python
from sapguimcp.models import get_settings

settings = get_settings()
print(settings.output_dir)
print(settings.log_level)
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

## Backend (`backend/`)

Tools get the backend via `get_backend()` instead of touching COM directly. It returns the
`DesktopBackend`, which drives SAP GUI for Windows through COM scripting (see `ARCHITECTURE.md`).

### Usage

```python
from sapguimcp.backend.manager import get_backend

backend = await get_backend(session=session, agent_id=agent_id, tool_name="my_tool")
await backend.enter_transaction("SE16")
snapshot = await backend.get_snapshot()
```

### Architecture

- **`backend/desktop/__init__.py`** — `DesktopBackend` (SAP GUI COM scripting implementation)
- **`backend/manager.py`** — `BackendManager` singleton, `get_backend()` entry point

## Type Hints

All models use proper type hints for mypy strict mode. When adding new models:

- Use `Optional[T]` for nullable types
- Use `list[T]` instead of `List[T]` (Python 3.9+)
- Add `__all__` exports for public API
- Run `uv run --group type_check mypy --show-error-codes src/sapguimcp --strict` to verify type correctness
