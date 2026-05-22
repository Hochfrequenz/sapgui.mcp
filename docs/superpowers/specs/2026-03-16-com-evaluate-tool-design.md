# Design: `sap_com_evaluate` — General-Purpose COM Tool

**Issue:** #375
**Date:** 2026-03-16

## Purpose

Give the LLM a general-purpose escape hatch for interacting with SAP GUI desktop elements via COM, mirroring how `browser_evaluate` works for WebGUI. The LLM uses `sap_get_snapshot` to see the screen, identifies element IDs, then calls `sap_com_evaluate` to read/write properties or call methods.

## API

### MCP Tool: `sap_com_evaluate`

```python
async def sap_com_evaluate(
    element_id: str,
    action: str,           # "get", "set", or "call"
    property_or_method: str,
    args: list[str | int | bool] | None = None,
    session: str | None = None,
    agent_id: str | None = None,
) -> ComEvaluateResult:
```

**Parameters:**

- `element_id`: SAP GUI element path (e.g., `"wnd[0]/usr/txtFIELD"`, `"wnd[0]/usr/cntl/shell"`)
- `action`: One of:
    - `"get"` — read a property (e.g., `Text`, `Selected`, `RowCount`)
    - `"set"` — write a property (e.g., `Text`, `Selected`)
    - `"call"` — call a method (e.g., `SendVKey`, `SelectRows`, `GetCellValue`)
- `property_or_method`: The COM property or method name (e.g., `"Text"`, `"GetCellValue"`)
- `args`: Arguments for `"set"` (value) or `"call"` (method args). Not used for `"get"`.

**Examples the LLM would generate:**

```python
# Read a field value
sap_com_evaluate("wnd[0]/usr/txtRSYST-BNAME", "get", "Text")
# → {"result": "KLEINK"}

# Set a field value
sap_com_evaluate("wnd[0]/usr/txtRSYST-BNAME", "set", "Text", ["NEWUSER"])
# → {"result": "NEWUSER"}

# Call a method with args
sap_com_evaluate("wnd[0]/usr/cntl/shell", "call", "GetCellValue", [0, "MATNR"])
# → {"result": "100-100"}

# Press Enter on a window
sap_com_evaluate("wnd[0]", "call", "SendVKey", [0])
# → {"result": null}

# Select rows in a grid
sap_com_evaluate("wnd[0]/usr/cntl/shell", "call", "SelectRows", ["0,1,2"])
# → {"result": null}
```

### Return Model: `ComEvaluateResult`

```python
class ComEvaluateResult(ToolResult):
    result: str | None = None        # JSON-serialized result
    element_id: str | None = None    # Echo back the element ID
    action: str | None = None        # Echo back the action
```

Mirrors `EvaluateResult` from `browser_tools.py`.

## Implementation

### Backend Method

Add to `DesktopBackend`:

```python
async def evaluate_com(
    self, element_id: str, action: str, property_or_method: str, args: list[Any] | None = None
) -> Any:
```

This is the protocol-level method. The MCP tool wraps it with session management and JSON serialization.

### COM Thread Dispatch

All COM work runs on the dedicated `ComThread`:

```python
def _evaluate() -> Any:
    elem = session.find_by_id(element_id)
    raw = getattr(elem, "com", getattr(elem, "_com", elem))

    if action == "get":
        return getattr(raw, property_or_method)
    elif action == "set":
        setattr(raw, property_or_method, args[0] if args else "")
        return getattr(raw, property_or_method)  # read back
    elif action == "call":
        method = getattr(raw, property_or_method)
        return method(*(args or []))
```

### Result Serialization

COM can return complex objects. Serialization strategy:

- Primitives (str, int, bool, None) → direct JSON
- COM collections → convert to list of strings
- COM objects → return their `.Id` and `.Type` as a dict
- Everything else → `str(result)`

### File Placement

- **Tool registration:** New file `src/sapguimcp/tools/com_tools.py` (mirrors `browser_tools.py`)
- **Result model:** Add `ComEvaluateResult` to `src/sapguimcp/models/browser_results.py` (or new `com_results.py`)
- **Backend method:** Add `evaluate_com` to `DesktopBackend` in `src/sapguimcp/backend/desktop/__init__.py`

## Safety

Same approach as `browser_evaluate` — full access with a clear warning in the tool description:

> "Execute a COM operation on any SAP GUI element. Use with caution — this has full access to the SAP GUI scripting interface. Prefer SAP-specific tools when available."

The LLM already has full SAP access via specialized tools. This just removes the need to add a new specialized tool for every edge case.

## Testing

1. Unit test with mock session: verify get/set/call dispatch
2. Integration test: read a field value on SE38 initial screen
3. Integration test: call SendVKey(0) (Enter) on a window
4. Error test: nonexistent element ID returns failure
