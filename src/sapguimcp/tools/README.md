# Tools

This directory contains MCP tool definitions for SAP Web GUI automation.

## Module Structure

```
tools/
├── __init__.py            # Package exports (register functions)
├── sap_tools.py           # High-level SAP tools
├── browser_tools.py       # Low-level browser escape hatches
├── se11_tools.py          # SE11 ABAP Dictionary lookup
├── se16_tools.py          # SE16N table data query
├── se24_tools.py          # SE24 Class Builder lookup
├── se37_tools.py          # SE37 Function Builder lookup
├── se93_tools.py          # SE93 Transaction Maintenance lookup
├── sm37_tools.py          # SM37 background job lookup
├── quick_report_tools.py  # Composite: TX → fill → F8 → read result
└── README.md              # This file
```

## Available Tools

### SAP Tools (`sap_tools.py`)

High-level, SAP-specific operations:

| Tool                  | Description                                                         |
| --------------------- | ------------------------------------------------------------------- |
| `sap_login`           | Opens SAP Web GUI for user to enter credentials                     |
| `sap_transaction`     | Enters and executes a transaction code (auto-enables OK-Code field) |
| `sap_keepalive_start` | Starts background task to prevent session timeout                   |
| `sap_keepalive_stop`  | Stops the keepalive background task                                 |

### Specialized Transaction Tools (faster, return structured data)

| Tool              | File            | Description                                               |
| ----------------- | --------------- | --------------------------------------------------------- |
| `sap_se11_lookup` | `se11_tools.py` | Look up table/structure metadata from ABAP Dictionary     |
| `sap_se16_query`  | `se16_tools.py` | Query table data via SE16N with pagination                |
| `sap_se24_lookup` | `se24_tools.py` | Look up class/interface metadata from Class Builder       |
| `sap_se37_lookup` | `se37_tools.py` | Look up function module signatures from Function Builder  |
| `sap_se93_lookup` | `se93_tools.py` | Look up transaction metadata from Transaction Maintenance |
| `sap_sm37_lookup` | `sm37_tools.py` | Look up background job status and logs |

### Composite Tools (multi-step pipelines)

| Tool               | File                   | Description                                                    |
| ------------------ | ---------------------- | -------------------------------------------------------------- |
| `sap_quick_report` | `quick_report_tools.py` | TX → fill selection screen → F8 → classify & read result table |

**Note:** Use these specialized tools instead of `sap_transaction('SExx')` - they are faster
and return structured Pydantic models instead of requiring manual screen parsing.

### Browser Tools (`browser_tools.py`)

Low-level escape hatches when SAP tools don't work:

| Tool                    | Description                                |
| ----------------------- | ------------------------------------------ |
| `browser_snapshot`      | Get accessibility tree of page             |
| `browser_screenshot`    | Take screenshot (returns base64 PNG)       |
| `browser_click`         | Click element by selector                  |
| `browser_fill`          | Fill input field                           |
| `browser_keyboard`      | Send keyboard input                        |
| `browser_navigate`      | Navigate to URL                            |
| `browser_evaluate`      | Execute JavaScript                         |
| `browser_wait`          | Wait for element state (use with selector) |
| `browser_get_html`      | Get HTML content                           |
| `browser_select_option` | Select dropdown option                     |

## Adding New Tools

### 1. Create a New Tool Module

Create a new file in the `tools/` directory:

```python
# src/sapguimcp/tools/my_custom_tools.py
"""Custom tools for [your use case]."""

import logging

from fastmcp import FastMCP

from sapguimcp.backend.manager import get_backend

__all__ = ["register_my_custom_tools"]

logger = logging.getLogger(__name__)


def register_my_custom_tools(mcp: FastMCP) -> None:
    """Register custom tools with the MCP server."""

    @mcp.tool()
    async def my_tool(
        param1: str, param2: int | None = None,
        session: str | None = None, agent_id: str | None = None,
    ) -> str:
        """
        Description of what this tool does.

        Args:
            param1: Description of param1
            param2: Optional description of param2

        Returns:
            Status message indicating success or describing any issues.
        """
        backend = await get_backend(session=session, agent_id=agent_id, tool_name="my_tool")

        try:
            await backend.click_button(param1)
            return f"Success: {param1}"
        except Exception as e:
            logger.exception("Error in my_tool")
            return f"Error: {e}"
```

