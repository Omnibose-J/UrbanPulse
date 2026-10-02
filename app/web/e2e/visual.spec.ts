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
  if (!en[2] && Number(en[1]) === 12) period = en[4].toUpperCase();
  else if (!en[2] && Number(en[1]) > Number(en[3])) period = en[4].toUpperCase() === "PM" ? "AM" : "PM";
  if (period === "PM" && hour < 12) hour += 12;
  if (period === "AM" && hour === 12) hour = 0;
  return hour;
}

async function kstHour(page: Page) {
  return page.evaluate(() =>
    Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", hour: "numeric", hourCycle: "h23" }).format(new Date())),
  );
}

async function fieldInset(page: Page) {
  const ok = await page.locator("[data-press]").evaluateAll((nodes) =>
    nodes
      .filter((node) => node.querySelector("[data-field-label]"))
      .every((node) => {
        const label = node.querySelector("[data-field-label]");
        if (!label) return false;
        return label.getBoundingClientRect().x >= node.getBoundingClientRect().x + 15.5;
      }),
  );
  expect(ok).toBe(true);
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
    await expect(page.locator("[data-busy-empty], [data-busy] [data-row]").first()).toBeVisible();
    await expect(page.locator("[data-quiet-empty], [data-quiet]").first()).toBeVisible();
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
    const card = page.locator("[data-quiet]").first();
    if (await card.count()) {
      const apart = await card.evaluate((node) => {
        const name = node.querySelector("[data-place-name]")?.getBoundingClientRect();
        const status = node.querySelector("[data-place-status]")?.getBoundingClientRect();
        if (!name || !status) return false;
        return name.right <= status.left + 0.5;
      });
      expect(apart).toBe(true);
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
        nodes.every((node) => {
          const cell = node as HTMLElement;
          if (!cell.textContent?.trim()) return true;
          return cell.getClientRects().length === 1 && cell.scrollWidth <= cell.clientWidth + 1;
        }),
      );
      expect(fits).toBe(true);
      if (locale === "en") {
        const width = await page.locator("[data-week-time]").first().evaluate((node) => Math.round((node as HTMLElement).clientWidth));
        expect(width).toBe(104);
      }
      await fieldInset(page);
      const today = page.locator("[data-row]", { hasText: locale === "ko" ? "오늘" : "Today" });
      if (await today.count()) {
        const time = await today.locator("[data-week-time]").innerText();
        const start = startHour(time);
        if (start !== null) expect(start).toBeGreaterThanOrEqual(hour);
      }
      await shot(page, `${locale}-week-${place.tier.toLowerCase()}`);
    }
  }
  let reference: Place | null = null;
  for (const place of places.filter((item) => item.tier === "A1").slice(0, 24)) {
    const body = await (await request.get(`/api/places/${place.id}/week?tolerance=moderate&purpose=sight`)).json();
    const ranked = (body.days as { state: string; date: string; windows: { score: number }[] | null }[])
      .filter((day) => day.windows && day.windows.length > 0 && day.state !== "off")
      .sort((a, b) => b.windows![0].score - a.windows![0].score || a.date.localeCompare(b.date));
    if (ranked[0]?.state === "reference") {
      reference = place;
      break;
    }
  }
  expect(reference).toBeTruthy();
  for (const locale of ["ko", "en"] as const) {
    await page.goto(`/${locale}/p/${reference!.id}`);
    const badge = page.locator("[data-answer-card] [data-badge]");
    await expect(badge).toBeVisible();
    const height = await badge.evaluate((node) => Math.round(node.getBoundingClientRect().height));
    expect(height).toBe(24);
  }
  expect(errors).toEqual([]);
});

