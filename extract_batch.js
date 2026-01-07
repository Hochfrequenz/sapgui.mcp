// Parse SE11 snapshot and return table metadata
function parseSE11Snapshot(snapshotText) {
    const result = {
        tableName: '',
        description: '',
        fieldCount: 0,
        fields: []
    };

    // Extract table name from textbox
    const tableMatch = snapshotText.match(/textbox "Transp\.Tabelle":\s*([^\n]+)/);
    if (tableMatch) {
        result.tableName = tableMatch[1].trim();
    }

    // Extract description
    const descMatch = snapshotText.match(/textbox "Kurzbeschreibung":\s*([^\n]+)/);
    if (descMatch) {
        result.description = descMatch[1].trim();
    }

    // Extract field count from buttons (e.g., button "1" / button "14")
    const countMatch = snapshotText.match(/button "(\d+)"\s*\n\s*- button \/\s*\n\s*- button "(\d+)"/);
    if (countMatch) {
        result.fieldCount = parseInt(countMatch[2]);
    }

    // Parse field rows - updated pattern to match the snapshot format
    // Look for rows with pattern: row "Zum Auswählen... FELDNAME DATA..."
    const rowPattern = /row "Zum Auswählen einer Zeile drücken Sie die Leertaste\.\s+([A-Z0-9_./]+)\s+([A-Z0-9_./]+)\s+([A-Z]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([^"]+)":/g;
    let match;

    while ((match = rowPattern.exec(snapshotText)) !== null) {
        const feldname = match[1];
        const datenelement = match[2];
        const datentyp = match[3];
        const laenge = parseInt(match[4]) || 0;
        const dezimalstellen = parseInt(match[5]) || 0;
        const kurztext = match[7].trim();
        
        // Check if field row has [checked] for key field
        const rowStart = match.index;
        const nextRowStart = snapshotText.indexOf('- row "Zum Auswählen', rowStart + 1);
        const rowContent = snapshotText.substring(rowStart, nextRowStart > 0 ? nextRowStart : rowStart + 2000);
        const isKey = /checkbox "" \[checked\]/.test(rowContent);
        
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

    return result;
}

// Test with sample if run directly
if (require.main === module) {
    const fs = require('fs');
    const testSnapshot = fs.readFileSync(process.argv[2] || 'test_snapshot.txt', 'utf8');
    console.log(JSON.stringify(parseSE11Snapshot(testSnapshot), null, 2));
}

module.exports = { parseSE11Snapshot };
