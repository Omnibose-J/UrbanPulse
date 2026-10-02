import { expect, test } from "@playwright/test";

import { kstDate, strayHangul, watch } from "./helpers";

// Live local stack, no mocks.
test.use({ locale: "ko-KR" });

const mapCalls = (api: string[]) => api.filter((path) => path.startsWith("/api/map")).length;

test("map keeps date and hour in the address, never refetches on the slider, and survives a trip to the day", async ({ page }) => {
  const seen = watch(page);
  await page.goto("/ko/map");
  await expect(page.locator("[data-pin]").first()).toBeVisible({ timeout: 20000 });
  await expect(page).toHaveURL(new RegExp(`date=${kstDate()}&hour=\\d+$`));

  const target = kstDate(2);
  await page.locator(`[data-day="${target}"]`).click();
  await expect(page.locator(`[data-day="${target}"]`)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("[data-pin]").first()).toBeVisible();
  const calls = mapCalls(seen.api);
  const slider = page.locator("input[type=range]");
  await slider.fill("18");
  await slider.fill("19");
  await slider.fill("17");
  await expect(page).toHaveURL(new RegExp(`date=${target}&hour=17$`));
  expect(mapCalls(seen.api)).toBe(calls);

  // the card speaks about the chosen hour and never states the unverified verdict
  const card = page.locator("[data-map-card]");
  await expect(card.locator("[data-hour-sentence]")).toContainText("17시는");
  await expect(card).not.toContainText("가도 괜찮아요");
  await expect(card).not.toContainText("피하는 게 좋아요");
  await expect(page.locator("[data-legend]")).toHaveCount(1);

  // ⑦ -> ⑤ -> app back: same day, same hour
  await page.locator("[data-map-action]").click();
  await expect(page).toHaveURL(new RegExp(`/ko/p/[A-Z0-9]+/${target}\\?from=map&hour=17$`));
  await page.locator("header a").first().click();
  await expect(page).toHaveURL(new RegExp(`/ko/map\\?date=${target}&hour=17$`));
  await expect(page.locator(`[data-day="${target}"]`)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("input[type=range]")).toHaveValue("17");

  expect(seen.errors).toEqual([]);
  expect(seen.failed).toEqual([]);
});

test("a nonsense address is corrected instead of drawn", async ({ page }) => {
  const seen = watch(page);
  await page.goto("/ko/map?date=2020-01-01&hour=abc");
  await expect(page.locator("[data-pin]").first()).toBeVisible({ timeout: 20000 });
  await expect(page).toHaveURL(new RegExp(`date=${kstDate()}&hour=(9|1\\d|2[0-3])$`));
  await expect(page.getByText("NaN")).toHaveCount(0);
  await page.goto("/ko/map?hour=2");
  await expect(page).toHaveURL(/hour=9$/);
  expect(seen.failed).toEqual([]);
});

test("stations are off by default, add pins when on, and the choice is remembered", async ({ page }) => {
  await page.goto("/ko/map");
  await expect(page.locator("[data-pin]").first()).toBeVisible({ timeout: 20000 });
  const without = await page.locator("[data-pin]").count();
  await expect(page.locator("[data-pin^=STN]")).toHaveCount(0);
  await page.getByLabel("역세권 포함").check();
  await expect.poll(() => page.locator("[data-pin]").count()).toBeGreaterThan(without);
  await expect(page.locator("[data-pin^=STN]").first()).toHaveAttribute("aria-label", /· 추정$/);
  await page.reload();
  await expect(page.getByLabel("역세권 포함")).toBeChecked();
  await expect.poll(() => page.locator("[data-pin]").count()).toBeGreaterThan(without);
});

test("a switched-off combination draws no pin for its places", async ({ page, request }) => {
  await page.addInitScript(() => localStorage.setItem("urbanpulse.conditions", JSON.stringify({ purpose: "sight", tolerance: "calm" })));
  const body = await (await request.get(`/api/map?date=${kstDate(1)}&tolerance=calm&purpose=sight&stations=0`)).json();
  const on = body.places.filter((place: { state: string }) => place.state !== "off").length;
  const off = body.places.length - on;
  expect(off).toBeGreaterThan(0);
  await page.goto(`/ko/map?date=${kstDate(1)}&hour=14`);
  await expect.poll(() => page.locator("[data-pin]").count(), { timeout: 20000 }).toBe(on);
});

test("zooming in is kept when the hour changes", async ({ page }) => {
  await page.goto("/ko/map");
  await expect(page.locator("[data-pin]").first()).toBeVisible({ timeout: 20000 });
  const small = await page.locator("[data-pin][data-selected='0']").first().getAttribute("data-pin-size");
  expect(small).toBe("18");
  await expect(page.locator("[data-map][data-map-ready='1']")).toBeVisible({ timeout: 20000 });
  await page.locator("[data-map] canvas").focus();
  // Each press animates one zoom step; presses sent without a pause merge into one.
  for (let index = 0; index < 4; index += 1) {
    await page.keyboard.press("Equal");
    await page.waitForTimeout(700);
  }
  await expect.poll(() => page.locator("[data-pin][data-selected='0']").first().getAttribute("data-pin-size")).toBe("28");
  await page.locator("input[type=range]").fill("20");
  await page.waitForTimeout(500);
  expect(await page.locator("[data-pin][data-selected='0']").first().getAttribute("data-pin-size")).toBe("28");
});

test.describe("desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 }, locale: "en-US" });

  test("the list is ordered, moves the map, links to the day, and speaks English", async ({ page }) => {
    const seen = watch(page);
    await page.goto("/en/map");
    const rows = page.locator("[data-list-row]");
    await expect(rows.first()).toBeVisible({ timeout: 20000 });
    const tones = await rows.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-tone")));
    const rank = { go: 0, ok: 1, bad: 2 } as Record<string, number>;
    expect(tones.map((tone) => rank[tone!])).toEqual([...tones.map((tone) => rank[tone!])].sort((a, b) => a - b));
    await expect(page.locator("[data-map-card]")).toBeHidden();
    const third = rows.nth(2);
    await third.getByRole("button").click();
    await expect(third.getByRole("button")).toHaveAttribute("aria-pressed", "true");
    const id = await third.getAttribute("data-list-row");
    await expect(page.locator(`[data-pin="${id}"]`)).toHaveAttribute("data-selected", "1");
    await expect(third.getByRole("link")).toHaveAttribute("href", new RegExp(`/en/p/${id}/\\d{4}-\\d{2}-\\d{2}\\?from=map&hour=\\d+$`));
    await expect(page.locator("[data-cond-button]")).toBeVisible();
    expect(await strayHangul(page)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});
