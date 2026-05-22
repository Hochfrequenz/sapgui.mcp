# Skill: General SAP Web GUI Navigation

## Overview

This skill covers basic navigation patterns in SAP Web GUI, including:

- Using the OK-Code field for transactions
- Standard keyboard shortcuts
- Finding and interacting with common UI elements

## Prerequisites

- User must be logged into SAP Web GUI
- Browser must be open with SAP Web GUI loaded

## Keyboard Shortcuts

SAP Web GUI supports these standard keyboard shortcuts:

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

To send keyboard shortcuts, use `browser_keyboard`:

```
browser_keyboard(key="F3")  # Go back
browser_keyboard(key="Control+s")  # Save
```

## OK-Code Field

The OK-Code field (also called command field or transaction field) is used to:

- Start new transactions: `/n{tcode}` (e.g., `/nVA01`)
- Open transaction in new session: `/o{tcode}` (e.g., `/oMM03`)
- End current transaction: `/n`
- Log off: `/nex`

### If OK-Code Field is Hidden

1. Look for a settings/gear icon in the toolbar
2. Open settings dialog
3. Find "OK-Code Field" or "Transaction Field" option
4. Enable it
5. Save settings

The `sap_transaction` tool handles this automatically.

## Common UI Elements

### Status Bar

Location: Bottom of the SAP window
Contains: System messages, errors, warnings

Selectors to try:

- `.urMsgBarTxt`
- `.sapMSGtext`
- `[class*="message" i]`
- `[class*="status" i]`

### Toolbar Buttons

Common button patterns:

- Save: `button:has-text("Save")`, `[title*="Save" i]`
- Back: `button:has-text("Back")`, `[title*="Back" i]`
- Cancel: `button:has-text("Cancel")`, `[title*="Cancel" i]`

### Input Fields

SAP input fields often have:

- Technical IDs like `M0_R1_C2_txt`
- Name attributes with field names like `VBAK-VBELN`
- Labels nearby with `for` attributes

Finding fields by label:

```
1. Find label with text
2. Get `for` attribute
3. Find input with matching ID
```

Or use nearby selector:

```
td:has-text("Customer") input
```

## Workflow: Navigate to Transaction

1. **Ensure logged in**: Use `sap_login` if needed
2. **Enter transaction**: Use `sap_transaction(tcode="XX00")`
3. **Verify screen**: Check page title or look for expected elements
4. **Handle errors**: Read status bar for messages

## Workflow: Fill Screen and Save

1. **Identify fields**: Use `browser_snapshot` to see structure
2. **Fill fields**: Use `browser_fill` for each input
3. **Verify entries**: Optionally read back values
4. **Save**: Press Ctrl+S or click Save button
5. **Check result**: Read status bar for success/error message

## Error Recovery

### "Session expired"

- Re-run `sap_login`
- Check if page shows login form

### "Element not found"

- Use `browser_snapshot` to see current page structure
- Try alternative selectors
- Check if a popup/modal is blocking

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
[calls browser_fill with material field selector and "12345"]

[calls browser_keyboard(key="Enter")]

The material 12345 is now displayed. I can see:
- Description: Widget ABC
- Base Unit: EA
- Material Type: FERT

What would you like to know about this material?
```
