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
sap_keyboard("F5")     # Create Person
# or
sap_keyboard("F6")     # Create Organization
```

### Step 3: Select Grouping

The grouping dropdown determines the BP number range.

```
sap_get_screen_text()  # Look for "Gruppierung" / "Grouping"
# Select appropriate grouping from dropdown
```

### Step 4: Enter General Data (Person)

```
sap_get_screen_text()  # Identify field positions

# Fill fields - use adaptive matching:
# Find "Anrede" or "Title" label, fill adjacent field
sap_fill(field_near_label="Anrede", value="Herr")
sap_fill(field_near_label="Vorname", value="Max")
sap_fill(field_near_label="Nachname", value="Mustermann")
```

### Step 5: Enter Address Data

Navigate to address section/tab if needed.

```
sap_get_screen_text()  # Look for "Adresse" / "Address" tab or section

sap_fill(field_near_label="Straße", value="Hauptstraße")
sap_fill(field_near_label="Hausnummer", value="123")
sap_fill(field_near_label="PLZ", value="12345")
sap_fill(field_near_label="Ort", value="Berlin")
sap_fill(field_near_label="Land", value="DE")
```

### Step 6: Add Business Partner Role (for IS-U)

For utilities, add appropriate roles:

```
sap_get_screen_text()  # Look for role section

# Add Contract Partner role for IS-U
# Role codes vary by configuration
```

### Step 7: Save

```
sap_keyboard("Control+S")
sap_read_status_bar()  # Should show "Geschäftspartner XXXXXXXXXX angelegt"
                       # or "Business Partner XXXXXXXXXX created"
```

Capture the BP number from the status message.

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
[calls sap_keyboard("F5")]

[calls sap_get_screen_text() to identify fields]
Ich sehe die Eingabefelder für die Personendaten.

[fills: Anrede=Herr, Vorname=Max, Nachname=Mustermann]
[fills address: Straße=Hauptstraße 1, PLZ=10115, Ort=Berlin, Land=DE]

[calls sap_keyboard("Control+S")]
[calls sap_read_status_bar()]

Der Geschäftspartner wurde erfolgreich angelegt.
Nummer: 1234567890

Soll ich auch ein Vertragskonto (CAA1) für diesen Partner erstellen?
```

## Sources

- [SAP Community: How to create a BP](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/how-to-create-a-bp-business-partner/ba-p/13394450)
- [SAP Community: BP Complete Configuration Guide](https://community.sap.com/t5/enterprise-resource-planning-blog-posts-by-members/business-partner-bp-complete-configuration-guide-in-sap-s4-hana/ba-p/14021389)
