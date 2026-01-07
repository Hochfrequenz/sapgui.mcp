const allTables = require('./us4g_transp_tables.json').tables.map(t => t.name);
const meta = require('./us4g_metadata.json');
const extracted = Object.keys(meta.tabellen || {});
const missing = allTables.filter(t => extracted.indexOf(t) === -1);
console.log('Missing tables:', missing.length);
console.log(JSON.stringify(missing));
