# JavaScript Extraction Design

## Overview

Extract embedded JavaScript from Python source code (`sap_tools.py`) into dedicated `.js` files for better maintainability, testability, and separation of concerns.

## Problem

Currently, `sap_tools.py` contains 7 significant JavaScript blocks (ranging from 15-90 lines each) embedded as Python string literals. This makes the code harder to:

- Read and maintain (no JS syntax highlighting in Python strings)
- Test independently
- Reuse across different tools

## Solution

Create a `src/sapguimcp/js/` directory containing dedicated JavaScript files, loaded at runtime using `importlib.resources`.

## Structure

```
src/sapguimcp/
├── js/
│   ├── __init__.py              # Makes it a package for importlib.resources
│   ├── set_language_field.js    # sap_login language setting
│   ├── set_okcode_field.js      # sap_transaction OK-Code setting
│   ├── extract_screen_text.js   # sap_get_screen_text
│   ├── extract_table_data.js    # sap_read_table
│   ├── extract_status_bar.js    # sap_read_status_bar
│   ├── extract_screen_info.js   # sap_get_screen_info
│   └── discover_fields.js       # sap_discover_fields
└── tools/
    └── sap_tools.py             # Modified to load JS from files
```

## JS File Format

Each JS file is a self-contained function expression compatible with Playwright's `page.evaluate()`.

### With Parameters

```javascript
// extract_table_data.js
(params) => {
    const { startRow, endRow, maxRows } = params;
    // ... implementation
    return { headers, rows, totalRows, ... };
}
```

### Without Parameters

```javascript
// extract_screen_text.js
() => {
    const result = { title: document.title, ... };
    // ... implementation
    return result;
}
```

## Python Integration

Helper function to load JS files:

```python
from importlib import resources

def _load_js(filename: str) -> str:
    """Load a JavaScript file from the sapguimcp.js package."""
    return resources.files("sapguimcp.js").joinpath(filename).read_text(encoding="utf-8")
```

Usage:

```python
# Without params
screen_text = await page.evaluate(_load_js("extract_screen_text.js"))

# With params
result = await page.evaluate(
    _load_js("extract_table_data.js"),
    {"startRow": start_row, "endRow": end_row, "maxRows": max_rows}
)
```

## File Mapping

| JS File                  | Python Function       | Has Params | Param Names                     |
| ------------------------ | --------------------- | ---------- | ------------------------------- |
| `set_language_field.js`  | `sap_login`           | Yes        | `language`                      |
| `set_okcode_field.js`    | `sap_transaction`     | Yes        | `transactionInput`              |
| `extract_screen_text.js` | `sap_get_screen_text` | No         | -                               |
| `extract_table_data.js`  | `sap_read_table`      | Yes        | `startRow`, `endRow`, `maxRows` |
| `extract_status_bar.js`  | `sap_read_status_bar` | No         | -                               |
| `extract_screen_info.js` | `sap_get_screen_info` | No         | -                               |
| `discover_fields.js`     | `sap_discover_fields` | No         | -                               |

## Not Extracted

- `browser_tools.py`: Contains only trivial single-expression JS (`el => el.outerHTML`, `el => el.innerHTML`) - not worth separate files.

## Packaging

Files in `src/sapguimcp/js/` are automatically included in the package since `pyproject.toml` has `only-include = ["src"]`. The `__init__.py` ensures the directory is treated as a package for `importlib.resources`.

## Testing

Existing integration tests (`test_sap_integration.py`) validate the JS works correctly. No new tests needed - if JS extraction breaks anything, integration tests will catch it.
