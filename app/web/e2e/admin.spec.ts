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

test("the admin page opens only through the form, and the token never rides in an address", async ({ page, request, context }) => {
  const value = token();
  expect(value, "ADMIN_TOKEN is not set in .env").not.toBe("");

  expect((await request.get("/admin/eval")).status()).toBe(404);
  expect((await request.get(`/admin/eval?token=${encodeURIComponent(value)}`)).status()).toBe(404);

  await page.goto("/admin");
  await page.locator("input[name=token]").fill("wrong");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.locator("input[name=token]")).toBeVisible();
  expect((await context.cookies()).filter((cookie) => cookie.name === "up_admin")).toEqual([]);

  await page.locator("input[name=token]").fill(value);
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/eval$/);
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();

  const cookie = (await context.cookies()).find((item) => item.name === "up_admin");
  expect(cookie).toBeTruthy();
  expect(cookie!.httpOnly).toBe(true);
  expect(cookie!.sameSite).toBe("Strict");
  expect(cookie!.path).toBe("/admin");
  expect(cookie!.value).not.toContain(value);
});
