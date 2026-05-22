#!/usr/bin/env python3
"""Add inline SE16 results to the transaction catalog.

This script adds transaction codes that were returned inline (not saved to files)
during the scraping session.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from sapguimcp.catalog.models import TransactionCatalog, TransactionInfo, detect_area

# Inline results from the scraping session
INLINE_RESULTS = [
    # VL* (154 total, showing key ones)
    {"TCODE": "VL00", "PGMNA": "MENUVL00", "TTEXT": "Versand"},
    {"TCODE": "VL01", "PGMNA": "SAPMV50A", "TTEXT": "Anlegen Auslieferung"},
    {"TCODE": "VL01N", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung zum Kd.auftrag anlegen"},
    {"TCODE": "VL01NO", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung ohne Bezug anlegen"},
    {"TCODE": "VL02", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung ändern"},
    {"TCODE": "VL02N", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung ändern"},
    {"TCODE": "VL02N_B", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung (zur Bestellung) ändern"},
    {"TCODE": "VL02N_EXH", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung ändern (3PL Handling)"},
    {"TCODE": "VL02N_F", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung (PP) ändern"},
    {"TCODE": "VL02N_O", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung (ohne Bezug) ändern"},
    {"TCODE": "VL03", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung anzeigen"},
    {"TCODE": "VL03N", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung anzeigen"},
    {"TCODE": "VL03N_EXH", "PGMNA": "SAPMV50A", "TTEXT": "Auslieferung anzeigen (3PL Handling)"},
    {"TCODE": "VL04", "PGMNA": "RV50SBT1", "TTEXT": "Bearbeiten Liefervorrat"},
    {"TCODE": "VL06", "PGMNA": "WS_DELIVERY_MONITOR", "TTEXT": "Lieferungsmonitor"},
    {"TCODE": "VL06C", "PGMNA": "WS_MONITOR_OUTB_DEL_CONF", "TTEXT": "Liste zu quittierender Auslieferung."},
    {"TCODE": "VL06D", "PGMNA": "WS_MONITOR_OUTB_DEL_DIST", "TTEXT": "Auslieferungen zur Verteilung"},
    {"TCODE": "VL06F", "PGMNA": "WS_MONITOR_OUTB_DEL_FREE", "TTEXT": "Allgemeine Lieferliste Auslieferung"},
    {"TCODE": "VL06G", "PGMNA": "WS_MONITOR_OUTB_DEL_GDSI", "TTEXT": "Liste Warenausgang Auslieferungen"},
    {"TCODE": "VL06I", "PGMNA": "WS_DELIVERY_MONITOR", "TTEXT": "Anlieferungsmonitor"},
    {"TCODE": "VL06O", "PGMNA": "WS_DELIVERY_MONITOR", "TTEXT": "Auslieferungsmonitor"},
    {"TCODE": "VL06P", "PGMNA": "WS_MONITOR_OUTB_DEL_PICK", "TTEXT": "Liste zu kommiss. Auslieferungen"},
    {"TCODE": "VL06T", "PGMNA": "WS_MONITOR_OUTB_DEL_TRAN", "TTEXT": "Liste Transportdispo. Auslieferungen"},
    {"TCODE": "VL09", "PGMNA": "RVV50L09", "TTEXT": "Storno Warenausgang zum Lieferschein"},
    {"TCODE": "VL10", "PGMNA": "", "TTEXT": "Benutzersp. Lieferliste bearbeiten"},
    {"TCODE": "VL10A", "PGMNA": "", "TTEXT": "Versandfällige Kundenaufträge"},
    {"TCODE": "VL10B", "PGMNA": "", "TTEXT": "Versandfällige Bestellungen"},
    {"TCODE": "VL21", "PGMNA": "RVV50L21", "TTEXT": "Warenausgang buchen im Batch"},
    {"TCODE": "VL22", "PGMNA": "WSCDSHOW", "TTEXT": "Änderungsbelege Lieferung anzeigen"},
    {"TCODE": "VL31N", "PGMNA": "SAPMV50A", "TTEXT": "Anlieferung anlegen"},
    {"TCODE": "VL32N", "PGMNA": "SAPMV50A", "TTEXT": "Anlieferung ändern"},
    {"TCODE": "VL33N", "PGMNA": "SAPMV50A", "TTEXT": "Anlieferung anzeigen"},
    {"TCODE": "VL34", "PGMNA": "RM06EANL", "TTEXT": "Arbeitsvorrat Anlieferungen"},
    {"TCODE": "VL71", "PGMNA": "SD70AV2A", "TTEXT": "Nachrichten aus Auslieferungen"},
    # VF* (69 total, showing key ones)
    {"TCODE": "VF00", "PGMNA": "MENUVF00", "TTEXT": "Verkaufsorganisat. & nicht definiert"},
    {"TCODE": "VF01", "PGMNA": "SAPMV60A", "TTEXT": "Fakturen anlegen"},
    {"TCODE": "VF02", "PGMNA": "SAPMV60A", "TTEXT": "Fakturen ändern"},
    {"TCODE": "VF03", "PGMNA": "SAPMV60A", "TTEXT": "Fakturen anzeigen"},
    {"TCODE": "VF04", "PGMNA": "SDBILLDL", "TTEXT": "Fakturavorrat bearbeiten"},
    {"TCODE": "VF05", "PGMNA": "SAPMV65A", "TTEXT": "Liste Fakturen"},
    {"TCODE": "VF05N", "PGMNA": "ERPSLS_BILLDOC_VIEW", "TTEXT": "Liste Fakturen"},
    {"TCODE": "VF06", "PGMNA": "RV60SBAT", "TTEXT": "Batchfakturierung"},
    {"TCODE": "VF11", "PGMNA": "SAPMV60A", "TTEXT": "Stornieren Faktura"},
    {"TCODE": "VF21", "PGMNA": "SAPMV60A", "TTEXT": "Anlegen Rechnungsliste"},
    {"TCODE": "VF22", "PGMNA": "SAPMV60A", "TTEXT": "Rechnungslisten ändern"},
    {"TCODE": "VF23", "PGMNA": "SAPMV60A", "TTEXT": "Rechnungslisten anzeigen"},
    {"TCODE": "VF31", "PGMNA": "SD70AV3A", "TTEXT": "Nachrichten aus Fakturen"},
    # SU* (105 total, showing key ones)
    {"TCODE": "SU0", "PGMNA": "", "TTEXT": "Eigene Benutzerfestwerte pflegen"},
    {"TCODE": "SU01", "PGMNA": "SAPMSUU0", "TTEXT": "Benutzerpflege"},
    {"TCODE": "SU01D", "PGMNA": "SAPMSUU0D", "TTEXT": "Benutzeranzeige"},
    {"TCODE": "SU02", "PGMNA": "SAPMS01C", "TTEXT": "Pflege Berechtigungsprofile"},
    {"TCODE": "SU03", "PGMNA": "SAPMS01C", "TTEXT": "Pflege Berechtigungen"},
    {"TCODE": "SU10", "PGMNA": "SAPMSUU0M", "TTEXT": "Massenpflege Benutzer"},
    {"TCODE": "SU20", "PGMNA": "RSU20_NEW", "TTEXT": "Pflege der Berechtigungsfelder"},
    {"TCODE": "SU21", "PGMNA": "SUSR_SUSO_MAINT", "TTEXT": "Berechtigungsobjektpflege"},
    {"TCODE": "SU22", "PGMNA": "SU2X_MAINTAIN_DEFAULT", "TTEXT": "Vorschlagsdatenpflege (SAP)"},
    {"TCODE": "SU24", "PGMNA": "SU2X_MAINTAIN_DEFAULT", "TTEXT": "Berechtigungsvorschlagsdaten (Cust.)"},
    {"TCODE": "SU3", "PGMNA": "SAPMSUU0O", "TTEXT": "Benutzer eigene Daten pflegen"},
    {"TCODE": "SU53", "PGMNA": "SAPMS01GNEW", "TTEXT": "Auswertung der Berechtigungspüfung"},
    {"TCODE": "SUGR", "PGMNA": "SAPMSUUG", "TTEXT": "Benutzergruppen pflegen"},
    {"TCODE": "SUIM", "PGMNA": "RSUSRSUIM", "TTEXT": "Benutzerinformationssystem"},
    {"TCODE": "SUPC", "PGMNA": "SAPPROFC_NEW", "TTEXT": "Profile zu Rollen"},
    # SD* (71 total, showing key ones)
    {"TCODE": "SD11", "PGMNA": "SAPMUD00", "TTEXT": "Data Modeler"},
    {"TCODE": "SDBE", "PGMNA": "SAPMSDBE", "TTEXT": "SQL-Anweisung erklären"},
    {"TCODE": "SDO1", "PGMNA": "SDORDE01", "TTEXT": "Aufträge des Zeitraums"},
    {"TCODE": "SDQ1", "PGMNA": "SDQUOT01", "TTEXT": "Ablaufende Angebote"},
    {"TCODE": "SDQ2", "PGMNA": "SDQUOT02", "TTEXT": "Abgelaufene Angebote"},
    {"TCODE": "SDV1", "PGMNA": "SDCONT01", "TTEXT": "Ablaufende Kontrakte"},
    {"TCODE": "SDV2", "PGMNA": "SDCONT02", "TTEXT": "Abgelaufene Kontrakte"},
    # VA* (75 total, showing all)
    {"TCODE": "VA00", "PGMNA": "MENUVA00", "TTEXT": "Einstieg Verkauf"},
    {"TCODE": "VA01", "PGMNA": "SAPMV45A", "TTEXT": "Kundenaufträge anlegen"},
    {"TCODE": "VA02", "PGMNA": "SAPMV45A", "TTEXT": "Kundenaufträge ändern"},
    {"TCODE": "VA03", "PGMNA": "SAPMV45A", "TTEXT": "Kundenaufträge anzeigen"},
    {"TCODE": "VA05", "PGMNA": "SD_SALES_DOCUMENT_VIEW", "TTEXT": "Liste Aufträge"},
    {"TCODE": "VA05N", "PGMNA": "SD_SALES_ORDERS_VIEW", "TTEXT": "Liste Aufträge"},
    {"TCODE": "VA06", "PGMNA": "SD_OSO_MONITOR", "TTEXT": "Kundenauftragsmonitor"},
    {"TCODE": "VA07", "PGMNA": "SDBANF02", "TTEXT": "Abgleich Verkauf - Einkauf (Auftrag)"},
    {"TCODE": "VA08", "PGMNA": "SDBANF01", "TTEXT": "Abgleich Verkauf - Einkauf (Org.dat)"},
    {"TCODE": "VA11", "PGMNA": "SAPMV45A", "TTEXT": "Kundenanfragen anlegen"},
    {"TCODE": "VA12", "PGMNA": "SAPMV45A", "TTEXT": "Kundenanfragen ändern"},
    {"TCODE": "VA13", "PGMNA": "SAPMV45A", "TTEXT": "Anfrage anzeigen"},
    {"TCODE": "VA15", "PGMNA": "SD_SALES_DOCUMENT_VA15", "TTEXT": "Liste der Kundenanfragen"},
    {"TCODE": "VA21", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufsangebote anlegen"},
    {"TCODE": "VA22", "PGMNA": "SAPMV45A", "TTEXT": "Angebote ändern"},
    {"TCODE": "VA23", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufsangebote anzeigen"},
    {"TCODE": "VA25", "PGMNA": "SD_SALES_DOCUMENT_VA25", "TTEXT": "Liste der Verkaufsangebote"},
    {"TCODE": "VA31", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufslieferpläne anlegen"},
    {"TCODE": "VA32", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufslieferpläne ändern"},
    {"TCODE": "VA33", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufslieferpläne anzeigen"},
    {"TCODE": "VA35", "PGMNA": "SAPMV75A", "TTEXT": "Liste der Verkaufslieferpläne"},
    {"TCODE": "VA41", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufskontrakte anlegen"},
    {"TCODE": "VA42", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufskontrakte ändern"},
    {"TCODE": "VA43", "PGMNA": "SAPMV45A", "TTEXT": "Verkaufskontrakte anzeigen"},
    {"TCODE": "VA45", "PGMNA": "SD_SALES_DOCUMENT_VA45", "TTEXT": "Liste der Verkaufskontrakte"},
    {"TCODE": "VA51", "PGMNA": "SAPMV45A", "TTEXT": "Positionsvorschlag anlegen"},
    {"TCODE": "VA52", "PGMNA": "SAPMV45A", "TTEXT": "Positionsvorschlag ändern"},
    {"TCODE": "VA53", "PGMNA": "SAPMV45A", "TTEXT": "Positionsvorschlag anzeigen"},
    {"TCODE": "VA71", "PGMNA": "SD70AV1A", "TTEXT": "Nachrichten aus Verkaufsbelegen"},
    {"TCODE": "VA88", "PGMNA": "SAPLKO71", "TTEXT": "Ist-Abrechnung: Kundenaufträge"},
    # XD* (11 total)
    {"TCODE": "XD01", "PGMNA": "SAPMF02D", "TTEXT": "Anlegen Debitor (Zentral)"},
    {"TCODE": "XD02", "PGMNA": "SAPMF02D", "TTEXT": "Ändern Debitor (Zentral)"},
    {"TCODE": "XD03", "PGMNA": "SAPMF02D", "TTEXT": "Anzeigen Debitor (Zentral)"},
    {"TCODE": "XD04", "PGMNA": "SAPMF01A", "TTEXT": "Änderungen Debitor (Zentral)"},
    {"TCODE": "XD05", "PGMNA": "SAPMF02D", "TTEXT": "Debitor sperren (zentral)"},
    {"TCODE": "XD06", "PGMNA": "SAPMF02D", "TTEXT": "Löschvormerkung Debitor (Zentral)"},
    {"TCODE": "XD07", "PGMNA": "SAPMF02D", "TTEXT": "Ändern Kontogruppe Debitor"},
    {"TCODE": "XD99", "PGMNA": "", "TTEXT": "Massenpflege Kundenstamm"},
    {"TCODE": "XDN1", "PGMNA": "SAPMSNUM", "TTEXT": "Nummernkreise Debitor"},
    # XK* (14 total)
    {"TCODE": "XK01", "PGMNA": "SAPMF02K", "TTEXT": "Anlegen Kreditor (Zentral)"},
    {"TCODE": "XK02", "PGMNA": "SAPMF02K", "TTEXT": "Ändern Kreditor (Zentral)"},
    {"TCODE": "XK03", "PGMNA": "SAPMF02K", "TTEXT": "Kreditoren anzeigen (zentral)"},
    {"TCODE": "XK04", "PGMNA": "SAPMF01A", "TTEXT": "Änderungen Kreditor (Zentral)"},
    {"TCODE": "XK05", "PGMNA": "SAPMF02K", "TTEXT": "Sperren Kreditor (Zentral)"},
    {"TCODE": "XK06", "PGMNA": "SAPMF02K", "TTEXT": "Löschvormerkung Kreditor (Zentral)"},
    {"TCODE": "XK07", "PGMNA": "SAPMF02K", "TTEXT": "Ändern Kontogruppe Kreditor"},
    {"TCODE": "XK11", "PGMNA": "SAPMV13A", "TTEXT": "Anlegen Kondition"},
    {"TCODE": "XK12", "PGMNA": "SAPMV13A", "TTEXT": "Ändern Kondition"},
    {"TCODE": "XK13", "PGMNA": "SAPMV13A", "TTEXT": "Anzeigen Kondition"},
    {"TCODE": "XK99", "PGMNA": "", "TTEXT": "Massenpflege Lieferantenstamm"},
    {"TCODE": "XKN1", "PGMNA": "SAPMSNUM", "TTEXT": "Nummernkreise anzeigen (Kreditor)"},
]


def main():
    """Add inline results to the catalog."""
    data_dir = project_root / "src" / "sapguimcp" / "data"
    catalog_file = data_dir / "transactions.json"

    # Load existing catalog
    if catalog_file.exists():
        with open(catalog_file, encoding="utf-8") as f:
            catalog_data = json.load(f)
        catalog = TransactionCatalog.model_validate(catalog_data)
        print(f"Loaded existing catalog with {len(catalog.transactions)} transactions")
    else:
        print("No existing catalog found, creating new one")
        catalog = TransactionCatalog(
            transactions=[],
            source_system="dev",
            language="DE",
            last_updated=datetime.now(UTC),
            tstc_count=0,
            enriched_count=0,
        )

    # Create lookup of existing transactions
    existing = {t.tcode: t for t in catalog.transactions}
    added = 0
    updated = 0

    # Add inline results
    for row in INLINE_RESULTS:
        tcode = row["TCODE"].upper()
        if tcode in existing:
            # Update if description is better
            if row["TTEXT"] and not existing[tcode].description:
                existing[tcode].description = row["TTEXT"]
                updated += 1
        else:
            # Add new transaction
            txn = TransactionInfo(
                tcode=tcode,
                description=row.get("TTEXT", ""),
                program=row.get("PGMNA", ""),
                screen_number=None,
                area=detect_area(tcode),
                enriched=False,
            )
            existing[tcode] = txn
            added += 1

    # Rebuild catalog
    catalog.transactions = sorted(existing.values(), key=lambda t: t.tcode)
    catalog.tstc_count = len(catalog.transactions)
    catalog.last_updated = datetime.now(UTC)

    # Save
    with open(catalog_file, "w", encoding="utf-8") as f:
        f.write(catalog.model_dump_json(indent=2))

    print(f"\nAdded {added} new transactions")
    print(f"Updated {updated} existing transactions")
    print(f"Total transactions: {len(catalog.transactions)}")
    print(f"Catalog saved to: {catalog_file}")


if __name__ == "__main__":
    main()
