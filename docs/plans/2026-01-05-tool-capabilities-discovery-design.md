# Tool Capabilities Discovery Design

**Date:** 2026-01-05
**Status:** Ready for implementation

## Problem

The client (AI) may start interacting with SAP without reading all available tool descriptions. Key guidance like "use `sap_get_shortcuts` before clicking buttons" lives in individual tool descriptions that the client might never read unless it already decides to call that tool.

## Solution

Two-part approach:

1. **Encourage reading all tool descriptions** via a new `sap_get_capabilities()` tool that dynamically returns all tool names and descriptions
2. **Prompt after login** by adding a `guidance` field to `LoginResult` that tells the client to call `sap_get_capabilities()`

Additionally, ensure all tool guidance is properly exposed via MCP by moving detailed descriptions from docstrings to the `description` parameter.

## Design

### Part A: Move descriptions to `description` parameter

FastMCP exposes the `description` parameter via MCP, but ignores docstrings for this purpose. Currently some tools have:

- Guidance split between decorator `description` and docstring
- Detailed docstring not exposed via MCP

**Change:** Merge docstring content into `description` parameter for all `@mcp.tool` decorated functions. Remove or minimize docstrings (add `# pylint: disable=missing-function-docstring`).

**Files affected:**

- `src/sapguimcp/tools/sap_tools.py`
- `src/sapguimcp/tools/browser_tools.py`
- `src/sapguimcp/tools/intent_tools.py`
- `src/sapguimcp/tools/feedback_tools.py`
- `src/sapguimcp/tools/workflow_tools.py`

### Part B: New `sap_get_capabilities()` tool

```python
@mcp.tool(
    description=(
        "RECOMMENDED: Call at the start of every SAP session. "
        "Returns all available tools with their full descriptions. "
        "Reading this first helps you work faster and avoid common mistakes."
    )
)
async def sap_get_capabilities() -> CapabilitiesResult:  # pylint: disable=missing-function-docstring
    # Introspect MCP registry to get all registered tools
    tools = []
    for tool in mcp._tool_manager.tools.values():
        tools.append(ToolInfo(
            name=tool.name,
            description=tool.description or "",
        ))
    return CapabilitiesResult(tools=tools)
```

### Part C: New models

```python
# In src/sapguimcp/models/capabilities_models.py

class ToolInfo(BaseModel):
    """Information about a single tool."""
    name: str
    description: str

class CapabilitiesResult(SapResult):
    """Result of sap_get_capabilities call."""
    tools: list[ToolInfo] = Field(default_factory=list)
```

### Part D: Modify `LoginResult`

```python
class LoginResult(SapResult):
    """Result of SAP login attempt."""
    url: str | None = None
    user: str | None = None
    already_logged_in: bool = False
    guidance: str | None = None  # NEW
```

On successful login (both fresh and already_logged_in):

```python
return LoginResult(
    url=effective_url,
    user=settings.sap_user,
    guidance=(
        "RECOMMENDED: Call sap_get_capabilities() to review all available tools "
        "and their descriptions before proceeding."
    ),
)
```

## Implementation Tasks

1. [ ] Create `CapabilitiesResult` and `ToolInfo` models
2. [ ] Add `guidance` field to `LoginResult`
3. [ ] Implement `sap_get_capabilities()` tool with MCP introspection
4. [ ] Update `sap_login` to populate `guidance` on success
5. [ ] Migrate all tool descriptions (sap_tools.py)
6. [ ] Migrate all tool descriptions (browser_tools.py)
7. [ ] Migrate all tool descriptions (intent_tools.py)
8. [ ] Migrate all tool descriptions (feedback_tools.py)
9. [ ] Migrate all tool descriptions (workflow_tools.py)
10. [ ] Add unit tests for `sap_get_capabilities()`
11. [ ] Verify MCP introspection works correctly

## Open Questions

- Exact FastMCP API for introspecting registered tools (need to verify `mcp._tool_manager.tools` or similar)
