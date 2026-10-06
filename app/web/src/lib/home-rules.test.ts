import assert from "node:assert/strict";
import test from "node:test";

import { pickBusy, pickQuiet } from "./home-rules.ts";

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

test("quiet list: A1 by activity then A2, and within each a commuter station comes after the other kinds", () => {
  const rows = [
    { id: "station-busy", tier: "A1", activity: 9, category: "인구밀집지역" },
    { id: "street", tier: "A1", activity: 1, category: "발달상권" },
    { id: "tourist", tier: "A1", activity: 2, category: "관광특구" },
    { id: "park", tier: "A2", activity: null, category: "공원" },
    { id: "a2-dense", tier: "A2", activity: null, category: "인구밀집지역" },
    { id: "palace", tier: "A2", activity: null, category: "고궁·문화유산" },
  ];
  assert.deepEqual(
    pickQuiet(rows).map((row) => row.id),
    ["tourist", "street", "station-busy", "park", "palace"],
  );
});
