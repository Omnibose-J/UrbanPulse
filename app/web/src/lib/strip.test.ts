import assert from "node:assert/strict";
import test from "node:test";

import { busiestRange, cellSentence } from "./strip.ts";

test("windows_only does not state the two-step verdict", () => {
  const outside = cellSentence({
    mode: "windows_only",
    inWindow: false,
    rating: 1,
    reason: "ok",
    hour: 12,
    locale: "ko",
  });
  assert.deepEqual(outside, { kind: "notPick", hour: "12" });
  const english = cellSentence({
    mode: "windows_only",
    inWindow: false,
    rating: 1,
    reason: "ok",
    hour: 12,
    locale: "en",
  });
  assert.deepEqual(english, { kind: "notPick", hour: "12 PM" });
  const inside = cellSentence({
    mode: "windows_only",
    inWindow: true,
    rating: 1,
    reason: "fit",
    hour: 12,
    locale: "ko",
    tier: "A2",
    crowd: 1,
  });
  assert.equal(inside.kind, "verdict");
  if (inside.kind === "verdict") assert.equal(inside.verdict, "window");
});

test("two_step still names the built verdict and a reason", () => {
  const row = cellSentence({
    mode: "two_step",
    inWindow: false,
    rating: 1,
    reason: "fit",
    hour: 11,
    locale: "ko",
    tier: "A1",
    purpose: "sight",
    crowd: 0,
    act: "quiet",
  });
  assert.deepEqual(row, {
    kind: "verdict",
    hour: "11",
    verdict: "ok",
    whys: ["reason.crowd0", "reason.sightQuiet"],
  });
});

test("a window cell uses the crowd sentence in 12-hour English", () => {
  const row = cellSentence({
    mode: "windows_only",
    inWindow: true,
    rating: 1,
    reason: "fit",
    hour: 12,
    locale: "en",
    tier: "A1",
    purpose: "sight",
    crowd: 1,
    act: "lively",
  });
  assert.deepEqual(row, {
    kind: "verdict",
    hour: "12 PM",
    verdict: "window",
    whys: ["reason.crowd1", "reason.sightLively"],
  });
});

test("an unknown reason throws", () => {
  assert.throws(() =>
    cellSentence({
      mode: "two_step",
      inWindow: false,
      rating: 0,
      reason: "nope",
      hour: 11,
      locale: "ko",
    }),
  );
});

test("busiestRange names the longest run at the day's peak crowd level, outside the windows and the closed hours", () => {
  const cell = (h: number, crowd: number, reason = "fit", inWindow = false) => ({ h, rating: 1, in_window: inWindow, reason, crowd });
  const hours = [
    cell(9, 3, "closed"),
    cell(10, 1),
    cell(11, 2),
    cell(12, 2, "fit", true),
    cell(13, 2),
    cell(14, 2),
    cell(15, 2),
    cell(16, 1),
    cell(17, 2, "too_busy"),
    cell(18, 3, "outside_hours"),
  ];
  assert.deepEqual(busiestRange(hours), { start: 13, end: 16, crowd: 2 });
});

test("busiestRange takes the earliest run on a tie, accepts unsorted input, and reports the peak level", () => {
  const cell = (h: number, crowd: number) => ({ h, rating: 1, in_window: false, reason: "fit", crowd });
  const hours = [cell(20, 3), cell(19, 3), cell(11, 3), cell(12, 3), cell(15, 2), cell(16, 2), cell(17, 2)];
  assert.deepEqual(busiestRange(hours), { start: 11, end: 13, crowd: 3 });
});

test("busiestRange is null when the open hours never reach 'a bit busy', when only window hours are busy, and on empty input", () => {
  const cell = (h: number, crowd: number, inWindow = false, reason = "fit") => ({ h, rating: 1, in_window: inWindow, reason, crowd });
  assert.equal(busiestRange([cell(9, 0), cell(10, 1), cell(11, 1)]), null);
  assert.equal(busiestRange([cell(12, 3, true), cell(13, 1)]), null);
  assert.equal(busiestRange([cell(9, 3, false, "closed")]), null);
  assert.equal(busiestRange([]), null);
  assert.equal(busiestRange(null), null);
});
