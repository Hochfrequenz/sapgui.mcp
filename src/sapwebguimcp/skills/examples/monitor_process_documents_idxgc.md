# Skill: Monitor Process Documents (Transaction /IDXGC/PDOCMON01)

## Overview

Monitor market communication process documents (PDOC) in SAP IS-U / S/4HANA Utilities.
Process documents track the status of German market communication processes like:

- GPKE (Lieferantenwechsel Strom / Supplier switch electricity)
- MaBiS (Bilanzkreisabrechnung / Balance group settlement)
- WiM (Wechselprozesse Messwesen / Meter operator switch)
- GeLi Gas (Lieferantenwechsel Gas / Supplier switch gas)

## Prerequisites

- User logged into SAP with IS-U / S/4HANA Utilities
- Authorization for `/IDXGC/` transactions
- IDEX/IDXGC framework configured (German market communication)
- Understanding of market roles (Lieferant, Netzbetreiber, MSB)

## When to Use

Use this skill for:

- Monitoring incoming/outgoing market messages
- Troubleshooting failed process documents
- Checking status of supplier switches (Lieferantenwechsel)
- Verifying meter operator changes
- Analyzing MaBiS balancing processes

## Adaptive Field Discovery

### Label Reference (DE/EN)

| Purpose          | German Label                | English Label                      |
| ---------------- | --------------------------- | ---------------------------------- |
| Process Document | Prozessdokument, PDOC       | Process Document                   |
| Process Type     | Prozessart                  | Process Type                       |
| Status           | Status                      | Status                             |
| Message Type     | Nachrichtentyp              | Message Type                       |
| Market Partner   | Marktpartner                | Market Partner                     |
| MeLo/MaLo        | Messlokation, Marktlokation | Metering Location, Market Location |
| Creation Date    | Erstellungsdatum            | Creation Date                      |
| Direction        | Richtung                    | Direction                          |
| Error            | Fehler                      | Error                              |

### Process Status Values

| Status Code | German         | English     | Meaning         |
| ----------- | -------------- | ----------- | --------------- |
| 01          | Neu            | New         | Just created    |
| 02          | In Bearbeitung | In Progress | Being processed |
| 03          | Erfolgreich    | Successful  | Completed OK    |
| 04          | Fehlerhaft     | Error       | Failed          |
| 05          | Storniert      | Cancelled   | Cancelled       |

## Workflow

### Step 1: Start Transaction

```
sap_transaction("/IDXGC/PDOCMON01")  # Inbound process monitoring
# or
sap_transaction("/IDXGC/PDOCMON02")  # Outbound process monitoring

sap_get_screen_text()  # Verify selection screen loaded
```

### Step 2: Set Selection Criteria

```
sap_get_screen_text()  # Identify filter fields

# Filter by date range
sap_fill(field_near_label="Erstellungsdatum", value="01.12.2024")
sap_fill(field_near_label="bis", value="19.12.2024")

# Filter by process type (optional)
# GPKE processes: ZMCPD_GPKE_*
# MaBiS processes: ZMCPD_MABIS_*
# WiM processes: ZMCPD_WIM_*
sap_fill(field_near_label="Prozessart", value="ZMCPD_GPKE*")

# Filter by status (optional)
sap_fill(field_near_label="Status", value="04")  # Only errors

# Filter by MaLo/MeLo (optional)
sap_fill(field_near_label="Marktlokation", value="DE000...")
```

### Step 3: Execute Search

```
sap_press_key("F8")  # Execute
sap_get_screen_text()  # Check results or error
```

### Step 4: Analyze Results

```
# Read the ALV table with results
sap_read_table()

# Results contain:
# - PDOC number
# - Process type
# - Status
# - Market partner
# - MaLo/MeLo
# - Timestamps
# - Error messages (if status = error)
```

### Step 5: View Process Document Details

```
# Double-click or select a row and press Enter to see details
sap_click(row=N)  # Select specific row
sap_press_key("Enter")

sap_get_screen_text()  # Read detail screen

# Detail screen shows:
# - Process header data
# - Linked messages (UTILMD, MSCONS, etc.)
# - Process steps and their status
# - Error log
```

### Step 6: View Linked Messages

```
# From detail screen, navigate to messages
sap_get_screen_text()  # Look for "Nachrichten" / "Messages" section

# Each PDOC can have multiple messages:
# - UTILMD: Master data exchange
# - MSCONS: Meter reading data
# - INVOIC: Billing data
# - REMADV: Payment advice
```

