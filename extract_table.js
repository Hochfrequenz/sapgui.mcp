// Parse SAP SE11 snapshot to extract table fields
function parseSnapshot(snapshot) {
  const fields = [];
  const beschreibungMatch = snapshot.match(/textbox "Kurzbeschreibung": ([^\n]+)/);
  const beschreibung = beschreibungMatch ? beschreibungMatch[1].trim() : '';

  // Parse rows from the grid
  const rowRegex = /row "Zum Auswählen einer Zeile.*? (\S+)\s+(?:(\S+))?\s+(\S+)\s+(\S+)\s+(\d+)\s+(\d+)\s+\d+\s+([^"]+)"/g;
  let match;

  while ((match = rowRegex.exec(snapshot)) !== null) {
    const feldname = match[1];
    const datenelement = match[3] || match[2];
    const datentyp = match[4];
    const laenge = parseInt(match[5], 10);
    const dezst = parseInt(match[6], 10);
    const kurztext = match[7].trim();

    // Determine if key field by checking if checkbox is checked
    const rowText = match[0];
    const isKey = rowText.includes('[checked]');

    fields.push({
      feldname,
      datenelement,
      datentyp,
      laenge,
      dezimalstellen: dezst,
      kurztext,
      schluesselfeld: isKey
    });
  }

  return { beschreibung, fields };
}

// Test with sample
const sample = process.argv[2] || '';
if (sample) {
  console.log(JSON.stringify(parseSnapshot(sample), null, 2));
}
