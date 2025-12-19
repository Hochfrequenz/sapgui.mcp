# Models

This directory contains data models and core infrastructure for the SAP Web GUI MCP Server.

## Module Structure

```
models/
├── __init__.py      # Package exports
├── config.py        # Configuration settings (pydantic-settings)
├── browser.py       # Browser manager for Playwright sessions
└── README.md        # This file
```

## Configuration (`config.py`)

The `SapWebGuiSettings` class uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) to
load configuration from environment variables.

### Available Settings

| Environment Variable | Type   | Default                   | Description                              |
|----------------------|--------|---------------------------|------------------------------------------|
| `SAP_URL`            | str    | `""`                      | Default SAP Web GUI URL                  |
| `SAP_USER`           | str    | `""`                      | SAP username for automatic login         |
| `SAP_PASSWORD`       | str    | `""`                      | SAP password for automatic login         |
| `SAP_MANDANT`        | str    | `""`                      | SAP client/mandant (3-digit, e.g., "100")|
| `SAP_LANGUAGE`       | enum   | `"EN"`                    | SAP login language (`"DE"` or `"EN"`)    |
| `BROWSER_MODE`       | enum   | `"launch"`                | `"launch"` or `"connect"`                |
| `BROWSER_TYPE`       | enum   | `"chromium"`              | `"chromium"`, `"firefox"`, or `"webkit"` |
| `BROWSER_HEADLESS`   | bool   | `false`                   | Run browser without GUI                  |
| `CDP_URL`            | str    | `"http://localhost:9222"` | CDP URL for connect mode                 |

### Usage

```python
from sapwebguimcp.models import get_settings

settings = get_settings()
print(settings.sap_url)
print(settings.browser_mode)
```

### Adding New Settings

1. Add a new field to `SapWebGuiSettings`:

```python
class SapWebGuiSettings(BaseSettings):
    # ... existing fields ...

    my_new_setting: str = Field(
        default="default_value",
        description="Description of the setting",
        json_schema_extra={"env": "MY_NEW_SETTING"},
    )
```

2. Update the `__all__` export if adding new public classes.

## Browser Manager (`browser.py`)

The `BrowserManager` class manages persistent Playwright browser sessions.

### Key Features

- **Singleton pattern**: One browser instance shared across all tool calls
- **Named pages**: Multiple pages can be managed by name
- **Persistent sessions**: Pages survive between tool calls (login once, use many times)
- **Connect mode**: Can connect to an existing browser (for VPN/Citrix setups)

### Usage

```python
from sapwebguimcp.models import get_browser_manager

manager = await get_browser_manager()
page = await manager.get_current_page()
await page.goto("https://example.com")
```

### Adding Browser Features

To add new browser capabilities:

1. Add methods to `BrowserManager` class
2. Export in `__init__.py` if needed
3. Add tests in `unittests/test_browser.py`

Example - adding a method to take screenshots:

```python
async def take_screenshot(self, path: str) -> bytes:
    """Take a screenshot of the current page."""
    page = await self.get_current_page()
    return await page.screenshot(path=path)
```

## Type Hints

All models use proper type hints for mypy strict mode. When adding new models:

- Use `Optional[T]` for nullable types
- Use `list[T]` instead of `List[T]` (Python 3.9+)
- Add `__all__` exports for public API
- Run `tox -e type_check` to verify type correctness
