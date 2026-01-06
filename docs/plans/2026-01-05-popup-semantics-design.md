# Popup Semantics Redesign

## Problem

Current naming implies popups are always errors/blockers:

- `blocking_popup` field name
- `sap_dismiss_popup` tool name
- "Dismiss" language throughout

But popups aren't always problems:

- F4 help dialogs are the _goal_, not a blocker
- Confirmation dialogs need user decision
- Only error popups are actual blockers

## Solution

Rename to neutral terminology and add popup type classification.

### Model Changes

**New enum in `models/base.py`:**

```python
class PopupType(StrEnum):
    """Type of popup dialog."""
    HELP = "help"        # F4 search help, value lists
    CONFIRM = "confirm"  # Yes/No decisions
    ERROR = "error"      # Validation errors, warnings
    INFO = "info"        # Informational messages
    UNKNOWN = "unknown"  # Can't determine (default)
```

**Updated PopupInfo:**

```python
class PopupInfo(BaseModel):
    """Info about an active popup dialog."""

    popup_type: PopupType = Field(
        default=PopupType.UNKNOWN,
        description="Type of popup if detectable: help, confirm, error, info, or unknown"
    )
    message: str | None = Field(default=None, description="Popup message text")
    buttons: list[PopupButton] = Field(default_factory=list, description="Available buttons")
    close_button_id: str | None = Field(default=None, description="ID of X close button if present")
```

**ToolResult field rename:**

```python
# Old
blocking_popup: PopupInfo | None

# New
popup: PopupInfo | None = Field(
    default=None,
    description="Present when a popup dialog is active on screen"
)
```

### Tool Rename

```python
# Old
sap_dismiss_popup() -> DismissPopupResult

# New
sap_close_popup() -> ClosePopupResult
```

New description:

> Close an active popup dialog. Use after a tool returns popup info.
> For F4 help popups, consider reading the values first before closing.
> Specify button by label ('Ja', 'Nein') or accesskey ('J', 'N'),
> or use close=True to click the X button if available.

### Files to Update

| File                    | Changes                                                |
| ----------------------- | ------------------------------------------------------ |
| `models/base.py`        | Add `PopupType` enum, rename field to `popup`          |
| `models/sap_results.py` | Rename `DismissPopupResult` → `ClosePopupResult`       |
| `models/__init__.py`    | Update exports                                         |
| `tools/sap_tools.py`    | Rename tool + helper, update all `blocking_popup` refs |
| `data/sap_knowledge.md` | Update popup guidance text                             |
| Tests                   | Update popup-related assertions                        |

### Internal Helper Rename

```python
# Old
async def _check_blocking_popup(page) -> PopupInfo | None:

# New
async def _check_popup(page) -> PopupInfo | None:
```

## Migration

Hard rename, no deprecation aliases. This is pre-1.0 and clients are AI agents that will adapt.

## Future Work

- Add popup type detection heuristics as we learn patterns
- Add tools to interact with popup content (read F4 values, select from list)
