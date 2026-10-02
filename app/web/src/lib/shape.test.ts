import assert from "node:assert/strict";
import test from "node:test";

import { measuredNow, namedAltPlaces, requireForeignHeavy } from "./shape.ts";
import { normalizeConditions } from "./storage.ts";

test("a measured hour without a live row has no now line", () => {
  assert.equal(measuredNow({ level: 1, hour: 21, target_ts: "2026-10-01T21:00:00+09:00" }, null), null);
});

test("an alt place with no joined name is dropped", () => {
  const names = new Map([["POI001", { name: "Alpha", name_en: null }]]);
  const rows = namedAltPlaces(
    [
      { place_id: "POI001", hours: [13], crowd: 1 },
      { place_id: "POI045", hours: [18], crowd: 0 },
    ],
    names,
  );
  assert.deepEqual(rows.map((row) => row.place_id), ["POI001"]);
});

test("an invalid stored setting is replaced by the default", () => {
  assert.deepEqual(normalizeConditions({ purpose: "nope", tolerance: "moderate" }), {
    purpose: "sight",
    tolerance: "moderate",
  });
  assert.deepEqual(normalizeConditions({ purpose: "food", tolerance: "calm" }), {
    purpose: "food",
    tolerance: "calm",
  });
  assert.deepEqual(normalizeConditions({ purpose: "food", tolerance: "nope" }), {
    purpose: "food",
    tolerance: "moderate",
  });
});

test("a missing foreign_heavy flag is an error", () => {
  assert.equal(requireForeignHeavy(false), false);
  assert.throws(() => requireForeignHeavy(undefined), /foreign_heavy/);
});
