# Design: `sap_fill_form` Tool

## Problem

Filling SAP forms currently requires 2 tool calls per field (focus + keyboard). For a form with 8 fields, that's 16 LLM round-trips - slow and inefficient.

## Solution

A new `sap_fill_form` tool that fills multiple fields in a single call using JavaScript batch execution.

## API

```python
sap_fill_form(
    fields: dict[str, str],  # {"Label or Selector": "value", ...}
    strict: bool = False     # If True, fail if any field not found
)
```

### Example Usage

```python
sap_fill_form({
    "First Name": "Max",
    "Last Name": "Mustermann",
    "Street": "Hauptstraße",
    "#M0:46:1:1:2:2:1:2B256:1:13:1:1::2:22": "10115"
})
```

### Key Resolution

Keys can be:

- **Label text** - Visible text on screen (e.g., "First Name", "Straße")
- **CSS selector** - Starting with `#` (e.g., "#M0:46:1:1::0:21")

Labels are resolved dynamically by scanning the page for matching text and finding adjacent input fields.

## Implementation

### 1. Pydantic Input Model

```python
class FillFormInput(BaseModel):
    fields: dict[str, str] = Field(
        description=(
            "Fields to fill. Keys can be:\n"
            "- Label text visible on screen (e.g., 'First Name', 'Straße')\n"
            "- CSS selector starting with '#' (e.g., '#M0:46:1:1::0:21')\n"
            "Values are the text to enter."
        )
    )
    strict: bool = Field(
        default=False,
        description="If True, fail when any field not found. If False, skip and report."
    )

    @field_validator('fields')
    @classmethod
    def fields_not_empty(cls, v: dict[str, str]) -> dict[str, str]:
        if not v:
            raise ValueError("fields cannot be empty")
        return v
```

### 2. Result Model

```python
class FillFormResult(ToolResult):
    filled: list[str] = Field(default_factory=list, description="Fields successfully filled")
    not_found: list[str] = Field(default_factory=list, description="Fields not found on page")
    errors: list[dict[str, str]] = Field(default_factory=list, description="Fields that errored")
```

### 3. JavaScript Implementation

```javascript
function findInputByLabel(labelText) {
    // Try exact label match with 'for' attribute
    const labels = document.querySelectorAll('label');
    for (const label of labels) {
        if (label.textContent.trim() === labelText && label.htmlFor) {
            return document.getElementById(label.htmlFor);
        }
    }

    // Find text node, then nearest input (SAP uses spans/divs as labels)
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    while (walker.nextNode()) {
        if (walker.currentNode.textContent.trim() === labelText) {
            const parent = walker.currentNode.parentElement;
            const container = parent.closest('tr, div, td');
            if (container) {
                const input = container.querySelector('input, textarea, select');
                if (input) return input;
            }
        }
    }
    return null;
}

function fillFields(fieldsJson) {
    const fields = JSON.parse(fieldsJson);
    const results = { filled: [], notFound: [], errors: [] };

    for (const [key, value] of Object.entries(fields)) {
        try {
            let el;
            if (key.startsWith('#')) {
                el = document.querySelector(key);
            } else {
                el = findInputByLabel(key);
            }

            if (!el) {
                results.notFound.push(key);
                continue;
            }

            el.focus();
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
            results.filled.push(key);
        } catch (e) {
            results.errors.push({ field: key, error: e.message });
        }
    }
    return results;
}
```

### 4. Tool Description

```python
@mcp.tool(
    description=(
        "Fill multiple SAP form fields in a single call. "
        "Use this when filling 2+ fields on the SAME screen without UI navigation between them. "
        "Much faster than multiple browser_fill/browser_keyboard calls.\n\n"
        "Keys can be:\n"
        "- Visible label text (e.g., 'First Name', 'Straße')\n"
        "- CSS selectors (e.g., '#M0:46:1:1::0:21')\n\n"
        "When to use:\n"
        "- Filling a form with multiple input fields\n"
        "- All fields visible on current screen\n"
        "- No button clicks or navigation needed between fields\n\n"
        "When NOT to use:\n"
        "- Single field only (use browser_fill)\n"
        "- Fields on different screens/tabs\n"
        "- Need to click buttons between fills"
    )
)
```

### 5. Update Existing Tool Descriptions

**browser_fill:**

```
"Fill a single input field by CSS selector. For filling multiple fields on the same screen, use sap_fill_form instead - it's faster."
```

**browser_keyboard:**

```
"Send keyboard input. For filling multiple form fields, use sap_fill_form instead - it's faster than repeated focus+type calls."
```

## Implementation Steps

1. Add `FillFormResult` to `models/sap_results.py`
2. Add `sap_fill_form` tool to `tools/sap_tools.py`
3. Update `browser_fill` and `browser_keyboard` descriptions
4. Add unit tests
5. Test with real SAP BP transaction

## Performance Impact

- Before: 16 tool calls for 8 fields (2 per field)
- After: 1 tool call for 8 fields
- **~16x reduction in round-trips**
