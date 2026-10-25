// Bundles the userscript built in mods/ into the standalone service, so the app ships its own copy
// instead of downloading one from a CDN on every page load.
//
//     cd mods && npm install && npm run build      ->  dist/userScript.js
//     node build-userscript.js [outDir]            ->  [outDir]/userscript.js
//
// The generated module exports { version, code }: the version comes from the app's config.xml.

const fs = require('fs');
const path = require('path');

const source = path.join(__dirname, '../../dist/userScript.js');
const outDir = path.resolve(process.argv[2] || __dirname);
const out = path.join(outDir, 'userscript.js');
const configXml = path.join(__dirname, '../config.xml');

if (!fs.existsSync(source)) {
    console.error('No userscript to bundle. Build it first: cd mods && npm install && npm run build');
    process.exit(1);
}

const config = fs.readFileSync(configXml, 'utf8');
const version = (config.match(/<widget[^>]*\bversion="([^"]+)"/) || [])[1] || '0.0.0';
const code = fs.readFileSync(source, 'utf8');

if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(out, "'use strict';\nmodule.exports = " + JSON.stringify({ version: version, code: code }) + ';\n');
console.log('Bundled the userscript ' + version + ' (' + Math.round(code.length / 1024) + ' KB) into ' + out);
