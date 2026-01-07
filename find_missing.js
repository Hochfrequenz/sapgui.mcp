const fs = require('fs');
const meta = JSON.parse(fs.readFileSync('us4g_metadata.json', 'utf8'));
const tables = JSON.parse(fs.readFileSync('us4g_transp_tables.json', 'utf8'));
const extracted = new Set(Object.keys(meta.tabellen));
const missing = tables.tables.filter(t => !extracted.has(t.name)).map(t => t.name);
console.log(JSON.stringify({
  extracted: extracted.size,
  total: tables.total_count,
  missing: missing.length,
  missingTables: missing
}, null, 2));
