import assert from "node:assert/strict";
import test from "node:test";

import { GatewayRejected, isGatewayRejection } from "./gateway.ts";

test("an HTML block page from the edge gateway is a rejection", () => {
  const page = '<!DOCTYPE html>\n<html class="no-js" lang="en-US">\n<head>\n<title>Attention Required! | Cloudflare</title>';
  assert.equal(isGatewayRejection(page), true);
  assert.equal(isGatewayRejection(page.toUpperCase()), true);
});

test("ordinary driver messages and empty messages are not rejections", () => {
  assert.equal(isGatewayRejection('column "x" does not exist'), false);
  assert.equal(isGatewayRejection("unavailable"), false);
  assert.equal(isGatewayRejection("<html>a page from somewhere else</html>"), false);
  assert.equal(isGatewayRejection(""), false);
  assert.equal(isGatewayRejection(null), false);
});

test("the error names its cause without any input text", () => {
  const error = new GatewayRejected();
  assert.equal(error.message, "search text rejected by the gateway");
  assert.equal(error.name, "GatewayRejected");
});
