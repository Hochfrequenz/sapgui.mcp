# Skill: General SAP GUI Navigation

## Overview

This skill covers basic navigation patterns in SAP GUI for Windows, including:

- Using the OK-Code field for transactions
- Standard keyboard shortcuts
- Finding and interacting with common UI elements

## Prerequisites

- SAP GUI for Windows is installed and scripting is enabled
- User must be logged into SAP (`sap_login`)

## Keyboard Shortcuts

SAP GUI supports these standard keyboard shortcuts:

| Shortcut | Action                        |
| -------- | ----------------------------- |
| Enter    | Execute/Confirm               |
| F3       | Back                          |
| Shift+F3 | Exit                          |
| Ctrl+S   | Save                          |
| F4       | Search Help (on input fields) |
| F5       | Refresh                       |
| F8       | Execute (in reports/lists)    |
| Ctrl+F   | Find                          |

To send keyboard shortcuts, use `sap_press_key`:

```
sap_press_key(key="F3")  # Go back
sap_press_key(key="Ctrl+S")  # Save
```

Use `sap_get_shortcuts` to list the shortcuts of the buttons on the current screen.

## OK-Code Field

The OK-Code field (also called command field or transaction field) is used to:

- Start new transactions: `/n{tcode}` (e.g., `/nVA01`)
- Open transaction in new session: `/o{tcode}` (e.g., `/oMM03`)
- End current transaction: `/n`
- Log off: `/nex`

Use the `sap_transaction` tool to enter a transaction code. It handles the OK-Code field for you.

## Common UI Elements

### Status Bar

Location: Bottom of the SAP window
Contains: System messages, errors, warnings

Read it with `sap_read_status_bar`. It returns the message type (S, I, W, E, A) and the text.

### Toolbar Buttons

Use `sap_discover_buttons` to list the buttons of the current screen, then `sap_click_button` to press one.
Prefer a keyboard shortcut (`sap_press_key`) when the button has one.

### Input Fields

SAP input fields have:

- Technical names like `VBAK-VBELN`
- Labels nearby, like "Customer"
- SAP GUI element IDs like `wnd[0]/usr/ctxtVBAK-VBELN`

Use `sap_discover_fields` to list the fields of the current screen with label, name and ID.
Fill them with `sap_fill_form` (several fields) or `sap_set_field` (one field), using the label or the technical name.

## Workflow: Navigate to Transaction

1. **Ensure logged in**: Use `sap_login` if needed
2. **Enter transaction**: Use `sap_transaction(tcode="XX00")`
3. **Verify screen**: Check the window title or look for expected elements (`sap_get_screen_info`)
4. **Handle errors**: Read status bar for messages

## Workflow: Fill Screen and Save

1. **Identify fields**: Use `sap_discover_fields` to see the fields
2. **Fill fields**: Use `sap_fill_form` for all fields in one call
3. **Verify entries**: Optionally read back values with `sap_get_form_fields`
4. **Save**: Press Ctrl+S or click Save button
5. **Check result**: Read status bar for success/error message

## Error Recovery

### "Session expired"

- Re-run `sap_login`
- Check the session with `sap_session_status`

### "Element not found"

- Use `sap_com_snapshot` to see the current element tree
- Try the technical field name instead of the label
- Check if a popup is blocking (`sap_close_popup`)

### "Authorization error"

- Note the authorization object from the error
- User may need additional roles
- Try transaction SU53 to see missing authorization

## Example Dialogue

```
User: Go to MM03 and look up material 12345

Claude: I'll navigate to the material display transaction.
[calls sap_transaction("MM03")]

The Material Display screen is open. I'll enter the material number.
[calls sap_fill_form({"Material": "12345"})]

[calls sap_press_key(key="Enter")]

The material 12345 is now displayed. I can see:
- Description: Widget ABC
- Base Unit: EA
- Material Type: FERT

What would you like to know about this material?
```
