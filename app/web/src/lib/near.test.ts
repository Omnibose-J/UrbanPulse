import assert from "node:assert/strict";
import test from "node:test";

import { distanceParts, haversineKm, nearbyPicks } from "./near.ts";

const place = (id: string, lat: number, lon: number, extra: Partial<{ tier: string; state: string; windows: { hours: number[] }[] | null }> = {}) => ({
  id,
  tier: "A1",
  name: id,
  name_en: null,
  lat,
  lon,
  state: "on",
  windows: [{ hours: [14] }, { hours: [19] }],
  ...extra,
});

test("haversine: Gangnam station to City Hall is about 8 km", () => {
  const km = haversineKm(37.4979, 127.0276, 37.5663, 126.9779);
  assert.ok(km > 8.5 && km < 9.3, String(km));
});

test("nearby picks: nearest first, only places with a pick still ahead, never tier B, off or unplaced rows, at most five", () => {
  const me = { lat: 37.5, lon: 127.0 };
  const rows = [
    place("far", 37.6, 127.1),
    place("near", 37.501, 127.001),
    place("mid", 37.52, 127.02),
    place("station", 37.5, 127.0, { tier: "B" }),
    place("off", 37.5, 127.0, { state: "off" }),
    place("gone", 37.5, 127.0, { windows: [{ hours: [9] }] }),
    place("none", 37.5, 127.0, { windows: null }),
    place("nolatlon", null as unknown as number, 127.0),
    place("e", 37.55, 127.05),
    place("f", 37.56, 127.06),
    place("g", 37.57, 127.07),
  ];
  const picked = nearbyPicks(rows, me.lat, me.lon, 12);
  assert.deepEqual(
    picked.map((row) => row.id),
    ["near", "mid", "e", "f", "g"],
  );
  assert.equal(picked[0].now, false);
  assert.deepEqual(picked[0].window, { hours: [14] });
});

test("nearby picks: a pick that includes the current hour is 'now', and an earlier pick of today is skipped", () => {
  const picked = nearbyPicks([place("a", 37.5, 127.0)], 37.5, 127.0, 19);
  assert.equal(picked[0].now, true);
  assert.deepEqual(picked[0].window, { hours: [19] });
});

test("distance parts: metres below one kilometre (rounded to ten), otherwise one decimal of kilometres", () => {
  assert.deepEqual(distanceParts(0.846), { unit: "m", value: "850" });
  assert.deepEqual(distanceParts(0.04), { unit: "m", value: "40" });
  assert.deepEqual(distanceParts(1.26), { unit: "km", value: "1.3" });
  assert.deepEqual(distanceParts(12), { unit: "km", value: "12.0" });
});
