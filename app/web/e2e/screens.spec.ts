import { expect, test, type Page, type Route } from "@playwright/test";

import { hours, place, week } from "./fixtures/place";

const day = "2026-12-15";

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockVisitor(page: Page, overrides?: { week?: unknown; home?: unknown; recommend?: unknown }) {
  const weekBody = overrides?.week ?? week;
  const home = overrides?.home ?? {
    as_of: "2026-10-01T10:00:00+09:00",
    stale: false,
    busy_top: [
      { id: "POI001", name: "Alpha", name_en: null, gu: "Gangnam", level: 3, window: { hours: [18] } },
      { id: "POI002", name: "Beta", name_en: null, gu: "Mapo", level: 2, window: { hours: [19] } },
      { id: "POI003", name: "Gamma", name_en: null, gu: "Jongno", level: 2, window: { hours: [13] } },
      { id: "POI004", name: "Delta", name_en: null, gu: "Songpa", level: 1, window: null },
      { id: "POI005", name: "Epsilon", name_en: null, gu: "Seocho", level: 0, window: { hours: [11] } },
    ],
    open_quiet: [
      { id: "POI006", name: "Quiet A", name_en: null, gu: "Yongsan", level: 1, tier: "A1", window: { hours: [13] }, hours: hours(), strip_mode: "windows_only" },
      { id: "POI007", name: "Quiet B", name_en: null, gu: "Nowon", level: 0, tier: "A2", window: { hours: [10] }, hours: hours(), strip_mode: "windows_only" },
    ],
  };
  const recommend = overrides?.recommend ?? {
    recommendation: {
      state: "on",
      off_reason: null,
      windows: [{ hours: [18] }, { hours: [19] }, { hours: [11] }],
      no_window: false,
      hours: hours(),
      strip_mode: "windows_only",
    },
    place,
    holiday: null,
    combos: week.combos,
    alt_dates: [{ date: "2026-12-16", hours: [13], score: 0.9 }],
    alt_places: [{ place_id: "POI045", hours: [18], name: "Nearby", name_en: null, crowd: 1 }],
  };
  await page.route("**/api/home**", (route) => json(route, home));
  await page.route("**/api/places?**", (route) => json(route, { places: [{ ...place, name: "Alpha" }] }));
  await page.route("**/api/places/*/week**", (route) => json(route, weekBody));
  await page.route("**/api/places/*/recommend**", (route) => json(route, recommend));
  await page.route("**/api/places/*/day**", (route) => json(route, { hours: [] }));
  await page.route("**/api/map**", (route) =>
    json(route, {
      places: [
        {
          ...place,
          lat: 37.5,
          lon: 127,
          state: "on",
          windows: [{ hours: [13] }],
          hours: hours(),
          strip_mode: "windows_only",
        },
      ],
    }),
  );
  await page.route("**/api/flags**", (route) => json(route, { rows: [] }));
}

test("D1 answer card is inside the first viewport", async ({ page }) => {
  await mockVisitor(page);
  for (const locale of ["ko", "en"]) {
    await page.goto(`/${locale}/p/POI001`);
    const weekCard = page.locator("[data-answer-card]");
    await expect(weekCard).toBeVisible();
    const weekBox = await weekCard.boundingBox();
    expect(weekBox).toBeTruthy();
    expect(weekBox!.y).toBeGreaterThanOrEqual(0);
    expect(weekBox!.y + weekBox!.height).toBeLessThanOrEqual(844);
    await page.goto(`/${locale}/p/POI001/${day}`);
    const dayCard = page.locator("[data-answer-card]");
    await expect(dayCard).toBeVisible();
    const dayBox = await dayCard.boundingBox();
    expect(dayBox!.y).toBeGreaterThanOrEqual(0);
    expect(dayBox!.y + dayBox!.height).toBeLessThanOrEqual(844);
  }
});

