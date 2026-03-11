---
description: Create a complete ISU/Utilities contract chain (GP, contract account, connection object, premise, installation, move-in) by composing generic SAP tools
---

# Create a Complete ISU/Utilities Contract

## Overview

This recipe walks through the full ISU (Industry Solution Utilities) object chain required to set up a utility contract. Each step builds on the previous one, so the order matters. All values shown below are **examples only** -- verify every value against your system configuration before using them.

The same generic tools are used throughout: `sap_transaction`, `sap_keyboard`, `sap_fill_form`, `sap_read_status_bar`, `sap_discover_fields`, and `sap_get_screen_text`.

## Object Chain

```
GP (Business Partner)
 └─ Vertragskonto / Contract Account (CAA1)
     └─ Anschlussobjekt / Connection Object (ES55)
         └─ Verbrauchsstelle / Premise (ES60)
             └─ Anlage / Installation (ES30)
                 └─ Einzugsbeleg / Move-In Document (EC50)
```

## Prerequisites

- SAP session is logged in and ready
- Authorization for transactions BP, CAA1, ES55, ES60, ES30, EC50
- ISU/Utilities module is active in the system
- Required Customizing is in place (number ranges, control parameters, etc.)

## Step 1: Create a Business Partner (BP)

See the **create_business_partner** prompt for the full recipe. Assign the role "Vertragspartner" (contract partner). Make sure to set `Land` (country) = `DE` and a valid `Region`.

After saving, note the GP number from the status bar.

## Step 2: Create a Contract Account (CAA1)

```
sap_transaction("CAA1")
```

Fill the initial screen with the GP number from Step 1:

```
sap_fill_form({
    "Geschaeftspartner": "<GP-Nummer aus Schritt 1>",
    "Vtrgskontotyp": "01",
    "Buchungskreis": "0001"
})
```

Press Enter to proceed to the detail screen:

```
sap_keyboard("Enter")
```

On the detail screen, fill payment and tax fields. Use `sap_discover_fields()` to find the exact labels on your system:

```
sap_fill_form({
    "Toleranzgruppe": "0001",
    "Zahlungskondition": "0001"
})
```

Navigate to the correspondence tab and fill:

```
sap_fill_form({
    "Rechnungsformular": "IS_U_BILL",
    "BuchungskreisGruppe": "0001",
    "Standardbuchungskreis": "0001"
})
```

Save and note the contract account number:

```
sap_keyboard("Control+S")
sap_read_status_bar()
```

> **Note:** The values `01`, `0001`, `IS_U_BILL` are system-specific examples. Use `sap_discover_fields()` to see available options and verify with your system configuration.

## Step 3: Create a Connection Object (ES55)

```
sap_transaction("ES55")
```

Fill address fields. The label "Bezeichnung" (description) may be ambiguous on this screen. If `sap_fill_form` by label fails, fall back to the CSS selector for the specific field:

```
sap_fill_form({
    "#M0\\:46\\:\\:\\:1\\:22": "Mein Anschlussobjekt",
    "input[lsdata*='STREET']": "Hauptstrasse",
    "input[lsdata*='HOUSE_NUM1']": "1",
    "input[lsdata*='POST_CODE1']": "10115",
    "input[lsdata*='CITY1']": "Berlin",
    "input[lsdata*='COUNTRY']": "DE",
    "Region": "BE"
})
```

> **Tip:** Always try `sap_discover_fields()` first. Only use CSS selectors when labels are ambiguous or don't work.

Save and note the connection object number:

```
sap_keyboard("Control+S")
sap_read_status_bar()
```

## Step 4: Create a Premise (ES60)

```
sap_transaction("ES60")
```

Fill the premise with the connection object number from Step 3:

```
sap_fill_form({
    "Anschlussobjekt": "<Nummer aus Schritt 3>",
    "Strassenerg. 1": "Hauptstrasse 1"
})
```

Save and note the premise number:

```
sap_keyboard("Control+S")
sap_read_status_bar()
```

## Step 5: Create an Installation (ES30) -- Critical Step

This is the most complex step. **Always use a template installation** if one exists in the system.

```
sap_transaction("ES30")
```

Fill the initial fields. The "Stichtag" (key date) field may require a CSS selector:

```
sap_fill_form({
    "Vorlage Anlage": "4000000000",
    "Sparte": "01",
    "#M0\\:46\\:\\:\\:3\\:17": "01.01.2025",
    "Verbrauchsstelle": "<Nummer aus Schritt 4>"
})
```

Press Enter to load the detail screen:

```
sap_keyboard("Enter")
```

