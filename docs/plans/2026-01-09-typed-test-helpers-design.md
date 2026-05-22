# Typed Test Helpers Design

## Problem

Test code has repetitive boilerplate for MCP tool calls:

```python
result = await sap_mcp_client.call_tool("sap_se16_query", {"table": "TSTC", "max_hits": 130})
assert result.content, "sap_se16_query returned no content"
text = _get_content_text(result.content[0])
data = json.loads(text)
assert data["success"] is True, f"Query failed: {data.get('error')}"
```

Issues:

- No type safety - `data` is `dict[str, Any]`
- Duplicate utility functions across 3 test files
- Manual JSON parsing and error checking

## Solution

A typed helper function that returns Pydantic models directly:

```python
result = await call_tool_typed(
    sap_mcp_client, "sap_se16_query",
    {"table": "TSTC", "max_hits": 130},
    SE16Result
)
assert result.success, f"Query failed: {result.error}"
assert result.table == "TSTC"  # typed attribute access
```

## Design

### Core Helper Function

```python
from typing import TypeVar, Any
from pydantic import BaseModel
from mcp import ClientSession

T = TypeVar("T", bound=BaseModel)
E = TypeVar("E", bound=BaseModel)

def _extract_content_text(content_item: Any) -> str:
    """Extract text from MCP content item (TextContent or EmbeddedResource)."""
    import base64
    if hasattr(content_item, "text"):
        return content_item.text
    elif hasattr(content_item, "resource") and hasattr(content_item.resource, "blob"):
        return base64.b64decode(content_item.resource.blob).decode("utf-8")
    return str(content_item)

async def call_tool_typed(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any],
    result_type: type[T],
    error_type: type[E] | None = None,
) -> T | E:
    """
    Call an MCP tool and return a typed Pydantic model.

    Discriminates using:
    - success=False -> parse as error_type (if provided)
    - presence of 'error' field with non-None value -> parse as error_type
    - otherwise -> parse as result_type
    """
    result = await client.call_tool(tool_name, args)
    assert result.content, f"{tool_name} returned no content"

    text = _extract_content_text(result.content[0])
    data = json.loads(text)

    # Discriminate between success/error
    if error_type is not None:
        is_error = data.get("success") is False or data.get("error") is not None
        if is_error:
            return error_type.model_validate(data)

    return result_type.model_validate(data)
```

### Additional Helpers

```python
async def assert_tool_success(
    client: ClientSession,
    tool_name: str,
    args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Call tool, assert success=True, return raw dict. For simple cases."""
    result = await client.call_tool(tool_name, args or {})
    assert result.content, f"{tool_name} returned no content"
    text = _extract_content_text(result.content[0])
    data = json.loads(text)
    assert data.get("success", True), f"{tool_name} failed: {data.get('error')}"
    return data

async def do_login(client: ClientSession) -> LoginResult:
    """Login and return typed result."""
    return await call_tool_typed(client, "sap_login", {}, LoginResult)
```

## Edge Cases

1. **Non-JSON responses** (e.g., `browser_get_html`, `browser_screenshot`)
    - Keep as raw `call_tool` calls - don't use `call_tool_typed`

2. **Multiple content items**
    - Always use `result.content[0]` - no tools return multiple items

3. **Union types** (success/error)
    - Pass both `result_type` and `error_type`
    - Discrimination via `success=False` or presence of `error` field

## Migration Scope

| File                                 | Calls | Change                           |
| ------------------------------------ | ----- | -------------------------------- |
| `unittests/conftest.py`              | -     | Add helpers                      |
| `unittests/test_sap_integration.py`  | ~342  | Remove duplicates, migrate calls |
| `unittests/test_se16_integration.py` | ~25   | Remove duplicates, migrate calls |
| `unittests/test_se11_integration.py` | ~32   | Remove duplicates, migrate calls |

## What Stays Unchanged

- Non-JSON tool calls
- Unit tests without MCP client calls
- All production code in `src/`

## Type Sources

Return types are read from tool function annotations in `src/sapguimcp/tools/*.py` and models in `src/sapguimcp/models/*.py`.
