# Popup Handling Design

## Problem

SAP popup dialogs block MCP tool operations:

1. **Confirmation dialogs** (Ja/Nein) - e.g., "Discard unsaved changes?"
2. **Blocking overlay layers** (`lsBlockLayer`, `urPopupWindowBlockLayer`) - intercept clicks, cause 30s timeouts

Current tools don't detect popups, leading to timeouts and failed operations.

## Solution

### 1. Popup Detection (Fast Path)

Fast check (~5ms) before operations:

```javascript
// Quick CSS selector check
const isBlocked = document.querySelector('#urPopupWindowBlockLayer, .lsBlockLayer') !== null;
```

Detailed extraction only when blocked:

```javascript
const popup = {
  message: document.querySelector('.urMessageText, .lsPopupText')?.textContent?.trim(),
  buttons: [...],
  closeButton: document.querySelector('[class*="close"], [title*="Close"]')
};
```

### 2. Models

```python
class PopupButton(BaseModel):
    label: str  # "Ja", "Nein", "Abbrechen"
    accesskey: str | None  # "J", "N"
    id: str | None  # "M1:46:::10:5"

class PopupInfo(BaseModel):
    message: str | None
    buttons: list[PopupButton]
    has_close_button: bool
    close_button_id: str | None

class ToolResult(BaseModel):
    success: bool = True
    error: str | None = None
    blocking_popup: PopupInfo | None = None  # NEW
```

### 3. Affected Tools

Tools that check for popup before operating:

- `sap_transaction`
- `sap_press_key`
- `sap_fill_form`
- `sap_set_field`
- `browser_click`
- `browser_fill`

Pattern:

```python
popup = await _check_blocking_popup(page)
if popup:
    return Result.failure("Popup blocking", blocking_popup=popup)
```

### 4. Dismiss Tool

```python
async def sap_dismiss_popup(
    button: str | None = None,  # Label or accesskey
    close: bool = False,        # Click X button
) -> DismissPopupResult
```

Error cases:

- No popup present
- `close=True` but no X button
- Button not found

### 5. Integration Test

BP discard changes popup:

1. `sap_login`
2. `sap_transaction("BP")`
3. `sap_press_key("F5")` - create person
4. `sap_fill_form({"Nachname": "Test"})`
5. `sap_transaction("SE16")` - triggers popup
6. Verify `blocking_popup` in response
7. `sap_dismiss_popup(button="Ja")`
8. Verify popup dismissed

## Implementation Order

1. Add models (`PopupInfo`, `PopupButton`, `DismissPopupResult`)
2. Add `blocking_popup` to `ToolResult` base class
3. Add JS + Python helpers for popup detection
4. Add `sap_dismiss_popup` tool
5. Add popup check to affected tools
6. Write BP integration test
