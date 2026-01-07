// parse_se11_snapshot.js
// Parses SE11 browser_snapshot output to extract table field metadata

function parseSE11Snapshot(snapshotText) {
    const result = {
        tableName: '',
        description: '',
        fields: [],
        fieldCount: 0
    };

    // Extract table name
    const tableMatch = snapshotText.match(/textbox "Transp\.Tabelle": ([^\n]+)/);
    if (tableMatch) result.tableName = tableMatch[1].trim();

    // Extract description
    const descMatch = snapshotText.match(/textbox "Kurzbeschreibung": ([^\n]+)/);
    if (descMatch) result.description = descMatch[1].trim();

    // Extract field count from "1 / 82" pattern
    const countMatch = snapshotText.match(/button "(\d+)"\n\s*- button \/\n\s*- button "(\d+)"/);
    if (countMatch) result.fieldCount = parseInt(countMatch[2]);

    // Parse field rows
    // Pattern: row "Zum Auswählen... FELDNAME DATENELEMENT DATENTYP LÄNGE DEZ KOORD KURZTEXT"
    const rowPattern = /row "Zum Auswählen einer Zeile drücken Sie die Leertaste\. ([^\n"]+)":/g;
    let match;

    while ((match = rowPattern.exec(snapshotText)) !== null) {
        const rowData = match[1].trim();
        // Skip header
        if (rowData.startsWith('Feld') || rowData.includes('Spalte für')) continue;

        // Parse: FELDNAME spaces DATENELEMENT DATENTYP LÄNGE DEZ KOORD KURZTEXT
        // Example: "MANDT   MANDT CLNT 3 0 0 Mandant"
        const parts = rowData.split(/\s+/);
        if (parts.length >= 6) {
            const field = {
                feldname: parts[0],
                datenelement: parts[1],
                datentyp: parts[2],
                laenge: parseInt(parts[3]) || 0,
                dezimalstellen: parseInt(parts[4]) || 0,
                // parts[5] is KoordSystem (usually 0)
                kurztext: parts.slice(6).join(' '),
                schluesselfeld: false
            };

            // Check for key field by looking at the row content after this match
            const rowStart = match.index;
            const rowEnd = snapshotText.indexOf('- row "', rowStart + 1);
            const rowContent = snapshotText.substring(rowStart, rowEnd > 0 ? rowEnd : rowStart + 2000);

            // Key field has [checked] checkbox in the Key column (3rd gridcell)
            const keyPattern = /gridcell "":\s*\n\s*- checkbox "" \[checked\]/;
            if (keyPattern.test(rowContent)) {
                field.schluesselfeld = true;
            }

            result.fields.push(field);
        }
    }

    return result;
}

// Test with sample
const testSnapshot = `
- textbox "Transp.Tabelle": /US4G/EDN_AMI
- textbox "Kurzbeschreibung": OBSOLET
- button "1"
- button /
- button "82"
- row "Zum Auswählen einer Zeile drücken Sie die Leertaste. MANDT   MANDT CLNT 3 0 0 Mandant":
  - gridcell "MANDT"
  - gridcell "":
    - checkbox "" [checked] [disabled]
`;

console.log(JSON.stringify(parseSE11Snapshot(testSnapshot), null, 2));

module.exports = { parseSE11Snapshot };
