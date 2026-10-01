import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

function token(): string {
  const file = path.resolve(__dirname, "../../../.env");
  const line = readFileSync(file, "utf8")
    .split(/\r?\n/)
    .find((item) => item.startsWith("ADMIN_TOKEN="));
  return line ? line.slice("ADMIN_TOKEN=".length).trim() : "";
}

test("admin eval stays hidden without the right token", async ({ request }) => {
  expect((await request.get("/admin/eval")).status()).toBe(404);
  expect((await request.get("/admin/eval?token=wrong")).status()).toBe(404);
  const value = token();
  const response = await request.get(`/admin/eval?token=${encodeURIComponent(value)}`);
  expect(response.status()).toBe(value ? 200 : 404);
});
