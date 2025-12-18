# Tools

This directory contains MCP tool definitions for SAP Web GUI automation.

## Module Structure

```
tools/
├── __init__.py         # Package exports
├── registry.py         # Central tool registration
├── sap_tools.py        # High-level SAP tools
├── browser_tools.py    # Low-level browser escape hatches
└── README.md           # This file
```

## Available Tools

### SAP Tools (`sap_tools.py`)

High-level, SAP-specific operations:

| Tool                  | Description                                                         |
|-----------------------|---------------------------------------------------------------------|
| `sap_login`           | Opens SAP Web GUI for user to enter credentials                     |
| `sap_transaction`     | Enters and executes a transaction code (auto-enables OK-Code field) |
| `sap_keepalive_start` | Starts background task to prevent session timeout                   |
| `sap_keepalive_stop`  | Stops the keepalive background task                                 |

### Browser Tools (`browser_tools.py`)

Low-level escape hatches when SAP tools don't work:

| Tool                    | Description                          |
|-------------------------|--------------------------------------|
| `browser_snapshot`      | Get accessibility tree of page       |
| `browser_screenshot`    | Take screenshot (returns base64 PNG) |
| `browser_click`         | Click element by selector            |
| `browser_fill`          | Fill input field                     |
| `browser_keyboard`      | Send keyboard input                  |
| `browser_navigate`      | Navigate to URL                      |
| `browser_evaluate`      | Execute JavaScript                   |
| `browser_wait`          | Wait for element or timeout          |
| `browser_get_html`      | Get HTML content                     |
| `browser_select_option` | Select dropdown option               |

## Adding New Tools

### 1. Create a New Tool Module

Create a new file in the `tools/` directory:

```python
# src/sapwebguimcp/tools/my_custom_tools.py
"""
Custom tools for [your use case].
"""

import logging
from typing import Optional

from mcp.server import Server

from sapwebguimcp.models import get_browser_manager

__all__ = ["register_my_custom_tools"]

logger = logging.getLogger(__name__)


def register_my_custom_tools(server: Server) -> None:
    """Register custom tools with the MCP server."""

    @server.tool()
    async def my_tool(param1: str, param2: Optional[int] = None) -> str:
        """
        Description of what this tool does.

        Args:
            param1: Description of param1
            param2: Optional description of param2

        Returns:
            Description of return value
        """
        manager = await get_browser_manager()
        page = await manager.get_current_page()

        try:
            # Your tool implementation here
            await page.click(f"#{param1}")
            return f"Success: {param1}"
        except Exception as e:
            logger.exception("Error in my_tool")
            return f"Error: {e}"
```

### 2. Register in the Registry

Update `registry.py` to include your new tools:

```python
from sapwebguimcp.tools.my_custom_tools import register_my_custom_tools


def register_all_tools(server: Server) -> None:
    register_sap_tools(server)
    register_browser_tools(server)
    register_my_custom_tools(server)  # Add this line
```

### 3. Export in `__init__.py`

```python
from sapwebguimcp.tools.my_custom_tools import register_my_custom_tools

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
        optional_param: Optional[int] = None,
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
from sapwebguimcp.tools import SELECTORS

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
