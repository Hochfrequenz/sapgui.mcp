/**
 * SE11 Table Metadata Extractor
 * Parses browser_snapshot output from SAP SE11 Dictionary view
 *
 * Usage: Pass the snapshot text to parseSE11Snapshot(snapshotText)
 * Returns: {tableName, description, fieldCount, fields: [{feldname, datenelement, datentyp, laenge, dezimalstellen, kurztext, schluesselfeld}]}
 */

function parseSE11Snapshot(snapshotText) {
    const result = {
        tableName: '',
        description: '',
        fieldCount: 0,
        fields: []
    };

    // Extract table name: textbox "Transp.Tabelle": /US4G/BILL_CYC
    const tableMatch = snapshotText.match(/textbox "Transp\.Tabelle":\s*([^\n]+)/);
    if (tableMatch) {
        result.tableName = tableMatch[1].trim();
    }

    // Extract description: textbox "Kurzbeschreibung": Abrechnungszyklus
    const descMatch = snapshotText.match(/textbox "Kurzbeschreibung":\s*([^\n]+)/);
    if (descMatch) {
        result.description = descMatch[1].trim();
    }

    // Extract field count: button "1" / button "/" / button "3"
    const countMatch = snapshotText.match(/button "(\d+)"\s*\n\s*- button \/\s*\n\s*- button "(\d+)"/);
    if (countMatch) {
        result.fieldCount = parseInt(countMatch[2]);
    }

    // Parse field rows
    // Pattern: row "Zum Auswählen einer Zeile drücken Sie die Leertaste. FELDNAME DATENELEMENT DATENTYP LÄNGE DEZ KOORD KURZTEXT":
    const rowPattern = /row "Zum Auswählen einer Zeile drücken Sie die Leertaste\.\s+([^"]+)":/g;
    let match;

    while ((match = rowPattern.exec(snapshotText)) !== null) {
        const rowData = match[1].trim();

        // Skip header row
        if (rowData.includes('Spalte für') || rowData.startsWith('Feld ')) continue;

        // Parse row data: FELDNAME [spaces] DATENELEMENT DATENTYP LÄNGE DEZ KOORD KURZTEXT...
        // Note: FELDNAME and DATENELEMENT can contain spaces internally, so we need smart parsing
        const parts = rowData.split(/\s+/);

        if (parts.length >= 6) {
            // Determine where kurztext starts (after position 5 which is KOORD)
            const feldname = parts[0];
            const datenelement = parts[1];
            const datentyp = parts[2];
            const laenge = parseInt(parts[3]) || 0;
            const dezimalstellen = parseInt(parts[4]) || 0;
            // parts[5] is KoordSystem (usually 0)
            const kurztext = parts.slice(6).join(' ');

            // Check if this is a key field by looking at the row content after the match
            const rowStart = match.index;
            const rowEnd = snapshotText.indexOf('\n        - row "', rowStart + 1);
            const rowContent = snapshotText.substring(rowStart, rowEnd > 0 ? rowEnd : rowStart + 1000);

            // Key field indicator: checkbox "" [checked]
            const isKey = /gridcell "":\s*\n\s*- checkbox "" \[checked\]/.test(rowContent);

            result.fields.push({
                feldname,
                datenelement,
                datentyp,
                laenge,
                dezimalstellen,
                kurztext,
                schluesselfeld: isKey
            });
        }
    }

    return result;
}

// For Node.js usage
if (typeof module !== 'undefined') {
    module.exports = { parseSE11Snapshot };
}

// Test
if (typeof require !== 'undefined' && require.main === module) {
    const testSnapshot = `
- textbox "Transp.Tabelle": /US4G/BILL_CYC
- textbox "Kurzbeschreibung": Abrechnungszyklus
- button "1"
- button /
- button "3"
- row "Zum Auswählen einer Zeile drücken Sie die Leertaste. MANDT   MANDT CLNT 3 0 0 Mandant":
  - gridcell "":
    - checkbox "" [checked]
- row "Zum Auswählen einer Zeile drücken Sie die Leertaste. BILL_CYCLE   /US4G/DE_BILL_CYCLE CHAR 2 0 0 Abrechnungszyklus":
  - gridcell "":
    - checkbox "" [checked]
`;
    console.log(JSON.stringify(parseSE11Snapshot(testSnapshot), null, 2));
}
