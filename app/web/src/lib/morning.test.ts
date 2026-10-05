import assert from "node:assert/strict";
import test from "node:test";

import { isNight, morningPicks } from "./morning.ts";

const row = (id: string, start: number, score: number, extra: Partial<{ state: string; serve_state: string; tier: string }> = {}) => ({
  id,
  state: "on",
  serve_state: "on",
  tier: "A1",
  windows: [{ hours: [start, start + 1], score }],
  ...extra,
});

test("morning picks keep windows that start between 9 and 11, best score first, at most five", () => {
  const rows = [
    row("late", 12, 0.99),
    row("a", 9, 0.4),
    row("b", 11, 0.9),
    row("c", 10, 0.8),
    row("d", 9, 0.7),
    row("e", 10, 0.6),
    row("f", 11, 0.5),
    row("early", 8, 0.95),
  ];
  assert.deepEqual(
    morningPicks(rows).map((item) => item.id),
    ["b", "c", "d", "e", "f"],
  );
});

test("morning picks drop off, reference, preparing and tier B rows, and rows without a window", () => {
  const rows = [
    row("off", 9, 0.9, { state: "off" }),
    row("ref", 9, 0.9, { state: "reference" }),
    row("prep", 9, 0.9, { serve_state: "preparing" }),
    row("b", 9, 0.9, { tier: "B" }),
    { ...row("none", 9, 0.9), windows: null },
    { ...row("empty", 9, 0.9), windows: [] },
    row("ok", 9, 0.1),
  ];
  assert.deepEqual(
    morningPicks(rows).map((item) => item.id),
    ["ok"],
  );
});

test("night is 20:00 to 05:59 KST", () => {
  assert.equal(isNight(20), true);
  assert.equal(isNight(23), true);
  assert.equal(isNight(0), true);
  assert.equal(isNight(5), true);
  assert.equal(isNight(6), false);
  assert.equal(isNight(12), false);
  assert.equal(isNight(19), false);
});