> **Important:** The value `4000000000` for "Vorlage Anlage" is a system-specific example. Ask your SAP admin for a valid template installation number, or omit the template and fill all time-dependent data manually.

### Time-Dependent Data Table (Without Template)

If no template is used, you must fill the "Zeitabhaengige Daten" (time-dependent data) table. This table uses special SPAN-based cells that require careful interaction:

1. **Locate the cell** -- cells have IDs like `M0:46:1[1,3]_c` with `role="textbox"`
2. **Activate the cell** -- double-click via JavaScript is needed:
    ```
    browser_evaluate("var el = document.getElementById('M0:46:1[1,3]_c'); el.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}))")
    ```
3. **Type the value** -- focus the inner input element and type with `browser_keyboard`
4. **For F4 (value help) dialogs** -- use **keyboard only** (ArrowDown + Enter), NOT JavaScript clicks, to avoid "control not found on batch step" errors

Without a template, typical fields include:

| Field                     | Example Value | Description                            |
| ------------------------- | ------------- | -------------------------------------- |
| AbrKl (Abrechnungsklasse) | `N`           | Billing class -- verify in your system |
| Tariftyp                  | `SNJNS-001`   | Tariff type -- system-specific         |
| Ableseeinheit             | `STROM01`     | Meter reading unit -- system-specific  |

Save and note the installation number:

```
sap_keyboard("Control+S")
sap_read_status_bar()
```

## Step 6: Create a Move-In Document (EC50)

```
sap_transaction("EC50")
```

The label "Vertragskonto" may be ambiguous. Use CSS selector if needed:

```
sap_fill_form({
    "Geschaeftspartner": "<GP-Nummer aus Schritt 1>",
    "#M0\\:46\\:1\\:\\:7\\:17": "<Vertragskonto aus Schritt 2>",
    "Einzugsdatum": "01.01.2025",
    "Verbrauchsstelle": "<Nummer aus Schritt 4>"
})
```

Press Enter:

```
sap_keyboard("Enter")
```

A warning "keine Geraete zugeordnet" (no devices assigned) may appear. Press F3 to go back:

```
sap_keyboard("F3")
```

### Activate the Contracts Tab First

Before filling contract-related fields, activate the "Vertraege" (contracts) tab. If tabs are not visible, activate via JavaScript:

```
browser_evaluate("document.getElementById('M0:46:1:1::0:4-title').click()")
```

Then fill:

```
sap_fill_form({
    "Kontenfindungsmerkmal": "01",
    "Mahnverfahren": "01"
})
```

> **Note:** The tab element ID and field values are system-specific. Use `sap_discover_fields()` and `sap_get_screen_text()` to verify.

Save:

```
sap_keyboard("Control+S")
sap_read_status_bar()
```

A sequence of dialogs may follow:

1. **"USt-Identnummer" info** -- press Enter to continue
2. **Print dialog** -- press "Abbrechen" (Cancel) or Enter
3. **Confirmation** -- press "Ja" (Yes) if prompted

```
sap_keyboard("Enter")
sap_keyboard("Enter")
```

## Known Pitfalls and Workarounds

| Problem                                         | Workaround                                                                                |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `sap_keyboard("Ctrl+S")` fails                  | Use `browser_keyboard` with key `Control+s`                                               |
| ES30 table cells not editable                   | Double-click cell via JavaScript, then focus inner input                                  |
| F4 value-help via JS click causes backend error | Use keyboard only: ArrowDown + Enter                                                      |
| Backend error popup blocks interaction          | Hide popup via JS: `popupWindowMessage.style.display='none'` then click `popupButtonSync` |
| Fields on non-visible tab not fillable          | Activate the tab first (click tab title via JS or label)                                  |
| Session hangs with dialog                       | Use `sap_session_close` and start a new session                                           |
| ABAP short dump in EC50                         | Do not click tabs while a backend error dialog is active                                  |

## Error Handling

### General Approach

After every save, always check the status bar:

```
sap_read_status_bar()
```

If an error occurs:

1. Read the full screen text: `sap_get_screen_text()`
2. Discover available fields: `sap_discover_fields()`
3. Fix the issue and retry

### Common Errors

- **"Pflichtfeld nicht gefuellt"** -- a required field is missing. Use `sap_discover_fields()` to find it.
- **"Nummernkreis erschoepft"** -- number range exhausted. Contact your SAP admin.
- **Backend error popup** -- dismiss via JavaScript (see table above) and retry.

## Key Takeaway

This workflow uses only generic tools. The same pattern -- open transaction, discover fields, fill form, save, check status bar -- applies to every step. All example values are **system-specific** and must be verified against your SAP configuration. Use `sap_discover_fields()` liberally to find the correct field labels and selectors on your system.
