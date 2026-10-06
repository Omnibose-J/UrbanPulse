import assert from "node:assert/strict";
import test from "node:test";

import { bestDay, withTodayTrimmed } from "./best.ts";

const day = (date: string, score: number | null, state = "on") => ({
  date,
  state,
  windows: score === null ? null : [{ hours: [13], score }],
});

test("best day is the highest first-window score among served days, the earlier date on a tie", () => {
  const days = [day("2026-10-06", 0.5), day("2026-10-07", 0.9), day("2026-10-08", 0.9), day("2026-10-09", 1.0, "off"), day("2026-10-10", null)];
  assert.equal(bestDay(days)?.date, "2026-10-07");
  assert.equal(bestDay([day("2026-10-06", null), day("2026-10-07", 1, "off")]), undefined);
});

test("today's windows that already ended are dropped before ranking", () => {
  const days = withTodayTrimmed([{ date: "2026-10-06", state: "on", windows: [{ hours: [10], score: 0.9 }, { hours: [20], score: 0.3 }] }, day("2026-10-07", 0.5)], "2026-10-06", 15);
  assert.deepEqual(days[0].windows, [{ hours: [20], score: 0.3 }]);
  assert.equal(bestDay(days)?.date, "2026-10-07");
});
