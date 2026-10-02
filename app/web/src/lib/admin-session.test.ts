import assert from "node:assert/strict";
import test from "node:test";

import { sessionValid, sessionValue, tokenMatches } from "./admin-session.ts";

test("only the configured token matches, and an unset token admits nobody", () => {
  assert.equal(tokenMatches("right", "right"), true);
  assert.equal(tokenMatches("wrong", "right"), false);
  assert.equal(tokenMatches("righ", "right"), false);
  assert.equal(tokenMatches(["right"], "right"), false);
  assert.equal(tokenMatches(null, "right"), false);
  assert.equal(tokenMatches("", ""), false);
  assert.equal(tokenMatches("", undefined), false);
});

test("the session cookie is valid only for the current token and does not contain it", () => {
  const cookie = sessionValue("right");
  assert.equal(sessionValid(cookie, "right"), true);
  assert.equal(sessionValid(cookie, "rotated"), false);
  assert.equal(sessionValid("right", "right"), false);
  assert.equal(sessionValid(undefined, "right"), false);
  assert.equal(sessionValid(sessionValue(""), ""), false);
  assert.equal(cookie.includes("right"), false);
});
