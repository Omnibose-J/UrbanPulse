import { readFileSync } from "node:fs";

const ko = JSON.parse(readFileSync(new URL("../messages/ko.json", import.meta.url), "utf8"));
const en = JSON.parse(readFileSync(new URL("../messages/en.json", import.meta.url), "utf8"));

function leaves(value, prefix, out) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      leaves(child, prefix ? `${prefix}.${key}` : key, out);
    }
    return;
  }
  out.push(prefix);
}

function keySet(tree) {
  const keys = [];
  leaves(tree, "", keys);
  return keys;
}

function walk(value, problems) {
  if (typeof value === "string") {
    if (value.includes("\u2014") || value.includes("\u2013")) problems.push(value);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item) => walk(item, problems));
    return;
  }
  if (value && typeof value === "object") {
    Object.values(value).forEach((item) => walk(item, problems));
  }
}

const koKeys = keySet(ko).sort();
const enKeys = keySet(en).sort();
const missing = koKeys.filter((key) => !enKeys.includes(key));
const extra = enKeys.filter((key) => !koKeys.includes(key));
const dashes = [];
walk(ko, dashes);
walk(en, dashes);
if (missing.length || extra.length || dashes.length) {
  console.error(JSON.stringify({ missing, extra, dashes: dashes.length }));
  process.exit(1);
}
console.log(koKeys.length);
