import { expect, test } from "@playwright/test";

import { hours, place, week } from "./fixtures/place";
import { kstDate } from "./helpers";

test("a failed map request shows the error box and no pins", async ({ page }) => {
  await page.route("**/api/map**", (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "unavailable" }) }));
  await page.goto("/ko/map");
  await expect(page.locator("[data-state=error]")).toBeVisible();
  await expect(page.locator("[data-pin]")).toHaveCount(0);
});

test("a blocked map style shows the error box", async ({ page }) => {
  await page.route("https://tiles.openfreemap.org/**", (route) => route.abort());
  await page.goto("/ko/map");
  await expect(page.locator("[data-state=error]")).toBeVisible({ timeout: 15000 });
});

test("a switched-off combination is not a day with no pick", async ({ page }) => {
  await page.route("**/api/places/*/recommend**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        recommendation: { state: "off", off_reason: "failed", windows: null, no_window: null, hours: null, strip_mode: null },
        place,
        holiday: null,
        combos: week.combos,
        alt_dates: [{ date: kstDate(3), hours: [13], score: 1 }],
        alt_places: [],
      }),
    }),
  );
  await page.goto(`/ko/p/POI001/${kstDate(2)}`);
  await expect(page.getByText("이 조건은 아직 준비하고 있어요")).toBeVisible();
  await expect(page.locator("[data-field-label]")).toBeVisible();
  await expect(page.getByText("이날은 추천할 시간이 없어요")).toHaveCount(0);
  await expect(page.locator("a", { hasText: "더 나아요" })).toHaveCount(0);
});

test("a switched-off station still shows the condition", async ({ page }) => {
  await page.route("**/api/places/*/recommend**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        recommendation: { state: "off", off_reason: "unverified", windows: null, no_window: null, hours: null, strip_mode: null },
        place: { ...place, id: "STN001", tier: "B", name: "서울역" },
        holiday: null,
        combos: [{ purpose: "none", tolerance: "moderate", state: "off" }],
        alt_dates: [],
        alt_places: [],
      }),
    }),
  );
  await page.goto(`/ko/p/STN001/${kstDate(2)}`);
  await expect(page.getByText("이 조건은 아직 준비하고 있어요")).toBeVisible();
  await expect(page.locator("[data-field-label]")).toBeVisible();
  await expect(page.locator("a", { hasText: "더 나아요" })).toHaveCount(0);
});

test("an off week row shows the preparing text and no strip", async ({ page }) => {
  await page.route("**/api/places/*/week**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        place,
        now: null,
        days: [
          { date: "2026-10-02", state: "on", off_reason: null, windows: [{ hours: [13], score: 1 }], no_window: false, hours: hours(), strip_mode: "windows_only", holiday: null },
          { date: "2026-10-03", state: "off", off_reason: "preparing", windows: null, no_window: null, hours: null, strip_mode: null, holiday: null },
        ],
        combos: week.combos,
      }),
    }),
  );
  await page.goto("/ko/p/POI001");
  const off = page.locator("[data-row]", { hasText: "준비 중" });
  await expect(off).toBeVisible();
  await expect(off.locator("[data-week-time]")).toHaveText("");
  await expect(off.getByText("준비 중")).toHaveCount(1);
  await expect(off.locator("[data-mini-strip]")).toHaveCount(0);
});
