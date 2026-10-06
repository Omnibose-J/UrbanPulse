import assert from "node:assert/strict";
import test from "node:test";

import { busiestRange, cellFill, cellSentence, nextPick } from "./strip.ts";

test("windows_only does not state the two-step verdict: a cell outside the windows says the crowd and the next pick", () => {
  const day = [12, 13, 18, 19].map((h) => ({ h, rating: 1, in_window: h === 18 || h === 19, reason: "fit", crowd: 1 }));
  const outside = cellSentence({
    mode: "windows_only",
    inWindow: false,
    rating: 1,
    reason: "fit",
    hour: 12,
    locale: "ko",
    crowd: 2,
    hours: day,
  });
  assert.deepEqual(outside, { kind: "notPick", hour: "12", whys: ["reason.crowdOnly2"], next: { kind: "from", start: 18, end: 20 } });
  const english = cellSentence({
    mode: "windows_only",
    inWindow: false,
    rating: 1,
    reason: "outside_hours",
    hour: 12,
    locale: "en",
    crowd: 0,
    hours: day,
  });
  assert.deepEqual(english, { kind: "notPick", hour: "12 PM", whys: ["reason.outsideHours"], next: { kind: "from", start: 18, end: 20 } });
  // Tier B states "busier than usual" bands, never a level name.
  const station = cellSentence({ mode: "windows_only", inWindow: false, rating: 1, reason: "fit", hour: 12, locale: "ko", tier: "B", crowd: 2, hours: day });
  assert.deepEqual(station, { kind: "notPick", hour: "12", whys: ["reason.b2"], next: { kind: "from", start: 18, end: 20 } });
  // A not-picked cell without a crowd level is a data defect, not a blank.
  assert.throws(() => cellSentence({ mode: "windows_only", inWindow: false, rating: 1, reason: "fit", hour: 12, locale: "ko", hours: day }));
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

test("nextPick names the next window run after the hour, the day's first run once every window is behind, or nothing", () => {
  const cell = (h: number, inWindow: boolean) => ({ h, rating: 1, in_window: inWindow, reason: "fit", crowd: 1 });
  const day = [cell(9, false), cell(10, true), cell(11, true), cell(12, false), cell(18, true), cell(19, false)];
  assert.deepEqual(nextPick(day, 9), { kind: "from", start: 10, end: 12 });
  assert.deepEqual(nextPick(day, 12), { kind: "from", start: 18, end: 19 });
  assert.deepEqual(nextPick(day, 19), { kind: "day", start: 10, end: 12 });
  assert.equal(nextPick([cell(9, false), cell(10, false)], 9), null);
  assert.equal(nextPick(null, 9), null);
});

test("cellFill: window cells are the pick colour, windows_only cells are shaded by crowd, closed hours are hollow, two_step keeps its verdict colours", () => {
  assert.deepEqual(cellFill({ in_window: true, rating: 1, reason: "fit", crowd: 3 }, "windows_only"), { tone: "go", crowd: null, hollow: false, color: "var(--go)" });
  assert.deepEqual(cellFill({ in_window: false, rating: 1, reason: "fit", crowd: 2 }, "windows_only"), { tone: "bad", crowd: 2, hollow: false, color: "var(--crowd-2)" });
  assert.deepEqual(cellFill({ in_window: false, rating: 0, reason: "too_busy", crowd: 3 }, "windows_only"), { tone: "bad", crowd: 3, hollow: false, color: "var(--crowd-3)" });
  assert.deepEqual(cellFill({ in_window: false, rating: 0, reason: "outside_hours", crowd: 0 }, "windows_only"), { tone: "bad", crowd: null, hollow: true, color: "var(--bg)" });
  assert.deepEqual(cellFill({ in_window: false, rating: 1, reason: "fit", crowd: 1 }, "two_step"), { tone: "ok", crowd: null, hollow: false, color: "var(--ok)" });
  assert.deepEqual(cellFill({ in_window: false, rating: 0, reason: "too_busy", crowd: 3 }, "two_step"), { tone: "bad", crowd: null, hollow: false, color: "var(--bad)" });
  assert.throws(() => cellFill({ in_window: false, rating: 1, reason: "fit" }, "windows_only"));
});
