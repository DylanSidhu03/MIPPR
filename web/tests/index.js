// `node --test web/tests/` resolves the folder to this file, which loads every *.test.mjs in it.
const { readdirSync } = require("node:fs");
const { join } = require("node:path");
const { pathToFileURL } = require("node:url");

for (const f of readdirSync(__dirname).filter((f) => f.endsWith(".test.mjs")).sort()) {
  import(pathToFileURL(join(__dirname, f)).href);
}