### 2. Register in server.py

Update `server.py` to include your new tools:

```python
from sapguimcp.tools.my_custom_tools import register_my_custom_tools

# After creating the mcp instance:
register_sap_tools(mcp)
register_browser_tools(mcp)
register_my_custom_tools(mcp)  # Add this line
```

### 3. Export in `__init__.py`

```python
from sapguimcp.tools.my_custom_tools import register_my_custom_tools

__all__ = [
    # ... existing exports ...
    "register_my_custom_tools",
]
```

### 4. Add Tests

Create `unittests/test_my_custom_tools.py`:

```python
"""Tests for custom tools."""

import pytest


class TestMyCustomTools:
    """Tests for my_custom_tools module."""

    @pytest.mark.asyncio
    async def test_my_tool_success(self) -> None:
        """Test my_tool returns success."""
        # Your test implementation
        pass
```

## Tool Best Practices

### 1. Always Use Type Hints

```python
async def my_tool(
        required_param: str,
        optional_param: int | None = None,
        flag: bool = False,
) -> str:
```

### 2. Provide Comprehensive Docstrings

The docstring is what Claude sees when deciding which tool to use:

```python
async def sap_transaction(tcode: str) -> str:
    """
    Enter and execute an SAP transaction code.

    This tool will:
    1. Check if the OK-Code field is visible
    2. If not, attempt to enable it via Settings
    3. Enter the transaction code and execute it

    Args:
        tcode: Transaction code (e.g., VA01, MM03, SE80, SU01)

    Returns:
        Status message indicating success or describing any issues.
    """
```

### 3. Handle Errors Gracefully

```python
try:
    result = await page.click(selector)
    return f"Success: clicked {selector}"
except Exception as e:
    logger.exception("Error clicking element")
    return f"Error clicking {selector}: {e}"
```

### 4. Return Informative Messages

Tools should return messages that help Claude understand what happened:

```python
# Good
return f"Transaction {tcode} executed. Current page: {title}."

# Bad
return "Done"
```

### 5. Use Logging

```python
import logging

logger = logging.getLogger(__name__)

# In your tool:
logger.info("Starting transaction: %s", tcode)
logger.debug("Found OK-Code field: %s", okcode_field)
logger.exception("Error executing transaction")  # Includes stack trace
```

## Customizing SAP Selectors

The `SELECTORS` dictionary in `sap_tools.py` contains CSS selectors for SAP Web GUI elements.
You may need to customize these for your specific SAP version:

```python
from sapguimcp.tools import SELECTORS

# Override a selector
SELECTORS["okcode_field"] = 'input#myCustomOkCodeField'

# Or create your own selector dictionary
MY_SELECTORS = {
    **SELECTORS,
    "custom_button": 'button#myButton',
}
```

## Testing Tools

Run tool tests with:

```bash
tox -e tests
```

For coverage:

```bash
tox -e coverage
```

## Debugging Tips

1. **Use browser_snapshot** to see the page structure
2. **Use browser_screenshot** to see what's on screen
3. **Check logs** - tools log their actions
4. **Try browser_evaluate** to run diagnostic JavaScript

Example debugging workflow:

```
Claude: I'll first take a snapshot to understand the page structure.
[calls browser_snapshot]

Claude: I can see the structure. Let me take a screenshot to verify visually.
[calls browser_screenshot]

Claude: Now I'll try clicking the element.
[calls browser_click with the right selector]
```
