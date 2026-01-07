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

    // Extract field count from buttons
    const countMatch = snapshotText.match(/button "(\d+)"\s*\n\s*- button \/\s*\n\s*- button "(\d+)"/);
    if (countMatch) {
        result.fieldCount = parseInt(countMatch[2]);
    }

    // Parse field rows
    const rowPattern = /row "Zum Auswählen einer Zeile drücken Sie die Leertaste\.\s+([A-Z0-9_./]+)\s+([A-Z0-9_./]+)\s+([A-Z]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([^"]+)":/g;
    let match;

    while ((match = rowPattern.exec(snapshotText)) !== null) {
        const feldname = match[1];
        const datenelement = match[2];
        const datentyp = match[3];
        const laenge = parseInt(match[4]) || 0;
        const dezimalstellen = parseInt(match[5]) || 0;
        const kurztext = match[7].trim();
        
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

// Read from stdin and parse
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
    const result = parseSE11Snapshot(input);
    console.log(JSON.stringify(result));
});
