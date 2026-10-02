import assert from "node:assert/strict";
import test from "node:test";

import { healthResponse } from "./health.ts";

test("a null place count is unavailable and zero is a real count", () => {
  assert.deepEqual(healthResponse(null, null), { status: 500, body: { error: "unavailable" } });
  assert.deepEqual(healthResponse(0, null), { status: 200, body: { db: "ok", places: 0 } });
  assert.deepEqual(healthResponse(12, new Error("down")), { status: 500, body: { error: "unavailable" } });
});
