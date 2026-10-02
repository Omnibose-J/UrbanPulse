import assert from "node:assert/strict";
import test from "node:test";

import { likePattern, namedAltPlaces, nowFromLive, quietSelection, requireForeignHeavy, selectAll } from "./shape.ts";
import { normalizeConditions } from "./storage.ts";
import { reasonMessageIds } from "./strip.ts";

const NOW = Date.parse("2026-10-02T14:40:00+09:00");

test("no observation means no now line", () => {
  assert.equal(nowFromLive(null, NOW), null);
});

test("a fresh observation gives its level; one older than 90 minutes is stale and states no level", () => {
  const fresh = nowFromLive({ ts: "2026-10-02T14:00:00+09:00", pop_min: 10, pop_max: 20, level: 2 }, NOW);
  assert.deepEqual(fresh, { level: 2, source: "live", stale: false, ts: "2026-10-02T14:00:00+09:00", pop_min: 10, pop_max: 20 });
  const edge = nowFromLive({ ts: "2026-10-02T13:10:00+09:00", pop_min: 10, pop_max: 20, level: 2 }, NOW);
  assert.equal(edge?.stale, false);
  const late = nowFromLive({ ts: "2026-10-02T13:09:00+09:00", pop_min: 10, pop_max: 20, level: 2 }, NOW);
  assert.equal(late?.stale, true);
  assert.equal(late?.level, null);
  assert.equal(late?.ts, "2026-10-02T13:09:00+09:00");
});

test("open-and-quiet keeps A1 places with measured activity in the last two clock hours and open A2 places", () => {
  const rows = [
    { id: "busy", tier: "A1", level: 2, hour: 14 },
    { id: "lively", tier: "A1", level: 1, hour: 14 },
    { id: "low", tier: "A1", level: 0, hour: 14 },
    { id: "old", tier: "A1", level: 0, hour: 14 },
    { id: "unmeasured", tier: "A1", level: 0, hour: 14 },
    { id: "park", tier: "A2", level: 0, hour: 14 },
    { id: "closed-palace", tier: "A2", level: 0, hour: 14 },
    { id: "station", tier: "B", level: 0, hour: 14 },
  ];
  const activity = new Map([
    ["busy", { hour: 14, value: 0.9 }],
    ["lively", { hour: 12, value: 0.5 }],
    ["low", { hour: 14, value: 0.49 }],
    ["old", { hour: 11, value: 0.9 }],
  ]);
  const chosen = quietSelection(rows, 14, activity, new Set(["park"]));
  assert.deepEqual(chosen.map((row) => [row.id, row.activity]), [["lively", 0.5], ["park", null]]);
});

test("selectAll reads every page and stops at a short one", async () => {
  const all = Array.from({ length: 2500 }, (_, index) => index);
  const calls: [number, number][] = [];
  const rows = await selectAll(async (from, to) => {
    calls.push([from, to]);
    return { data: all.slice(from, to + 1), error: null };
  });
  assert.equal(rows.length, 2500);
  assert.deepEqual(calls, [[0, 999], [1000, 1999], [2000, 2999]]);
  await assert.rejects(selectAll(async () => ({ data: null, error: { message: "boom" } })), /boom/);
});

test("a search text is matched literally", () => {
  assert.equal(likePattern("서울역(1호선)"), "%서울역(1호선)%");
  assert.equal(likePattern("100%"), "%100\\%%");
  assert.equal(likePattern("a_b"), "%a\\_b%");
  assert.equal(likePattern("a\\b"), "%a\\\\b%");
});

test("a window with no activity clause is a whole sentence, not a fragment", () => {
  assert.deepEqual(reasonMessageIds("A2", { crowd: 1, act: null, act_level: null }), ["reason.crowdOnly1"]);
  assert.deepEqual(reasonMessageIds("A1", { crowd: 2, act: "food", act_level: "lively" }), ["reason.crowd2", "reason.foodLively"]);
  assert.deepEqual(reasonMessageIds("B", { crowd: 2, act: null, act_level: null }), ["reason.b2"]);
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
