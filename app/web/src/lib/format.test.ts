import assert from "node:assert/strict";
import test from "node:test";

import { formatStoredWindows } from "./format.ts";

test("adjacent stored hours merge and a single hour spans the next hour", () => {
  const windows = [{ hours: [18] }, { hours: [19] }, { hours: [11] }];
  assert.deepEqual(formatStoredWindows(windows, "ko", "시"), ["18~20시", "11~12시"]);
  assert.deepEqual(formatStoredWindows([{ hours: [13] }], "ko", "시"), ["13~14시"]);
  assert.deepEqual(formatStoredWindows([{ hours: [13] }], "en", ""), ["1 to 2 PM"]);
});

test("a merged range keeps the pick position of its earliest hour", () => {
  const windows = [{ hours: [11] }, { hours: [19] }, { hours: [18] }];
  assert.deepEqual(formatStoredWindows(windows, "ko", "시"), ["11~12시", "18~20시"]);
});
