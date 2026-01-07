// Script to find missing tables and add extracted tables to metadata
const fs = require('fs');

// Functions
function findMissing() {
  const allTables = JSON.parse(fs.readFileSync('us4g_transp_tables.json', 'utf8'));
  const metadata = JSON.parse(fs.readFileSync('us4g_metadata.json', 'utf8'));

  const allTableNames = allTables.tables.map(t => t.name);
  const extractedNames = Object.keys(metadata.tabellen);

  const missing = allTableNames.filter(name => !extractedNames.includes(name));

  console.log('Total tables:', allTableNames.length);
  console.log('Extracted:', extractedNames.length);
  console.log('Missing:', missing.length);

  fs.writeFileSync('missing_tables.json', JSON.stringify(missing, null, 2));
  return missing;
}

function addTable(tableName, tableData) {
  const metadata = JSON.parse(fs.readFileSync('us4g_metadata.json', 'utf8'));
  metadata.tabellen[tableName] = tableData;
  metadata.fortschritt.extrahiert = Object.keys(metadata.tabellen).length;
  fs.writeFileSync('us4g_metadata.json', JSON.stringify(metadata, null, 2));
  console.log(`Added ${tableName}, total: ${metadata.fortschritt.extrahiert}`);
}

function parseSnapshot(snapshot) {
  // Extract description - handle quoted strings
  let beschreibung = '';
  const descMatch1 = snapshot.match(/textbox "Kurzbeschreibung": "([^"]+)"/);
  const descMatch2 = snapshot.match(/textbox "Kurzbeschreibung": ([^\n]+)/);
  if (descMatch1) {
    beschreibung = descMatch1[1].trim();
  } else if (descMatch2) {
    beschreibung = descMatch2[1].trim().replace(/^"/, '').replace(/"$/, '');
  }

  // Extract total field count from button pattern before grid
  const countMatch = snapshot.match(/button "(\d+)"\s*\n\s*-\s+grid:/);
  const totalFields = countMatch ? parseInt(countMatch[1]) : 0;

  // Parse rows - each field row starts with specific pattern
  const felder = [];
  const seenFields = new Set();

  // Match rows with field data
  const rowPattern = /row "Zum Auswählen einer Zeile drücken Sie die Leertaste\. ([^"]+)":/g;
  let match;

  while ((match = rowPattern.exec(snapshot)) !== null) {
    const rowData = match[1];
    const rowStartIndex = match.index;

    // Find the content after this row until next row or rowgroup
    const nextRowMatch = snapshot.substring(rowStartIndex + match[0].length).match(/(?:\s*-\s+row "Zum Auswählen|\s*-\s+rowgroup)/);
    const rowEndOffset = nextRowMatch ? nextRowMatch.index : 500;
    const rowContent = snapshot.substring(rowStartIndex, rowStartIndex + match[0].length + rowEndOffset);

    // Parse row data: FELDNAME DATENELEMENT DATENTYP LAENGE DEZ KOORD KURZTEXT
    // Handle special cases where description might have colons or quotes
    const parts = rowData.split(/\s+/);
    if (parts.length < 5) continue;

    const feldname = parts[0];

    // Skip duplicates
    if (seenFields.has(feldname)) continue;
    seenFields.add(feldname);

    const datenelement = parts[1];
    const datentyp = parts[2];
    const laenge = parseInt(parts[3]) || 0;
    const dezimalstellen = parseInt(parts[4]) || 0;
    // parts[5] is KoordSystem (always 0), skip it
    const kurztext = parts.slice(6).join(' ');

    // Check for key field - look for checked checkbox in Key column
    const isKeyField = rowContent.includes('checkbox "" [checked]');

    felder.push({
      feldname,
      datenelement,
      datentyp,
      laenge,
      dezimalstellen,
      kurztext,
      schluesselfeld: isKeyField
    });
  }

  return {
    beschreibung,
    anzahl_felder: totalFields || felder.length,
    felder
  };
}

// CLI
const cmd = process.argv[2];
if (cmd === 'missing') {
  findMissing();
} else if (cmd === 'add') {
  const tableName = process.argv[3];
  const snapshotFile = process.argv[4];
  const snapshot = fs.readFileSync(snapshotFile, 'utf8');
  const tableData = parseSnapshot(snapshot);
  addTable(tableName, tableData);
} else if (cmd === 'addraw') {
  // Add pre-parsed table data from JSON file
  const dataFile = process.argv[3];
  const data = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
  for (const [tableName, tableData] of Object.entries(data)) {
    addTable(tableName, tableData);
  }
} else {
  findMissing();
}
