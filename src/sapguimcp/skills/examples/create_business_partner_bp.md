# Skill: Create Business Partner (Transaction BP)

## Overview

Create a business partner for utility customer scenarios using transaction BP.
Business partners are central master data in SAP IS-U and S/4HANA Utilities -
they represent customers (Vertragspartner), vendors, or contacts.

In German utilities (IS-U), the business partner is linked to:

- Contract Accounts (Vertragskonten) for billing
- Contracts (Verträge) for service delivery
- PODs (Zählpunkte/MaLo) via installations

## Prerequisites

- User logged into SAP
- Authorization for transaction BP
- Know the BP grouping to use (determines number range)
- Know required BP roles:
    - `FLCU00` - Customer (Financial Accounting)
    - IS-U specific: Contract Partner roles

## Adaptive Field Discovery

This skill uses adaptive field discovery. The agent should:

1. Call `sap_get_screen_text()` after each screen loads
2. Look for known labels in the returned text
3. Match fields by proximity to labels

### Label Reference (DE/EN)

| Purpose          | German Label      | English Label  |
| ---------------- | ----------------- | -------------- |
| Title/Salutation | Anrede            | Title          |
| First Name       | Vorname           | First Name     |
| Last Name        | Nachname          | Last Name      |
| Name (Org)       | Name 1, Name 2    | Name 1, Name 2 |
| Street           | Straße            | Street         |
| House Number     | Hausnummer        | House Number   |
| Postal Code      | Postleitzahl, PLZ | Postal Code    |
| City             | Ort               | City           |
| Country          | Land              | Country        |
| Language         | Sprache           | Language       |
| Search Term      | Suchbegriff       | Search Term    |
| BP Role          | Rolle             | Role           |

## Workflow

### Step 1: Start Transaction

```
sap_transaction("BP")
sap_get_screen_text()  # Verify "Geschäftspartner pflegen" or "Maintain Business Partner"
```

### Step 2: Select Create Mode

- For natural person (Person):
    - Look for: "Person anlegen" / "Create Person"
    - Or press F5
- For organization (Organisation):
    - Look for: "Organisation anlegen" / "Create Organization"
    - Or press F6

```
sap_get_screen_text()  # Find button labels
sap_press_key("F5")     # Create Person
# or
sap_press_key("F6")     # Create Organization
```

### Step 3: Select Grouping

The grouping dropdown determines the BP number range.

```
sap_get_screen_text()  # Look for "Gruppierung" / "Grouping"
# Select appropriate grouping from dropdown
```

### Step 4: Enter General Data and Address

There are two ways to fill the form fields:

#### Option A: Batch Fill (Recommended - Much Faster)

Use `sap_fill_form` to fill all fields in a single call. This is ~10x faster
than filling fields one by one because it executes everything in one browser round-trip.

```
# Fill person fields using CSS selectors that target SAP field IDs
sap_fill_form({
    "input[lsdata*='NAME_FIRST']": "Max",
    "input[lsdata*='NAME_LAST']": "Mustermann",
    "input[lsdata*='STREET']": "Hauptstraße",
    "input[lsdata*='HOUSE_NUM1']": "123",
    "input[lsdata*='POST_CODE1']": "12345",
    "input[lsdata*='CITY1']": "Berlin"
})
```

Keys can be:

- CSS selectors using lsdata attribute (reliable, works across systems)
- Example patterns: `input[lsdata*='NAME_FIRST']`, `input[lsdata*='STREET']`

#### Option B: One-by-One Fill (Slower, More Control)

Fill fields individually when you need to wait between fields or handle
dynamic field behavior:

```
# Use sap_set_field for single fields (returns matched selector for debugging)
sap_set_field(label="input[lsdata*='NAME_FIRST']", value="Max")
sap_set_field(label="input[lsdata*='NAME_LAST']", value="Mustermann")
# ... etc
```

This approach is slower but gives more control when fields have
dependencies or trigger UI updates. It also returns the matched selector.

### Step 5: Add Business Partner Role (for IS-U)

For utilities, add appropriate roles:

```
sap_get_screen_text()  # Look for role section

# Add Contract Partner role for IS-U
# Role codes vary by configuration
```

### Step 6: Save

```
sap_press_key("Control+S")
sap_read_status_bar()  # Should show "Geschäftspartner XXXXXXXXXX angelegt"
                       # or "Business Partner XXXXXXXXXX created"
```

Capture the BP number from the status message.

### Step 7: Start Over

If you want to create another business partner, simply start again with step 1

```
sap_transaction("BP")
```

Do NOT try to navigate back after the success message appeared - the UI is broken.
Just focus the OK_CODE transaction field and start over by starting the transaction.

## Error Handling

### "Nummernkreis erschöpft" / "Number range exhausted"

- Contact basis admin to extend number range
- Or use different BP grouping

### "Dublette gefunden" / "Duplicate found"

- System found similar BP via duplicate check
- Check if BP already exists
- Can override if intentional duplicate

### "Pflichtfeld nicht gefüllt" / "Required field not filled"

- Use `sap_get_screen_text()` to identify which field is missing
- Look for fields marked with \* or highlighted

## German Utilities Specifics

### IS-U Integration

When creating BPs for IS-U:

1. BP must have appropriate roles for FICA posting
2. BP will be linked to Contract Account (Vertragskonto)
3. Consider MaKo (Marktkommunikation) requirements if BP is a market partner

### MaKo Market Partners

For German market communication (GPKE, MaBiS, WiM):

- Market partners (Lieferant, Netzbetreiber, MSB) need specific attributes
- Partner identification via BDEW codes
- See `/IDXGC/` transactions for market partner setup

## Example Dialogue

```
User: Erstelle einen neuen Geschäftspartner für Max Mustermann, Berlin

Claude: Ich öffne die Transaktion BP zur Geschäftspartner-Pflege.
[calls sap_transaction("BP")]

Die Maske "Geschäftspartner pflegen" ist geladen. Ich lege eine Person an.
[calls sap_press_key("F5")]

[calls sap_get_screen_text() to identify fields]
Ich sehe die Eingabefelder für die Personendaten.

[fills: Anrede=Herr, Vorname=Max, Nachname=Mustermann]
[fills address: Straße=Hauptstraße 1, PLZ=10115, Ort=Berlin, Land=DE]

[calls sap_press_key("Control+S")]
[calls sap_read_status_bar()]

Der Geschäftspartner wurde erfolgreich angelegt.
Nummer: 1234567890

Soll ich auch ein Vertragskonto (CAA1) für diesen Partner erstellen?
```

## Sources

- [SAP Community: How to create a BP](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/how-to-create-a-bp-business-partner/ba-p/13394450)
- [SAP Community: BP Complete Configuration Guide](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/business-partner-bp-complete-configuration-guide-in-sap-s4-hana/ba-p/14021389)
