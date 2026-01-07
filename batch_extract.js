const fs = require('fs');

// Parse fields from SAP SE11 browser snapshot
function parseFieldsFromSnapshot(snapshot, beschreibung) {
  const fields = [];

  // Match all row patterns in the grid
  // Format: row "Zum Auswählen einer Zeile drücken Sie die Leertaste. FELDNAME   DATENELEMENT DATENTYP LAENGE DEZST 0 KURZTEXT":
  const lines = snapshot.split('\n');

  for (const line of lines) {
    // Match the row pattern
    const rowMatch = line.match(/row "Zum Auswählen.*?\. (\S+)\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+\d+\s+([^"]+)"/);
    if (rowMatch) {
      const [, feldname, datenelement, datentyp, laenge, dezst, kurztext] = rowMatch;

      // Check if key field (has [checked] in the row context)
      // We need to look for the checkbox pattern after the field name
      const isKey = line.includes('[checked]');

      fields.push({
        feldname,
        datenelement,
        datentyp,
        laenge: parseInt(laenge, 10),
        dezimalstellen: parseInt(dezst, 10),
        kurztext: kurztext.trim(),
        schluesselfeld: isKey
      });
    }
  }

  return {
    beschreibung,
    anzahl_felder: fields.length,
    felder: fields
  };
}

// Read existing metadata
function loadMetadata() {
  try {
    const content = fs.readFileSync('us4g_metadata.json', 'utf8');
    return JSON.parse(content);
  } catch (e) {
    return {
      extraktionsdatum: new Date().toISOString().split('T')[0],
      quelle: "SAP SE11 - ABAP Dictionary",
      beschreibung: "S/4 Utilities /US4G/ Tabellen-Feldmetadaten",
      fortschritt: { extrahiert: 0, gesamt: 613 },
      tabellen: {}
    };
  }
}

// Save metadata
function saveMetadata(meta) {
  fs.writeFileSync('us4g_metadata.json', JSON.stringify(meta, null, 2), 'utf8');
}

// Add table to metadata
function addTable(tableName, tableData) {
  const meta = loadMetadata();
  meta.tabellen[tableName] = tableData;
  meta.fortschritt.extrahiert = Object.keys(meta.tabellen).length;
  saveMetadata(meta);
  return meta.fortschritt.extrahiert;
}

module.exports = { parseFieldsFromSnapshot, loadMetadata, saveMetadata, addTable };

// Test
if (require.main === module) {
  const testSnapshot = `
  - textbox "Kurzbeschreibung": Test Description
  - row "Zum Auswählen einer Zeile drücken Sie die Leertaste. MANDT   MANDT CLNT 3 0 0 Mandant":
    - gridcell "Zum Auswählen einer Zeile drücken Sie die Leertaste."
    - gridcell "MANDT"
    - gridcell "": [checked]
  `;
  const result = parseFieldsFromSnapshot(testSnapshot, "Test");
  console.log(JSON.stringify(result, null, 2));
}
