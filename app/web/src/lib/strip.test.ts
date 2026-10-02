import assert from "node:assert/strict";
import test from "node:test";

import { cellSentence } from "./strip.ts";

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
    reason: "ok",
    hour: 12,
    locale: "ko",
  });
  assert.equal(inside.kind, "verdict");
  if (inside.kind === "verdict") assert.equal(inside.verdict, "window");
});

test("two_step still names the built verdict and a reason", () => {
  const row = cellSentence({
    mode: "two_step",
    inWindow: false,
    rating: 1,
    reason: "ok",
    hour: 11,
    locale: "ko",
  });
  assert.deepEqual(row, { kind: "verdict", hour: "11", verdict: "ok", why: "ok" });
});