## Error Handling

### "Keine Daten gefunden" / "No data found"

- Broaden search criteria (larger date range)
- Remove specific filters
- Check if process documents exist at all

### "Keine Berechtigung" / "No authorization"

- User needs authorization for `/IDXGC/` transactions
- Check authorization object `IDEX_PDOC`

### Common PDOC Errors

| Error Pattern       | Cause                   | Resolution                   |
| ------------------- | ----------------------- | ---------------------------- |
| MaLo nicht gefunden | Market location unknown | Check MaLo master data       |
| Partner ungültig    | Invalid market partner  | Verify partner in /IDXGC/BPM |
| Doppelte Nachricht  | Duplicate message       | Check for existing process   |
| Zeitfenster         | Timing conflict         | Check process dates          |

## German Market Communication Specifics

### GPKE Process Types (Electricity Supply)

| Process            | Description                     |
| ------------------ | ------------------------------- |
| ZMCPD_GPKE_LIEFBEG | Lieferbeginn (Start of Supply)  |
| ZMCPD_GPKE_LIEFEND | Lieferende (End of Supply)      |
| ZMCPD_GPKE_KUNDW   | Kundenwechsel (Customer Switch) |

### MaBiS Process Types (Balancing)

| Process         | Description                              |
| --------------- | ---------------------------------------- |
| ZMCPD_MABIS_SLP | SLP-Bilanzierung (Standard Load Profile) |
| ZMCPD_MABIS_RLM | RLM-Bilanzierung (Interval Metering)     |

### WiM Process Types (Meter Operation)

| Process          | Description                       |
| ---------------- | --------------------------------- |
| ZMCPD_WIM_MSBBEG | MSB-Beginn (Meter Operator Start) |
| ZMCPD_WIM_MSBEND | MSB-Ende (Meter Operator End)     |

### Market Partner Roles

| Role | German                      | Description                  |
| ---- | --------------------------- | ---------------------------- |
| LF   | Lieferant                   | Supplier                     |
| NB   | Netzbetreiber               | Distribution System Operator |
| MSB  | Messstellenbetreiber        | Meter Operator               |
| BKV  | Bilanzkreisverantwortlicher | Balance Responsible Party    |
| ÜNB  | Übertragungsnetzbetreiber   | Transmission System Operator |

## Related Transactions

| Transaction      | Purpose                            |
| ---------------- | ---------------------------------- |
| /IDXGC/PDOCMON01 | Monitor inbound process documents  |
| /IDXGC/PDOCMON02 | Monitor outbound process documents |
| /IDXGC/BPM       | Market partner maintenance         |
| /IDXGC/DISP_CUST | Display customizing                |
| /IDXGC/MSG_MON   | Message monitoring                 |

## Example Dialogue

```
User: Zeige mir alle fehlerhaften GPKE-Prozesse der letzten Woche

Claude: Ich öffne die PDOC-Überwachung für eingehende Prozesse.
[calls sap_transaction("/IDXGC/PDOCMON01")]

[calls sap_get_screen_text()]
Die Selektionsmaske ist geladen.

[fills date range: 12.12.2024 - 19.12.2024]
[fills process type: ZMCPD_GPKE*]
[fills status: 04 (Fehlerhaft)]

[calls sap_press_key("F8")]

[calls sap_read_table()]

Ich habe 3 fehlerhafte GPKE-Prozesse gefunden:

| PDOC | Prozessart | MaLo | Fehler |
|------|------------|------|--------|
| 100001 | LIEFBEG | DE00014... | MaLo nicht gefunden |
| 100002 | KUNDW | DE00089... | Partner ungültig |
| 100003 | LIEFEND | DE00023... | Zeitfenster-Konflikt |

Soll ich die Details zu einem dieser Prozesse anzeigen?
```

## Sources

- [SAP Learning: Market Communication Architecture](https://learning.sap.com/learning-journeys/transitioning-to-sap-s-4hana-for-utilities/analyzing-and-applying-sap-market-communication-architecture-for-utilities)
- [SAP Community: Introducing APE](https://community.sap.com/t5/sap-for-utilities-blog-posts/introducing-application-process-engine-ape-latest-sap-solution-for-choice/ba-p/13548853)
- [Prologa: Market Communication](https://prologa.com/sap-solution/market-communication/)
