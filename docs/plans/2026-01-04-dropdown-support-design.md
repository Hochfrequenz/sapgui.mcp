# Dropdown/ComboBox Support Design

## Problem

SAP dropdown fields (ComboBox, `ct="CB"`) cannot be filled with `sap_fill_form` or `browser_fill` because:

- They have `readonly` attribute (can't type directly)
- Clicking opens a listbox popup with `role="listbox"`
- Standard `browser_click` on options fails ("element is not visible")
- Multiple hidden listboxes may exist in DOM from previous interactions

## Solution

Integrate dropdown support into existing tools with lazy option fetching by default.

### Dropdown Detection

Identify dropdowns via:

```javascript
is_dropdown = element.getAttribute('ct') == 'CB' && element.hasAttribute('readonly');
```

Key attributes:

- `id` - element ID for clicking
- `value` - current selection
- `title` - tooltip/label
- `aria-labelledby` - linked label element ID

### Models

```python
class SapFieldType(str, Enum):
    TEXT = "text"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    RADIO = "radio"

class FormField(BaseModel):
    id: str = Field(description="Element ID for targeting with sap_fill_form or browser tools")
    label: str = Field(description="Visible label text associated with this field")
    field_type: SapFieldType = Field(description="Type of input control: text, dropdown, checkbox, or radio")
    current_value: str | None = Field(description="Current field value, or None if empty")
    readonly: bool = Field(description="True if field cannot be edited (HTML readonly/disabled attribute)")
    options: list[str] | None = Field(
        default=None,
        description="Available options for dropdown fields. Only populated when include_dropdown_options=True"
    )

class DropdownInfo(BaseModel):
    id: str = Field(description="Element ID for targeting")
    label: str = Field(description="Visible label text")
    options: list[str] = Field(description="Available dropdown options")
```

### New Tool: `sap_get_form_fields`

```python
async def sap_get_form_fields(
    include_dropdown_options: bool = False
) -> FormFieldsResult
```

Returns all fillable fields on screen with type detection. When `include_dropdown_options=True`, opens each dropdown to capture available options.

### Extended: `sap_get_screen_text`

```python
async def sap_get_screen_text(
    include_dropdown_options: bool = False
) -> ScreenTextResult
```

Adds `dropdowns: list[DropdownInfo] | None` to result when parameter is True.

### Extended: `sap_fill_form` Dropdown Handling

When filling a dropdown field:

1. Detect field is dropdown (`ct="CB"` + `readonly`)
2. Click field to open listbox
3. Wait for visible listbox (`[role="listbox"]` with `offsetParent !== null`)
4. Search for exact match in options
5. **Match found:** Click option via JavaScript, wait for listbox to close
6. **No match:** Return failure with all available options
7. **Popup appears:** Return success + `blocking_popup` info

Error response example:

```json
{
    "success": false,
    "error": "Value 'Kreditor' not found in dropdown 'GP-Rolle'",
    "available_options": ["GPartner allgemein", "Gläubiger", "Debitor"]
}
```

### JavaScript for Listbox Interaction

```javascript
// Find visible listbox (SAP keeps old ones hidden in DOM)
const listbox = [...document.querySelectorAll('[role="listbox"]')].find(
    (lb) => lb.offsetParent !== null
);

// Extract options
const options = [...listbox.querySelectorAll('[role="option"]')].map((opt) => ({
    text: opt.textContent.trim(),
    id: opt.id,
}));

// Click option (standard click fails, use JS)
option.click();
```

## Testing

### Unit Tests (HTML snapshots)

- Dropdown detection from `bp_create_person_de.html`
- Verify `ct="CB"` + `readonly` identification
- Label extraction for GP-Rolle, Gruppierung, Anredetext

### Integration Tests (BP transaction)

1. `test_dropdown_detection` - verify dropdowns found on BP F5 screen
2. `test_dropdown_get_options` - open GP-Rolle, verify options include "Gläubiger"
3. `test_dropdown_select_value` - select "Gläubiger", handle popup with `sap_dismiss_popup`
4. `test_dropdown_select_empty_field` - select value in empty Gruppierung dropdown
5. `test_dropdown_invalid_value` - verify error returns available options

### New Snapshots

- BP F5 screen with listbox open

## Implementation Order

1. Add `SapFieldType` enum and `FormField` model to `models/sap_results.py`
2. Create `js/detect_dropdowns.js`
3. Create `js/get_dropdown_options.js`
4. Create `js/select_dropdown_option.js`
5. Add `sap_get_form_fields` tool
6. Extend `sap_fill_form` with dropdown handling
7. Extend `sap_get_screen_text` with `include_dropdown_options`
8. Capture new HTML snapshots
9. Write unit tests
10. Write integration tests
