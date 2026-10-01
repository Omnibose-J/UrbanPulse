import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles/tokens.css", import.meta.url), "utf8");
const tokens = {};
for (const match of css.matchAll(/(--[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)) {
  tokens[match[1]] = match[2];
}

function lin(hex) {
  const n = parseInt(hex.slice(1), 16);
  const channels = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((value) => {
    const s = value / 255;
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function ratio(fg, bg) {
  const lighter = Math.max(lin(fg), lin(bg));
  const darker = Math.min(lin(fg), lin(bg));
  return (lighter + 0.05) / (darker + 0.05);
}

const pairs = [
  ["--text", "--bg", 4.5],
  ["--text-2", "--bg", 4.5],
  ["--text-3", "--bg", 4.5],
  ["--go-text", "--bg", 4.5],
  ["--go-text", "--go-soft", 4.5],
  ["--on-ink", "--ink", 4.5],
  ["--go-bright", "--ink", 3],
  ["--on-ink-2", "--ink", 3],
  ["--on-ink-3", "--ink", 3],
  ["--error-fg", "--bg", 4.5],
  ["--hol", "--bg", 4.5],
  ["--stale-fg", "--bg", 4.5],
];

let failed = 0;
for (const [fg, bg, need] of pairs) {
  const value = ratio(tokens[fg], tokens[bg]);
  const ok = value + 1e-9 >= need;
  if (!ok) failed += 1;
  console.log(`${fg} on ${bg} ${value.toFixed(2)} need ${need} ${ok ? "ok" : "FAIL"}`);
}
if (failed) process.exit(1);
