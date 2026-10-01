import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";

const dir = "e2e/screenshots/live";

type Place = { id: string; tier: string; name: string; name_en: string | null };
type Day = { date: string; state: string; windows: { hours: number[] }[] | null; no_window: boolean | null; hours: unknown[] | null };

function watch(page: Page) {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}

function rangeCount(text: string) {
  const ko = text.match(/\d+~\d+시/g) ?? [];
  const en = text.match(/\d+\s*(?:AM|PM)?\s+to\s+\d+\s*(?:AM|PM)/gi) ?? [];
  return ko.length + en.length;
}

function startHour(text: string): number | null {
  if (/추천 없음|No pick/.test(text)) return null;
  const ko = text.match(/(\d+)~\d+시/);
  if (ko) return Number(ko[1]);
  const en = text.match(/(\d+)\s*(AM|PM)?\s+to\s+(\d+)\s*(AM|PM)/i);
  if (!en) return null;
  let hour = Number(en[1]);
  let period = (en[2] || en[4] || "").toUpperCase();
  if (!en[2] && Number(en[1]) > Number(en[3])) period = en[4].toUpperCase() === "PM" ? "AM" : "PM";
  if (period === "PM" && hour < 12) hour += 12;
  if (period === "AM" && hour === 12) hour = 0;
  return hour;
}

async function kstHour(page: Page) {
  return page.evaluate(() =>
    Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }).format(new Date())),
  );
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: `${dir}/${name}.png`, fullPage: true });
}

test.beforeAll(() => {
  fs.mkdirSync(dir, { recursive: true });
});

