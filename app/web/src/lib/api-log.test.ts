import assert from "node:assert/strict";
import test from "node:test";

import { logApiError } from "./api-log.ts";

test("an API error is logged once with the message only", () => {
  const lines: string[] = [];
  const original = console.error;
  console.error = (...args: unknown[]) => {
    lines.push(args.map(String).join(" "));
  };
  logApiError("home", new Error("boom"));
  console.error = original;
  assert.deepEqual(lines, ["[api] home boom"]);
});