test("D3 screenshots of each state", async ({ page }) => {
  await page.goto("/ko");
  await mockVisitor(page, {
    week: { ...week, place: { ...place, serve_state: "preparing" }, days: week.days.map((row) => ({ ...row, state: "off", off_reason: "preparing", windows: null, hours: null })) },
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-state=preparing]").screenshot({ path: "e2e/screenshots/preparing.png" });

  await mockVisitor(page, { week: { ...week, now: { ...week.now, stale: true } } });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/stale.png" });

  await page.unroute("**/api/places/*/week**");
  await page.route("**/api/places/*/week**", (route) => json(route, { error: "unavailable" }, 500));
  await page.goto("/ko/p/POI001");
  await page.locator("[data-state=error]").screenshot({ path: "e2e/screenshots/error.png" });

  await page.unroute("**/api/places/*/week**");
  await page.route("**/api/places/*/week**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800));
    await json(route, week);
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-state=skeleton]").screenshot({ path: "e2e/screenshots/skeleton.png" });

  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "off", off_reason: "myeongjeol", windows: null, no_window: null, hours: null, strip_mode: null },
      place,
      holiday: { name: "추석", kind: "chuseok" },
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.locator("[data-state=myeongjeol]").screenshot({ path: "e2e/screenshots/myeongjeol.png" });

  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "on", off_reason: null, windows: [], no_window: true, hours: hours("closed"), strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [{ date: "2026-12-16", hours: [13], score: 0.4 }],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/no-window.png" });

  await mockVisitor(page, {
    recommend: {
      recommendation: { state: "reference", off_reason: null, windows: [{ hours: [13] }], no_window: false, hours: hours(), strip_mode: "windows_only" },
      place,
      holiday: null,
      combos: week.combos,
      alt_dates: [],
      alt_places: [],
    },
  });
  await page.goto(`/ko/p/POI001/${day}`);
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/reference.png" });

  await mockVisitor(page, {
    week: { ...week, place: { ...place, tier: "B", serve_state: "experimental" }, now: null },
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/tier-b.png" });

  await mockVisitor(page, {
    week: { ...week, days: week.days.map((row) => ({ ...row, windows: [], no_window: true, state: "on" })) },
  });
  await page.goto("/ko/p/POI001");
  await page.locator("[data-answer-card]").screenshot({ path: "e2e/screenshots/week-no-pick.png" });
});

test("D4 changing purpose moves off a tolerance that is not ready", async ({ page }) => {
  await mockVisitor(page);
  await page.addInitScript(() => {
    localStorage.setItem("urbanpulse.conditions", JSON.stringify({ purpose: "sight", tolerance: "calm" }));
  });
  await page.goto("/ko/p/POI001");
  await page.getByRole("button", { name: "바꾸기" }).click();
  await page.getByRole("radio", { name: "맛집" }).click();
  await expect(page.getByText("바꿨어요")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "바꾸기" }).click();
  await expect(page.getByRole("button", { name: /한적하게/ })).toBeVisible();
});

test("D5 share link back opens the week of the same place", async ({ page }) => {
  await mockVisitor(page);
  await page.goto(`/ko/p/POI001/${day}?purpose=food&tol=moderate`);
  await page.getByRole("link", { name: "이번 주" }).click();
  await expect(page).toHaveURL(/\/ko\/p\/POI001$/);
});

test("D6 pressable heights and the 16px text line", async ({ page }) => {
  await mockVisitor(page);
  await page.goto("/ko");
  const title = page.getByRole("heading", { level: 1 });
  const box = await title.boundingBox();
  expect(Math.round(box!.x)).toBe(16);
  const presses = page.locator("[data-press]");
  const count = await presses.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const height = (await presses.nth(index).boundingBox())!.height;
    expect(height).toBe(48);
  }
  const bar = page.locator("header").first();
  expect((await bar.boundingBox())!.height).toBe(56);
});

test("D9 english pages keep Hangul inside lang=ko", async ({ page }) => {
  await mockVisitor(page);
  await page.goto("/en");
  const leaked = await page.evaluate(() => {
    const found: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode.textContent ?? "";
      if (!/[가-힣]/.test(text)) continue;
      const parent = walker.currentNode.parentElement;
      if (parent?.closest('[lang="ko"]')) continue;
      found.push(text.trim());
    }
    return found;
  });
  expect(leaked).toEqual([]);
});

test("D10 slider does not refetch and back restores the map hour", async ({ page }) => {
  await mockVisitor(page);
  let mapCalls = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/map")) mapCalls += 1;
  });
  await page.goto(`/ko/map?date=${day}&hour=13`);
  await expect(page.locator("[data-pin]")).toHaveAttribute("data-tone", "go");
  const before = mapCalls;
  await page.locator("[data-hour]").fill("18");
  expect(mapCalls).toBe(before);
  await page.locator("[data-map-card]").click();
  await page.getByRole("link", { name: "지도" }).click();
  await expect(page).toHaveURL(new RegExp(`date=${day}`));
  await expect(page).toHaveURL(/hour=18/);
});

test("D11 windows_only uses two tones", async ({ page }) => {
  await mockVisitor(page);
  await page.goto(`/ko/p/POI001/${day}`);
  await expect(page.locator("[data-cell]").first()).toBeVisible();
  const tones = await page.locator("[data-cell]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-tone")));
  expect(tones).toContain("go");
  expect(tones).toContain("bad");
  expect(tones).not.toContain("ok");
});

test("D12 home rows follow the fixture order and quiet levels", async ({ page }) => {
  await mockVisitor(page);
  await page.goto("/ko");
  await expect(page.getByRole("link", { name: "Alpha" })).toBeVisible();
  const names = await page.locator("ol a").allTextContents();
  expect(names[0]).toContain("Alpha");
  expect(names[4]).toContain("Epsilon");
  const quiet = await page.locator("[data-quiet]").evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-quiet")));
  expect(quiet.every((level) => level === "0" || level === "1")).toBe(true);
});

test("D1 and live smoke walk the home list when a busy row exists", async ({ page }) => {
  const statuses: { url: string; status: number }[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/")) statuses.push({ url: response.url(), status: response.status() });
  });
  await page.goto("/ko");
  await expect(page.locator("[data-busy-empty], [data-busy] [data-row]").first()).toBeVisible();
  const first = page.locator("[data-busy] [data-row]").first();
  if (await first.count()) {
    await first.click();
    await expect(page).toHaveURL(/\/ko\/p\//);
    await page.locator("[data-answer-card]").click();
    await expect(page).toHaveURL(/\/ko\/p\/.+\/\d{4}-\d{2}-\d{2}/);
  } else {
    await expect(page.locator("[data-busy-empty]")).toBeVisible();
  }
  expect(statuses.every((item) => item.status === 200)).toBe(true);
});
