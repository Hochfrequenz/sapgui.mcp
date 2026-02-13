---
description: Create a business partner (person or organization) by composing generic SAP tools
---

# Create a Business Partner

## Overview

This recipe demonstrates how to automate a complete SAP workflow by composing generic tools. There is no dedicated "create BP" tool -- instead, you combine `sap_transaction`, `sap_keyboard`, `sap_fill_form`, and `sap_read_status_bar` to create a business partner from scratch.

This pattern works for **any SAP transaction**, not just BP.

## Prerequisites

- SAP session is logged in and ready
- Authorization for transaction BP
- Know the BP type: person (F5) or organization (F6)

## Steps

### Step 1: Open the BP Transaction

```
sap_transaction("BP")
```

Verify the screen shows "Geschaeftspartner pflegen" (DE) or "Maintain Business Partner" (EN).

### Step 2: Create a New Business Partner

For a **person** (natural person):

```
sap_keyboard("F5")
```

For an **organization** (company):

```
sap_keyboard("F6")
```

A popup may appear asking to confirm the BP type. If so, confirm it.

### Step 3: Select Grouping

A grouping dropdown may appear that determines the BP number range. Select the appropriate grouping for your scenario. Use `sap_discover_fields()` to find the dropdown if needed.

### Step 4: Fill the Form Fields

Use `sap_fill_form` to fill all fields in one call. This is much faster than filling fields individually.

**Person fields:**

```
sap_fill_form({
    "Anrede": "Herr",
    "Vorname": "Max",
    "Nachname": "Mustermann",
    "Strasse": "Hauptstrasse",
    "Hausnr.": "1",
    "Postleitzahl": "10115",
    "Ort": "Berlin",
    "Land": "DE"
})
```

**Organization fields:**

```
sap_fill_form({
    "Name 1": "Musterfirma GmbH",
    "Strasse": "Industriestr.",
    "Hausnr.": "42",
    "Postleitzahl": "80331",
    "Ort": "Muenchen",
    "Land": "DE"
})
```

**Tip:** Field labels vary by system language and configuration. If `sap_fill_form` can't find a field by label, use `sap_discover_fields()` to see what's available on the current screen.

### Step 5: Save

```
sap_keyboard("Control+S")
```

### Step 6: Check the Result

```
sap_read_status_bar()
```

**On success:** The status bar shows "Geschaeftspartner XXXXXXXXXX angelegt" with the new BP number.

**On error:** See Error Handling below.

### Step 7: Handle Missing Obligatory Fields

If save fails with "Pflichtfeld nicht gefuellt" (required field not filled):

1. Read the screen to identify what's missing:

    ```
    sap_get_screen_text()
    ```

2. Look for fields marked as required or highlighted

3. Fill the missing fields:

    ```
    sap_fill_form({"Missing Field Label": "value"})
    ```

4. Try saving again:
    ```
    sap_keyboard("Control+S")
    sap_read_status_bar()
    ```

### Step 8: Verify the Created BP

**Option A: Display the BP in the same transaction**

```
sap_transaction("BP")
```

Enter the BP number and display it to confirm the data.

**Option B: Check the database table directly**

```
sap_se16_query(table="BUT000", filters={"PARTNER": "XXXXXXXXXX"})
```

This returns the BP master data record from the database.

### Step 9: Create Another BP

After a successful save, start over from Step 1:

```
sap_transaction("BP")
```

Do NOT try to navigate back -- just restart the transaction.

## Error Handling

### "Pflichtfeld nicht gefuellt" / "Required field not filled"

- Use `sap_get_screen_text()` to find which field is missing
- Required fields depend on the BP role and system configuration
- Common missing fields: Anrede (title), Suchbegriff (search term)

### "Dublette gefunden" / "Duplicate found"

- SAP found a similar BP via duplicate check
- Check if the BP already exists before creating a new one
- Can be overridden if an intentional duplicate

### "Nummernkreis erschoepft" / "Number range exhausted"

- Contact your SAP admin to extend the number range
- Or try a different BP grouping

## Key Takeaway

This workflow uses only generic tools: `sap_transaction`, `sap_keyboard`, `sap_fill_form`, `sap_read_status_bar`, `sap_get_screen_text`, and `sap_se16_query`. The same pattern applies to **any** SAP transaction -- open it, fill fields, save, check the result.