test("day card, axis, and back label", async ({ page, request }) => {
  test.setTimeout(90000);
  const errors = watch(page);
  const listed = await (await request.get("/api/places?q=")).json();
  const places = (listed.places as Place[]).filter((item) => item.tier === "A1");
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
      const back = page.locator("header a").first();
      await expect(back.locator("svg")).toHaveCount(1);
      const lines = await back.locator("span").first().evaluate((node) => node.getClientRects().length);
      expect(lines).toBe(1);
      await fieldInset(page);
      if (sample.kind === "none" && locale === "ko") {
        await expect(page.locator("[data-field-label]", { hasText: "더 나아요" })).toHaveText(/^(오늘|[월화수목금토일])\(\d+\/\d+\) /);
      }
      await shot(page, `${locale}-day-${sample.kind}`);
    }
  }
  let holiday: { place: Place; date: string } | null = null;
  for (const place of places) {
    const body = await (await request.get(`/api/places/${place.id}/week?tolerance=moderate&purpose=sight`)).json();
    const day = (body.days as { date: string; holiday: unknown; windows: unknown[] | null }[]).find(
      (item) => item.holiday && item.windows && item.windows.length > 0,
    );
    if (day) {
      holiday = { place, date: day.date };
      break;
    }
  }
  expect(holiday).toBeTruthy();
  for (const locale of ["ko", "en"] as const) {
    await page.goto(`/${locale}/p/${holiday!.place.id}/${holiday!.date}`);
    const badge = page.locator("[data-answer-card] [data-badge]");
    await expect(badge).toBeVisible();
    const height = await badge.evaluate((node) => Math.round(node.getBoundingClientRect().height));
    expect(height).toBe(24);
  }
  expect(errors).toEqual([]);
});

test("search field sits in the bar and an off day says its state once", async ({ page }) => {
  const errors = watch(page);
  await page.goto("/ko/search");
  const field = page.locator("[data-search] input");
  await expect(field).toBeVisible();
  await expect(page.locator("[data-search-icon]")).toHaveCount(1);
  const textX = await field.evaluate((node) => node.getBoundingClientRect().x);
  expect(textX).toBeGreaterThanOrEqual(28);
  const langRight = await page.locator("[data-lang]").evaluate((node) => node.getBoundingClientRect().right);
  expect(390 - langRight).toBeLessThanOrEqual(16);
  await shot(page, "ko-search");
  await page.route("**/api/places/*/week**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        place: { id: "POI001", tier: "A1", name: "Sample", name_en: null, gu: "강남구", serve_state: "on", foreign_heavy: false },
        now: null,
        days: [
          { date: "2026-10-02", state: "on", off_reason: null, windows: [{ hours: [13], score: 1, crowd: 1, act: "sight", act_level: "lively" }], no_window: false, hours: null, strip_mode: "windows_only", holiday: null },
          { date: "2026-10-03", state: "off", off_reason: "preparing", windows: null, no_window: null, hours: null, strip_mode: null, holiday: null },
        ],
        combos: [{ purpose: "sight", tolerance: "moderate", state: "on" }],
      }),
    }),
  );
  await page.goto("/ko/p/POI001");
  const off = page.locator("[data-row]", { hasText: "준비 중" });
  await expect(off.getByText("준비 중")).toHaveCount(1);
  await expect(off.locator("[data-week-time]")).toHaveText("");
  expect(errors).toEqual([]);
});

test("map pins spread and the card button stays on screen", async ({ page }) => {
  test.setTimeout(90000);
  const errors = watch(page);
  for (const locale of ["ko", "en"] as const) {
    await page.goto(`/${locale}/map`);
    await expect.poll(async () => page.locator("[data-pin]").count(), { timeout: 20000 }).toBeGreaterThanOrEqual(20);
    await expect.poll(async () => page.locator("[data-pin-label]:visible").count(), { timeout: 15000 }).toBe(1);
    const spread = await page.locator("[data-pin]").evaluateAll((nodes) => {
      const rects = nodes.map((node) => node.getBoundingClientRect());
      const xs = rects.map((rect) => rect.x + rect.width / 2);
      const ys = rects.map((rect) => rect.y + rect.height / 2);
      return { width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
    });
    console.log(`pin-bbox ${locale} ${Math.round(spread.width)}x${Math.round(spread.height)}`);
    const pin = page.locator("[data-pin][data-selected='0']").first();
    await expect(pin).toHaveAttribute("data-pin-size", "18");
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