test("home matches the mockup measurements", async ({ page }) => {
  test.setTimeout(60000);
  const errors = watch(page);
  const hour = await kstHour(page);
  for (const locale of ["ko", "en"] as const) {
    await page.goto(`/${locale}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const search = await page.locator(`a[href='/${locale}/search'] span`).boundingBox();
    expect(search!.x).toBeGreaterThanOrEqual(28);
    const cards = page.locator("[data-quiet]");
    const count = await cards.count();
    for (let index = 0; index < count; index += 1) {
      const card = cards.nth(index);
      await expect(card.locator("[data-status-dot]")).toHaveCount(1);
      await expect(card.locator("[data-mini-strip] > *")).toHaveCount(15);
    }
    const ranges = (await page.locator(".phone-shell").innerText()).match(/\d+~\d+시|\d+\s*(?:AM|PM)?\s+to\s+\d+\s*(?:AM|PM)/gi) ?? [];
    for (const range of ranges) {
      const start = startHour(range);
      if (start !== null) expect(start).toBeGreaterThanOrEqual(hour);
    }
    await shot(page, `${locale}-home`);
  }
  await page.route("**/api/home**", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.busy_top = [];
    await route.fulfill({ status: response.status(), contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/ko");
  await expect(page.getByText("지금은 붐비는 곳이 없어요")).toBeVisible();
  await page.goto("/en");
  await expect(page.getByText("Nothing is busy right now")).toBeVisible();
  expect(errors).toEqual([]);
});

test("week cards show one range and even rows", async ({ page, request }) => {
  test.setTimeout(90000);
  const errors = watch(page);
  const hour = await kstHour(page);
  const listed = await (await request.get("/api/places?q=")).json();
  const places = listed.places as Place[];
  const a1 = places.find((item) => item.tier === "A1");
  const a2 = places.find((item) => item.tier === "A2");
  expect(a1 && a2).toBeTruthy();
  for (const place of [a1!, a2!]) {
    for (const locale of ["ko", "en"] as const) {
      await page.goto(`/${locale}/p/${place.id}`);
      const card = page.locator("[data-answer-card]");
      await expect(card).toBeVisible();
      const text = await card.innerText();
      expect(text).toContain(locale === "en" && place.name_en ? place.name_en : place.name);
      expect(rangeCount(text)).toBe(1);
      await expect(card.locator("p.body")).not.toHaveText("");
      const box = await card.boundingBox();
      expect(box!.y + box!.height).toBeLessThanOrEqual(844);
      const heights = await page.locator("[data-row]").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
      expect(heights.length).toBe(8);
      expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
      const fits = await page.locator("[data-week-time]").evaluateAll((nodes) =>
        nodes.every((node) => node.getClientRects().length === 1),
      );
      expect(fits).toBe(true);
      const today = page.locator("[data-row]", { hasText: locale === "ko" ? "오늘" : "Today" });
      if (await today.count()) {
        const time = await today.locator("[data-week-time]").innerText();
        const start = startHour(time);
        if (start !== null) expect(start).toBeGreaterThanOrEqual(hour);
      }
      await shot(page, `${locale}-week-${place.tier.toLowerCase()}`);
    }
  }
  expect(errors).toEqual([]);
});

test("day card, axis, and back label", async ({ page, request }) => {
  test.setTimeout(90000);
  const errors = watch(page);
  const listed = await (await request.get("/api/places?q=")).json();
  const places = (listed.places as Place[]).filter((item) => item.tier === "A1").slice(0, 12);
  let withWindow: { place: Place; date: string } | null = null;
  let without: { place: Place; date: string } | null = null;
  for (const place of places) {
    const body = await (await request.get(`/api/places/${place.id}/week?tolerance=moderate&purpose=sight`)).json();
    for (const day of body.days as Day[]) {
      if (!withWindow && day.windows && day.windows.length > 0 && day.state !== "off") withWindow = { place, date: day.date };
      if (!without && day.hours && day.hours.length > 0 && (!day.windows || day.windows.length === 0 || day.no_window)) without = { place, date: day.date };
    }
    if (withWindow && without) break;
  }
  expect(withWindow).toBeTruthy();
  expect(without).toBeTruthy();
  for (const locale of ["ko", "en"] as const) {
    for (const sample of [
      { ...withWindow!, kind: "window" },
      { ...without!, kind: "none" },
    ]) {
      await page.goto(`/${locale}/p/${sample.place.id}/${sample.date}`);
      const card = page.locator("[data-answer-card]");
      await expect(card).toBeVisible();
      const text = await card.innerText();
      expect(text).toContain(locale === "en" && sample.place.name_en ? sample.place.name_en : sample.place.name);
      expect(text).toMatch(locale === "ko" ? /\d+월/ : /[A-Z][a-z]{2},/);
      if (sample.kind === "window") await expect(card.locator("p.body")).not.toHaveText("");
      await expect(page.locator("[data-axis-label='1']")).toHaveCount(5);
      const lines = await page.locator("header a span").first().evaluate((node) => node.getClientRects().length);
      expect(lines).toBe(1);
      await shot(page, `${locale}-day-${sample.kind}`);
    }
  }
  expect(errors).toEqual([]);
});

test("map pins spread and the card button stays on screen", async ({ page }) => {
  test.setTimeout(90000);
  const errors = watch(page);
  for (const locale of ["ko", "en"] as const) {
    await page.goto(`/${locale}/map`);
    await expect.poll(async () => page.locator("[data-pin]").count(), { timeout: 20000 }).toBeGreaterThanOrEqual(20);
    const spread = await page.locator("[data-pin]").evaluateAll((nodes) => {
      const rects = nodes.map((node) => node.getBoundingClientRect());
      const xs = rects.map((rect) => rect.x + rect.width / 2);
      const ys = rects.map((rect) => rect.y + rect.height / 2);
      return { width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
    });
    console.log(`pin-bbox ${locale} ${Math.round(spread.width)}x${Math.round(spread.height)}`);
    expect(spread.width).toBeGreaterThan(150);
    expect(spread.height).toBeGreaterThan(150);
    const canvas = page.locator("[data-map] canvas");
    if (await canvas.count()) {
      const size = await canvas.first().evaluate((node) => ({ width: node.clientWidth, height: node.clientHeight }));
      expect(size.width).toBeGreaterThan(0);
      expect(size.height).toBeGreaterThan(0);
    }
    const button = await page.locator("[data-map-action]").boundingBox();
    expect(button).toBeTruthy();
    expect(button!.y).toBeGreaterThanOrEqual(0);
    expect(button!.y + button!.height).toBeLessThanOrEqual(844);
    await shot(page, `${locale}-map`);
  }
  expect(errors).toEqual([]);
});
