# Skill: Create Contract Account (Transaction CAA1)

## Overview

Create a contract account (Vertragskonto) for billing and payment processing in SAP IS-U.
The contract account links the business partner to their financial transactions
and determines collection/payment rules.

In German utilities, the contract account is the central FI-CA object for:

- Billing document posting (Abrechnungsbelege)
- Payment processing (Zahlungsverkehr)
- Dunning (Mahnwesen)
- Account balance management

## Prerequisites

- Business partner already created (need BP number)
- User authorized for transaction CAA1
- Know the contract account category (Vertragskontenkategorie) to use
- Know the company code (Buchungskreis)

## Adaptive Field Discovery

### Label Reference (DE/EN)

| Purpose           | German Label            | English Label          |
| ----------------- | ----------------------- | ---------------------- |
| Business Partner  | Geschäftspartner, GP    | Business Partner, BP   |
| Contract Account  | Vertragskonto, VK       | Contract Account, CA   |
| Account Category  | Vertragskontenkategorie | Contract Acc. Category |
| Company Code      | Buchungskreis           | Company Code           |
| Account Name      | Kontoname               | Account Name           |
| Correspondence    | Korrespondenz           | Correspondence         |
| Payment Method    | Zahlweg                 | Payment Method         |
| Bank Details      | Bankverbindung          | Bank Details           |
| Dunning Procedure | Mahnverfahren           | Dunning Procedure      |
| Dunning Area      | Mahnbereich             | Dunning Area           |
| Account Determ.   | Kontenfindung           | Account Determination  |

## Workflow

### Step 1: Start Transaction

```
sap_transaction("CAA1")
sap_get_screen_text()  # Verify "Vertragskonto anlegen" or "Create Contract Account"
```

### Step 2: Enter Business Partner

```
sap_get_screen_text()  # Find "Geschäftspartner" field

# Enter the BP number from previous creation
sap_fill(field_near_label="Geschäftspartner", value="1234567890")
```

### Step 3: Select Contract Account Category

```
sap_get_screen_text()  # Find "Vertragskontenkategorie"

# Categories are configured per system, examples:
# - Haushaltskunde (residential)
# - Gewerbekunde (commercial)
# - Industriekunde (industrial)
sap_fill(field_near_label="Kontenkategorie", value="HH01")
```

### Step 4: Enter Basic Account Data

```
sap_get_screen_text()

# Account name (may default from BP)
sap_fill(field_near_label="Kontoname", value="Mustermann, Max")

# Account determination ID (for GL posting)
sap_fill(field_near_label="Kontenfindung", value="01")
```

### Step 5: Enter Payment Data

Navigate to payment tab if needed.

```
sap_get_screen_text()  # Look for "Zahlung" / "Payment" tab

# Payment method
sap_fill(field_near_label="Zahlweg", value="U")  # Überweisung (bank transfer)

# For direct debit (Lastschrift):
# sap_fill(field_near_label="Zahlweg", value="L")
# Then fill bank details:
# sap_fill(field_near_label="IBAN", value="DE89370400440532013000")
# sap_fill(field_near_label="BIC", value="COBADEFFXXX")
```

### Step 6: Enter Dunning Data

Navigate to dunning tab if needed.

```
sap_get_screen_text()  # Look for "Mahnung" / "Dunning" tab

sap_fill(field_near_label="Mahnverfahren", value="01")
sap_fill(field_near_label="Mahnbereich", value="0001")
```

### Step 7: Save

```
sap_press_key("Control+S")
sap_read_status_bar()  # Should show "Vertragskonto XXXXXXXXXXXX angelegt"
                       # or "Contract Account XXXXXXXXXXXX created"
```

Capture the contract account number from the status message.

## Error Handling

### "Geschäftspartner existiert nicht" / "Business partner does not exist"

- Verify BP number is correct (check for leading zeros)
- Check BP has correct roles assigned
- BP may need to be extended to company code

### "Ungültige Kontenkategorie" / "Invalid account category"

- Check customizing for allowed categories
- Verify category is active for company code
- SPRO path: FI-CA > Contract Accounts > Configure Contract Account Categories

### "Nummernkreis nicht gefunden" / "Number range not found"

- Number range not configured for account category
- SPRO path: FI-CA > Contract Accounts > Define Number Ranges

### "Kontenfindung ungültig" / "Invalid account determination"

- Account determination ID not configured
- Check SPRO: FI-CA > Basic Functions > Account Determination

## German Utilities Specifics

### IS-U Contract Structure

In IS-U, the hierarchy is:

```
Business Partner (Geschäftspartner)
  └── Contract Account (Vertragskonto)
        └── Contract (Vertrag)
              └── Installation (Anlage)
                    └── Device (Gerät)
```

### SEPA Integration

For German utilities with SEPA direct debit:

- Mandate reference (Mandatsreferenz) may be required
- Mandate date and status tracking
- Pre-notification settings (Vorabankündigung)

### MaKo Considerations

For market communication (Marktkommunikation):

- Contract account is referenced in INVOIC messages
- REMADV payment advice references contract account
- Balance group (Bilanzkreis) may be linked for balancing

## Related Transactions

| Transaction | Purpose                                           |
| ----------- | ------------------------------------------------- |
| CAA2        | Change Contract Account (Vertragskonto ändern)    |
| CAA3        | Display Contract Account (Vertragskonto anzeigen) |
| FPL9        | Display Line Items (Einzelposten anzeigen)        |
| FPE1        | Post Document (Beleg buchen)                      |

## Example Dialogue

```
User: Erstelle ein Vertragskonto für den Geschäftspartner 1234567890

Claude: Ich öffne die Transaktion CAA1 zur Vertragskonto-Anlage.
[calls sap_transaction("CAA1")]

[calls sap_get_screen_text()]
Die Maske "Vertragskonto anlegen" ist geladen.

[fills: Geschäftspartner=1234567890]
[fills: Vertragskontenkategorie=HH01]

Welchen Zahlweg soll ich eintragen?
- Überweisung (U)
- Lastschrift (L) - dann benötige ich IBAN und BIC
- Bar (B)

User: Lastschrift mit IBAN DE89370400440532013000

Claude: [navigates to payment tab]
[fills: Zahlweg=L, IBAN=DE89370400440532013000]

[calls sap_press_key("Control+S")]
[calls sap_read_status_bar()]

Das Vertragskonto wurde erfolgreich angelegt.
Nummer: 200000012345

Soll ich als nächstes einen Vertrag (EC50N) oder einen Einzug (Move-In) erstellen?
```

## Sources

- [SAP TCodes: CAA1 Create Contract Account](https://www.sap-tcodes.org/tcode/caa1.html)
- [SAP Community: Configure Contract Accounts](https://answers.sap.com/questions/7579129/configure-contract-accounts.html)
- [SAP Community: Creating Contract Account using BAPI](https://community.sap.com/t5/enterprise-resource-planning-q-a/creating-contract-account-caa1-using-suitable-bapi/qaq-p/12735411)
