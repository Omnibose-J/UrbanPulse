import assert from "node:assert/strict";
import test from "node:test";

import { hourBounds, inServedRange, initialHour, kstNow } from "./kst.ts";

test("the map hour is an integer from 9 to 23, else the clamped clock hour", () => {
  assert.equal(initialHour("18", 3), 18);
  assert.equal(initialHour("9", 3), 9);
  assert.equal(initialHour("30", 14), 23);
  assert.equal(initialHour("2", 14), 9);
  assert.equal(initialHour("abc", 14), 14);
  assert.equal(initialHour("", 14), 14);
  assert.equal(initialHour("-3", 14), 14);
  assert.equal(initialHour(undefined, 2), 9);
  assert.equal(initialHour(undefined, 23), 23);
});

test("the served range is today through today plus seven", () => {
  assert.equal(inServedRange("2026-10-02", "2026-10-02"), true);
  assert.equal(inServedRange("2026-10-09", "2026-10-02"), true);
  assert.equal(inServedRange("2026-10-10", "2026-10-02"), false);
  assert.equal(inServedRange("2026-10-01", "2026-10-02"), false);
  assert.equal(inServedRange("2027-01-03", "2026-12-28"), true);
});

test("the clock is read in Seoul whatever the machine zone", () => {
  assert.deepEqual(kstNow(new Date("2026-10-02T15:30:00Z")), { date: "2026-10-03", hour: 0 });
  assert.deepEqual(kstNow(new Date("2026-10-02T14:59:00Z")), { date: "2026-10-02", hour: 23 });
});

test("hour bounds cross midnight at 23", () => {
  assert.deepEqual(hourBounds("2026-10-02", 23), ["2026-10-02T23:00:00+09:00", "2026-10-03T00:00:00+09:00"]);
});
