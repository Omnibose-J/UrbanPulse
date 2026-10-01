import assert from "node:assert/strict";
import test from "node:test";

import { pickBusy } from "./home-rules.ts";

test("busy list keeps only levels 2 and 3", () => {
  const rows = [
    { level: 3, popMax: 1 },
    { level: 2, popMax: 1 },
    { level: 1, popMax: 9 },
    { level: 0, popMax: 9 },
  ];
  assert.deepEqual(
    pickBusy(rows).map((row) => row.level),
    [3, 2],
  );
});

test("busy list is empty when every level is 1 or 0", () => {
  const rows = [
    { level: 1, popMax: 4 },
    { level: 0, popMax: 9 },
  ];
  assert.equal(pickBusy(rows).length, 0);
});
